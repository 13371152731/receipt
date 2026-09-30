from pathlib import Path
import argparse
import hashlib
import json
import shutil

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=root/'models'/'official_models')
parser.add_argument('--target', type=Path, default=root/'models'/'benchmark_models')
args = parser.parse_args()
source = args.source.resolve()
target = args.target.resolve()
models = ['PP-LCNet_x1_0_doc_ori','PP-LCNet_x1_0_textline_ori','PP-OCRv5_server_det','PP-OCRv5_server_rec','UVDoc']
records = []
for name in models:
    dest = target / name
    dest.mkdir(parents=True, exist_ok=True)
    for filename in ['inference.json','inference.yml','inference.pdiparams']:
        src = source / name / filename
        recovered = False
        if not src.exists() and filename == 'inference.pdiparams':
            src = source / name / '._tmp' / filename
            recovered = True
        shutil.copy2(src, dest / filename)
        records.append({'model':name,'filename':filename,'source':str(src),'recovered_from_temp':recovered,'bytes':src.stat().st_size,'sha256':hashlib.sha256((dest / filename).read_bytes()).hexdigest()})
(target / 'manifest.json').write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(records,ensure_ascii=False,indent=2))
