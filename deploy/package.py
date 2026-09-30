"""Build a private deployment archive with SQLite backup and portable image paths."""
import json
from pathlib import Path, PureWindowsPath
import sqlite3
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
REMOTE='/home/learned/invoice-system'
OUTPUT=ROOT/'outputs'/'deployment-192.168.3.117.tar.gz'
OUTPUT.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    db=Path(temp)/'invoices.sqlite3'
    with sqlite3.connect(ROOT/'invoice_demo/data/invoices.sqlite3') as source, sqlite3.connect(db) as dest:
        source.backup(dest)
        dest.execute('DELETE FROM sessions')
        count=0
        for rid,payload in dest.execute('SELECT id,payload FROM invoices').fetchall():
            r=json.loads(payload)
            for key in ('image_path','display_path'):
                if r.get(key):
                    name=PureWindowsPath(r[key]).name
                    if not (ROOT/'invoice_demo/data/images'/name).is_file():
                        raise RuntimeError(f'Missing image for {rid}: {name}')
                    r[key]=f'{REMOTE}/data/invoices/images/{name}'
            dest.execute('UPDATE invoices SET payload=? WHERE id=?',(json.dumps(r,ensure_ascii=False),rid))
            count+=1
    source.close()
    dest.close()
    with tarfile.open(OUTPUT,'w:gz') as archive:
        for folder in ('cert_demo','invoice_demo','deploy'):
            for file in (ROOT/folder).rglob('*'):
                rel=file.relative_to(ROOT)
                if not file.is_file() or any(x in rel.parts for x in ('data','__pycache__','launch_check','validation')):continue
                if file.suffix not in ('.py','.html','.js','.css','.txt','.md','.service','.conf'):continue
                archive.add(file,arcname=str(rel).replace('\\','/'))
        metadata=ROOT/'ocr_benchmark/gpu_standard/metadata.json'
        archive.add(metadata,arcname='ocr_benchmark/gpu_standard/metadata.json')
        cfg=json.loads(metadata.read_text(encoding='utf-8'))['config']
        for key,value in cfg.items():
            if key.endswith('_model_dir'):
                archive.add(value,arcname='models/'+PureWindowsPath(value).name)
        archive.add(db,arcname='data/invoices/invoices.sqlite3')
        archive.add(ROOT/'invoice_demo/data/images',arcname='data/invoices/images')
    print(json.dumps({'archive':str(OUTPUT),'bytes':OUTPUT.stat().st_size,'records':count}))
