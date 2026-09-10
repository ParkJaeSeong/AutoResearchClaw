"""Trace Takeda-reference target pairs without changing or filtering source data."""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

BASE=Path(__file__).resolve().parent
DATA=BASE/'discovery-runs/restart-02/coordinator-audit'

def main():
    with (DATA/'data_EC.csv').open() as f:
        rows=[dict(row,source_csv_line=i) for i,row in enumerate(csv.DictReader(f),start=2)]
    with (DATA/'sample_detail_EC.csv').open() as f:
        raw={r['Sample ID']:(i,r) for i,r in enumerate(csv.DictReader(f),start=2)}
    pc=[r for r in rows if r['PID']=='P150011' and r['filler']=='CNT']
    target=[r for r in pc if r['rid']=='44100']
    assert len(target)==14 and len({r['id'] for r in target})==7
    grouped=defaultdict(list)
    for row in target:grouped[row['id']].append(row)
    paired=[]
    for sid,rr in sorted(grouped.items()):
        assert len(rr)==2
        line,detail=raw[sid]
        differing=[k for k in rr[0] if k!='source_csv_line' and rr[0][k]!=rr[1][k]]
        assert set(differing)<= {'log10(EC)'}
        values=[float(r['log10(EC)']) for r in rr]
        match=[r['source_csv_line'] for r in rr if math.isclose(float(r['log10(EC)']),float(detail['log10(elecon)']),abs_tol=1e-10)]
        paired.append({'sample_id':sid,'rid':'44100','source_csv_lines':[r['source_csv_line'] for r in rr],
          'detail_csv_line':line,'vol_percent_as_recorded':rr[0]['vol%'],'log10_ec_values':values,
          'absolute_log_difference':abs(values[0]-values[1]),'differing_columns':differing,
          'detail_log_target':detail['log10(elecon)'],'detail_matching_processed_lines':match,
          'detail_condition':detail['[elecon] condition'],'detail_method':detail['[elecon] method'],
          'detail_remark':detail['[elecon] remarks'],'processed_ac':rr[0]['ac'],'processed_impedance':rr[0]['impedance'],
          'status':'unresolved_measurement_identity' if differing else 'identical_rows_unresolved_replication'})
    assert sum(bool(x['differing_columns']) for x in paired)==6
    unaffected=[r for r in pc if r['rid']!='44100']
    result={'source_sha256':{name:hashlib.sha256((DATA/name).read_bytes()).hexdigest() for name in ['data_EC.csv','sample_detail_EC.csv']},
      'paper':{'doi':'10.1016/j.polymer.2011.06.046','rid':'44100','title':'Modeling and characterization of the electrical conductivity of carbon nanotube-based polymer composites',
               'publisher_url':'https://www.sciencedirect.com/science/article/pii/S0032386111005350',
               'access':'publisher search excerpt read; full article and Fig.4 not inspected',
               'excerpt_paraphrase':'The publisher search excerpt describes Fig.4 as AC conductivity versus frequency at several filler fractions and reports testing three specimens per fraction while displaying typical data.',
               'limits':'Neither plotted frequencies nor correspondence of each processed target to a curve, point or specimen are verified.'},
      'pairs':paired,
      'non_destructive_hold_manifest':{'scope':'entire rid44100 for any prospective predictive evaluation until event identity is reconstructed',
         'csv_lines':[r['source_csv_line'] for r in target],'rows':len(target),'unique_samples':len(grouped),
         'remaining_pc_rows_if_held':len(unaffected),'remaining_pc_sample_ids':len({r['id'] for r in unaffected}),
         'remaining_pc_rids':len({r['rid'] for r in unaffected}),'remaining_pc_expts':len({r['expt'] for r in unaffected}),
         'applied_to_source_data':False,'remaining_data_validated':False},
      'decisions':[
        'Do not infer absence of AC measurements from ac=0: detailed records explicitly describe AC measurements for these rows.',
        'Do not average, delete, select the matching target or assign frequencies by magnitude.',
        'Missing frequency is a plausible explanation candidate, not a demonstrated cause of the target differences.',
        'A shared sample ID does not identify a unique measurement event; the CSV does not identify three independent replicate measurements per fraction.',
        'Full figure or author measurement extraction lineage is required before releasing the held records.'],
      'm1_complete':False,'native_issues_resolved':False}
    (BASE/'target-pair-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result['non_destructive_hold_manifest'],ensure_ascii=False))

if __name__=='__main__':main()
