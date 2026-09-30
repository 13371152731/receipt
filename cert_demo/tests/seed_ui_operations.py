"""Prepare an isolated local UI fixture; does not use the live database."""
import copy
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
from PIL import Image

root=Path(__file__).resolve().parents[1]
data=root/'data'/'ui-operations-qa'
if (data/'demo.sqlite3').exists():
    raise SystemExit('UI fixture already exists; reuse it without overwriting')
os.environ['CERT_DEMO_DATA']=str(data)
sys.path.insert(0,str(root.parent))
from cert_demo import app
from cert_demo.extraction import extract
app.initialize()
image=data/'images'/'ui-fixture.png'
Image.new('RGB',(800,500),'#edf5f5').save(image)
raw=json.loads((root.parent/'ocr_benchmark/gpu_standard/ocr_results.json').read_text(encoding='utf-8'))['T07'][0]
for rid,delta in [('qa-old',7),('qa-new',700)]:
    record=dict(id=rid,created_at=app.now(),filename='界面测试_'+rid+'.png',sample=None,sha256=rid,image_path=str(image),display_path=None,
                job_status='done',parsed=extract(raw),raw=raw,corrections={'person_name':'UI Test Person','valid_to':(date.today()+timedelta(days=delta)).isoformat()},
                confirmed=[],type_override=None,ocr_s=.3,version=1,reviewed_at=None,reviewer='',note='独立界面测试数据')
    app.write(record)
print(data)
