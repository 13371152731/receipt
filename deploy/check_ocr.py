"""Read-only OCR smoke check against migrated images; no business data edits."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import tempfile
from typing import Any, cast

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ['CERT_OCR_DEVICE']='cpu'
os.environ['CERT_OCR_MODEL_ROOT']=str(root/'models'/'official_models')
os.environ['CERT_OCR_CPU_THREADS']='4'
with tempfile.TemporaryDirectory(prefix='invoice-ocr-check-') as scratch:
    os.environ['CERT_DEMO_DATA']=scratch
    from cert_demo import app
    from invoice_demo.extraction import extract, evaluate
    db_path=root/'data/invoices/invoices.sqlite3'
    if not db_path.exists():
        db_path=root/'invoice_demo/data/invoices.sqlite3'
    with sqlite3.connect(db_path) as c:
        # noinspection SqlNoDataSourceInspection
        records=[json.loads(x[0]) for x in c.execute('SELECT payload FROM invoices')]
    selected=[]
    for kind in ('ordinary','special','train'):
        candidates=[r for r in records if (r.get('parsed') or {}).get('kind')==kind and not r.get('deleted_at')]
        if candidates:selected.append(candidates[0])
    if not selected:selected=records[:2]
    started=time.perf_counter()
    ocr=app.engine()
    print(json.dumps({'model_load_s':round(time.perf_counter()-started,3),'engine':app.engine_state()},ensure_ascii=False),flush=True)
    import cv2
    results=[]
    for r in selected:
        image_path=Path(r['image_path'])
        if not image_path.is_file():
            image_path=root/'invoice_demo/data/images'/image_path.name
        if not image_path.is_file():
            raise FileNotFoundError(f'找不到发票图片: {r["image_path"]}')
        pixels=cv2.imread(str(image_path))
        if pixels is None:
            raise RuntimeError(f'无法读取发票图片: {image_path}')
        for run in range(2):
            started=time.perf_counter()
            result=list(ocr.predict(pixels))[0]
            elapsed=time.perf_counter()-started
            raw={k:app.native(result[k]) for k in ('rec_texts','rec_scores','rec_polys')}
            raw['pdf_title']=r.get('pdf_title','')
            aligned=cast(Any,result.get('doc_preprocessor_res',{}).get('output_img'))
            if aligned is None:aligned=pixels
            if aligned is None or not hasattr(aligned, 'shape'):
                raise RuntimeError(f'OCR 未返回有效图像: {image_path}')
            h,w=aligned.shape[:2]
            parsed=extract(raw,w,h)
            checked=evaluate(dict(parsed=parsed,corrections={},reviewed_at=None))
            row={'record_id':r['id'],'run':run+1,'ocr_s':round(elapsed,3),'kind':parsed['kind'],'values':checked['values'],'missing':checked['missing'],'errors':checked['errors']}
            results.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    print('OCR_CHECK_COMPLETE',flush=True)
