"""Local Atlas transport. Credentials never enter request journals or browser payloads."""
import base64
import binascii
import hashlib
import json
import os
import re
import stat
from urllib import request, error, parse

MAX_RAW = 10_485_760
MAX_RESPONSE = 40 * 1024 * 1024  # QA raw base64 plus parsed record.
VERSION = 'pilot-atlas/1.0'


class AtlasError(ValueError):
    def __init__(self, code, *, status=0, retryable=False, details=None):
        super().__init__(code)
        self.status, self.retryable = status, retryable
        self.details = details or {}


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def unpack_raw(raw, expected, limit=MAX_RAW):
    try:
        if raw['encoding'] != 'base64' or type(raw['size_bytes']) is not int:
            raise ValueError()
        if not 0 <= raw['size_bytes'] <= limit or len(raw['content_base64']) > (limit+2)//3*4:
            raise ValueError()
        data = base64.b64decode(raw['content_base64'], validate=True)
        if len(data) != raw['size_bytes'] or hashlib.sha256(data).hexdigest() != expected or raw['sha256'] != expected:
            raise ValueError()
        return data
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise AtlasError('atlas_raw_invalid') from None


class AtlasClient:
    def __init__(self, connection_file):
        self.connection_file = connection_file

    def _connection(self):
        try:
            fd = os.open(self.connection_file, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                meta = os.fstat(stream.fileno())
                if not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_uid != os.getuid():
                    raise ValueError()
                config = json.loads(stream.read(65537))
            url = parse.urlsplit(config['url'])
            if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
                raise ValueError()
            if not isinstance(config['token'],str) or not config['token'] or '\n' in config['token'] or '\r' in config['token']:
                raise ValueError()
            return config['url'].rstrip('/'), config['token']
        except (OSError, ValueError, KeyError, TypeError):
            raise AtlasError('atlas_connection_invalid') from None

    def request(self, method, path, payload=None, params=None):
        url, token = self._connection()
        if not path.startswith('/api/') or '?' in path or '#' in path:
            raise AtlasError('atlas_path_invalid')
        url += path + (('?' + parse.urlencode(params)) if params else '')
        data = json.dumps(payload,ensure_ascii=False,allow_nan=False).encode() if payload is not None else None
        req = request.Request(url,data=data,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        opener = request.build_opener(request.ProxyHandler({}),_NoRedirect())
        try:
            with opener.open(req,timeout=30) as response:
                body = response.read(MAX_RESPONSE+1)
            if len(body)>MAX_RESPONSE: raise AtlasError('atlas_response_too_large')
            result = json.loads(body)
            if not isinstance(result,dict): raise ValueError()
            return result
        except error.HTTPError as exc:
            try:
                value=json.loads(exc.read(65536));code=value.get('error_code','atlas_http_error')
                if not isinstance(code,str) or not re.fullmatch('[a-z_]+',code): code='atlas_http_error'
                retryable=value.get('retryable') is True
                details={k:v for k,v in value.get('details',{}).items() if k in ('size_bytes','max_bytes','raw_available','result_available') and type(v) in (int,bool)}
            except (ValueError,TypeError,AttributeError): code,retryable,details='atlas_http_error',False,{}
            raise AtlasError(code,status=exc.code,retryable=retryable,details=details) from None
        except (error.URLError, OSError):
            raise AtlasError('atlas_transport_unavailable',retryable=True) from None
        except AtlasError:
            raise
        except (ValueError,TypeError):
            raise AtlasError('atlas_response_invalid') from None

    def identity(self, expected=None):
        info=self.request('GET','/api/info')
        if info.get('contract_version')!=VERSION or not isinstance(info.get('atlas_instance_id'),str):
            raise AtlasError('atlas_contract_unsupported')
        if expected and info['atlas_instance_id']!=expected:
            raise AtlasError('atlas_instance_mismatch')
        if not {'qa_export_v1','page_raw_v1'} <= set(info.get('capabilities',[])):
            raise AtlasError('atlas_capability_unavailable')
        return info

    def source(self, source_id, version):
        import tempfile
        digest=hashlib.sha256();offset=0;expected=None;total=None
        with tempfile.TemporaryFile() as output:
            while True:
                part=self.request('GET','/api/sources/'+parse.quote(source_id,safe='')+'/versions/'+str(version),
                                  params={'offset':offset,'limit':262144})
                try:
                    chunk=base64.b64decode(part['content_base64'],validate=True)
                    if expected is None: expected,total=part['sha256'],part['size']
                    if (part['source_id']!=source_id or part['version']!=version or part['offset']!=offset or part['sha256']!=expected or part['size']!=total or part['next_offset']!=(None if part['eof'] else offset+len(chunk)) or not chunk and not part['eof']):raise ValueError()
                    output.write(chunk);digest.update(chunk);offset+=len(chunk)
                    if offset>total:raise ValueError()
                    if part['eof']:
                        if offset!=total or digest.hexdigest()!=expected:raise ValueError()
                        output.seek(0)
                        return dict(source_id=source_id,version=version,sha256=expected,size_bytes=total),output.read()
                except (KeyError,TypeError,ValueError):raise AtlasError('atlas_source_invalid') from None
