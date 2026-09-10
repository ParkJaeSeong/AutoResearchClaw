"""Read-only EC condition/lineage audit; aggregate output, no author code execution."""
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

BASE=Path(__file__).resolve().parent
DATA=BASE/'discovery-runs/restart-02/coordinator-audit'
OUT=BASE/'condition-lineage-audit.json'
COLS=['vol%','temperature','log10(thickness)','ac','dc','four-probe','two-probe','impedance']
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read(name):
    with (DATA/name).open() as f:
        return list(csv.DictReader(f))


def same(a,b):
    try:
        return math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-10)
    except (TypeError,ValueError):
        return a==b


def workbook_check():
    result={}
    with ZipFile(DATA/'ci3c01894_si_002.xlsx') as z:
        strings=[''.join(t.text or '' for t in si.iter('{'+NS['m']+'}t')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        for name,sheet in [('TC',1),('EC',2)]:
            root=ET.fromstring(z.read(f'xl/worksheets/sheet{sheet}.xml'))
            rows=[]
            for row in root.findall('.//m:sheetData/m:row',NS):
                cells={}
                for c in row:
                    v=c.find('m:v',NS)
                    if v is not None:
                        key=''.join(x for x in c.attrib['r'] if x.isalpha())
                        cells[key]=strings[int(v.text)] if c.attrib.get('t')=='s' else v.text
                rows.append(cells)
            headers=rows[0]
            records=[{header:row.get(col,'') for col,header in headers.items()} for row in rows[1:]]
            csv_rows=read(f'data_{name}.csv')
            assert len(records)==len(csv_rows) and set(headers.values())==set(csv_rows[0])
            mismatches=[{'row':i+2,'field':k} for i,(a,b) in enumerate(zip(records,csv_rows)) for k in a if not same(a[k],b[k])]
            result[name]={'rows':len(records),'columns':len(headers),'mismatched_cells':len(mismatches),'examples':mismatches[:10]}
    return result


def summarize(rows,raw):
    byid=defaultdict(list); byrid=defaultdict(list)
    for r in rows:
        byid[r['id']].append(r);byrid[r['rid']].append(r)
    repeated={key:rr for key,rr in byid.items() if len(rr)>1}
    features={}
    for c in COLS:
        values=Counter(r[c] for r in rows)
        support=sum(r[c] in {x[c] for x in rows if x['rid']!=r['rid']} for r in rows)
        features[c]={'distinct_values':len(values),'within_rid_varying':sum(len({r[c] for r in rr})>1 for rr in byrid.values()),
          'values':dict(values) if len(values)<25 else None,'rows_with_same_value_in_other_rid':support}
    fields={}
    for rawcol,proc in [('[elecon] temp','temperature'),('log10(thickness)','log10(thickness)'),('[elecon] method',None),('log10(elecon)','log10(EC)')]:
        blank=[r for r in rows if not raw[r['id']][rawcol].strip()]
        present=[r for r in rows if raw[r['id']][rawcol].strip()]
        fields[rawcol]={'blank_linked_rows':len(blank),'blank_unique_sample_ids':len({r['id'] for r in blank}),
          'present_linked_rows':len(present),'processed_values_when_raw_blank':dict(Counter(r[proc] for r in blank)) if proc else None,
          'different_from_processed_among_present':sum(not same(r[proc],raw[r['id']][rawcol]) for r in present) if proc else None}
    allkeys=list(rows[0]); predictable=[c for c in allkeys if c not in ('log10(EC)','id','rid','expt','html') and not c.startswith('expt_')]
    duplicate_full=len(rows)-len({tuple(r[k] for k in allkeys) for r in rows})
    collisions=sum(len({tuple(r[k] for k in predictable) for r in rr})==1 and len({r['log10(EC)'] for r in rr})>1 for rr in repeated.values())
    # Marginal overlap is only a support diagnostic, not identification or full joint overlap.
    volume_in_other_range=0
    for r in rows:
        other=[float(x['vol%']) for x in rows if x['rid']!=r['rid']]
        volume_in_other_range+=min(other)<=float(r['vol%'])<=max(other)
    return {'rows':len(rows),'unique_samples':len(byid),'rids':len(byrid),'expts':len({r['expt'] for r in rows}),
      'pid_matches':sum(r['PID']==raw[r['id']]['PID'] for r in rows),
      'rid_matches_sample_prefix':sum(r['rid']==r['id'].split('-')[0] for r in rows),
      'repeated_sample_ids':len(repeated),'extra_rows_after_unique_samples':len(rows)-len(byid),
      'exact_duplicate_excess_rows':duplicate_full,
      'repeated_ids_identical_model_inputs_different_targets':collisions,
      'columns_varying_within_repeated_sample':dict(Counter(c for rr in repeated.values() for c in allkeys if len({r[c] for r in rr})>1)),
      'features':features,'raw_linked_fields':fields,'rows_volume_in_other_rid_range':volume_in_other_range}


def main():
    rows=read('data_EC.csv'); detail=read('sample_detail_EC.csv')
    raw={r['Sample ID']:r for r in detail}
    assert len(raw)==len(detail) and all(r['id'] in raw for r in rows)
    subsets={'all_EC':rows,'PC_CNT':[r for r in rows if r['PID']=='P150011' and r['filler']=='CNT'],
             'PP_CNT':[r for r in rows if r['PID']=='P010002' and r['filler']=='CNT']}
    result={'provenance':{'csv':'https://github.com/shimakawa-hvg/expt-group-partitioning',
      'xlsx':'https://acs.figshare.com/articles/dataset/25657025','xlsx_md5':hashlib.md5((DATA/'ci3c01894_si_002.xlsx').read_bytes()).hexdigest(),
      'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [DATA/'data_EC.csv',DATA/'sample_detail_EC.csv',DATA/'ci3c01894_si_002.xlsx']},
      'join':'data_EC.id == sample_detail_EC.Sample ID; exact strings; many processed rows to one detail row',
      'numeric_tolerance':'relative/absolute 1e-10; strings exact',
      'limits':'sample_detail is an author-distributed detail table, not the complete original measurement record; matching does not explain repeated measurement lineage or establish units/imputation rules'},
      'detail_rows':len(detail),'all_processed_rows_matched':len(rows),'detail_samples_unrepresented':len(set(raw)-{r['id'] for r in rows}),
      'subsets':{name:summarize(rr,raw) for name,rr in subsets.items()},'xlsx_csv_comparison':workbook_check()}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:{f:v[f] for f in ['rows','unique_samples','rids','repeated_sample_ids','exact_duplicate_excess_rows','repeated_ids_identical_model_inputs_different_targets']} for k,v in result['subsets'].items()}))
    print('XLSX',result['xlsx_csv_comparison'])

if __name__=='__main__':main()
