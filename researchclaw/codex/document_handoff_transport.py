"""Loopback-only consumer HTTP. Credentials use separate 0600 connection files."""
import base64
import hashlib
import json
import os
import re
from http.client import HTTPException
from pathlib import Path
from urllib import request, error, parse
from uuid import uuid4
from .atlas_client import AtlasClient, _NoRedirect
from .document_handoff_adapter import VERSION, require

MAX_BYTES=128*1024*1024


class TransportError(ValueError):
    def __init__(self,code,status=0):
        super().__init__(code)
        self.status=status


class HandoffHTTP(AtlasClient):
    def request(self, method, path, payload=None, params=None):
        raw=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode() if payload is not None else None
        return self._send(method,path,raw,'application/json',params)

    def _send(self,method,path,data,content_type,params=None):
        base,token=self._connection()
        require(path.startswith('/api/') and '?' not in path and '#' not in path and '\\' not in path and '..' not in parse.unquote(path).split('/'),'invalid_path')
        url=base+path+('?' + parse.urlencode(params) if params else '')
        req=request.Request(url,data=data,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':content_type})
        try:
            with request.build_opener(request.ProxyHandler({}),_NoRedirect()).open(req,timeout=30) as response:
                raw=response.read(40*1024*1024+1)
            require(len(raw)<=40*1024*1024,'response_too_large')
            result=json.loads(raw)
            require(isinstance(result,dict),'invalid_response')
            return result
        except error.HTTPError as exc:
            try:
                value=json.loads(exc.read(65536));nested=value.get('error');code=nested.get('code') if isinstance(nested,dict) else value.get('error_code')
                if not isinstance(code,str) or not re.fullmatch('[a-zA-Z_]+',code):code='http_error'
            except (ValueError,TypeError):code='http_error'
            raise TransportError(code,exc.code) from None
        except (OSError,HTTPException) as exc:
            raise TransportError('transport_unavailable') from None

    @staticmethod
    def _bytes(path,expected):
        # Original/asset bytes are rechecked on every replay, not trusted by path.
        with open(path,'rb') as f:
            require(os.fstat(f.fileno()).st_size<=MAX_BYTES,'source_too_large')
            data=f.read(MAX_BYTES+1)
        require(len(data)<=MAX_BYTES and hashlib.sha256(data).hexdigest()==expected,'source_changed')
        return data

    def recover_or_submit(self,row):
        operation,key=row['operation'],row['request_key']
        try:
            return self.request('GET','/api/integration/receipts/'+parse.quote(key,safe=''),params={'operation':operation})
        except TransportError as exc:
            if exc.status!=404 or str(exc)!='RECEIPT_NOT_FOUND':raise
        fields=row['documents_request'];source=row['atlas_request']['source']
        raw=self._bytes(fields['original_path'],source['sha256'])
        filename=source['filename']
        require(isinstance(filename,str) and filename not in ('','.','..') and not any(c in filename for c in '/\\\r\n\x00"'),'invalid_filename')
        common=dict(contract_version=VERSION,request_key=key,config_revision=fields['config_revision'],retrieval_consumer_id=fields['retrieval_consumer_id'])
        if operation=='convert.jats':
            require(len(raw)<=32*1024*1024,'source_too_large')
            assets=[];total=len(raw)
            for asset in fields.get('assets',[]):
                data=self._bytes(asset['path'],asset['sha256']);total+=len(data)
                require(len(data)<=24*1024*1024 and total<=MAX_BYTES,'assets_too_large')
                assets.append(dict(href=asset['href'],content_base64=base64.b64encode(data).decode(),source_url=asset.get('source_url','')))
            return self.request('POST','/api/tasks/jats',dict(common,filename=filename,xml_base64=base64.b64encode(raw).decode(),assets=assets))
        require(operation=='convert.file','invalid_operation')
        boundary='pilot-'+uuid4().hex;parts=[]
        for name,value in common.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+raw+b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        return self._send('POST','/api/tasks',b''.join(parts),'multipart/form-data; boundary='+boundary)
