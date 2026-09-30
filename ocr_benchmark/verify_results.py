import json
from pathlib import Path
import statistics
import re

root=Path(__file__).resolve().parent
expected=['20250318','20190318','20250718','20250318','20190318','20270131','may252026','20291205','20290216']
audit={}
for profile in ['gpu_full','gpu_standard','gpu_960']:
    rows=json.loads((root/profile/'measurements.json').read_text(encoding='utf-8'))
    summary=json.loads((root/profile/'summary.json').read_text(encoding='utf-8'))
    raw=json.loads((root/profile/'ocr_results.json').read_text(encoding='utf-8'))
    assert len(rows)==27
    assert len({(r['round'],r['id']) for r in rows})==27
    assert abs(statistics.mean(r['ocr_s'] for r in rows)-summary['mean_s'])<1e-10
    for key in summary['by_image']:
        assert len(summary['by_image'][key]['values_s'])==3
    matches=[]
    for i,target in enumerate(expected):
        key=f'T{i+1:02}'
        text=''.join(t for result in raw[key] for t in result['rec_texts'])
        normalized=re.sub('[^a-z0-9]','',text.lower())
        if target in normalized: matches.append(key)
    audit[profile]={'count':27,'mean_s':summary['mean_s'],'expiry_text_matches':matches,'expiry_text_match_count':len(matches)}
assert [audit[p]['expiry_text_match_count'] for p in audit]==[5,7,7]
(root/'verification.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
cpu_meta=root/'cpu_standard'/'completion_status.json'
cpu_meta.write_text(json.dumps({'status':'stopped_incomplete','completed_first_image_seconds':19.751333899970632,'completed_T01_warmup_seconds':18.56117910001194,'aggregate_metrics_available':False,'reason':'Only one sample completed; later image did not return promptly. No nine-image CPU results are claimed.'},indent=2),encoding='utf-8')
print(json.dumps(audit,ensure_ascii=False,indent=2))
