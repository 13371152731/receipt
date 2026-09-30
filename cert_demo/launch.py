"""Start the local demo without changing Windows script execution policy."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    project=root.parent
    os.environ.setdefault('CERT_OCR_MODEL_ROOT',str(project/'models'/'official_models'))
    os.environ.setdefault('CERT_OCR_DEVICE','cpu')
    os.environ.setdefault('CERT_OCR_CPU_THREADS','8')
    os.environ.setdefault('PADDLE_PDX_CACHE_HOME',str(project/'models'/'paddlex-cache'))
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
    os.environ.setdefault('DISABLE_MODEL_SOURCE_CHECK','True')
    url=f'http://127.0.0.1:{args.port}'
    def ready():
        try:
            with urllib.request.urlopen(url+'/api/state',timeout=1) as r:
                data=json.load(r)
            return 'records' in data and 'templates' in data.get('settings',{})
        except (OSError,ValueError): return False
    if not ready():
        logs=Path(os.environ.get('CERT_DEMO_DATA',str(root/'data')));logs.mkdir(parents=True,exist_ok=True)
        python=os.environ.get('CERT_DEMO_PYTHON',sys.executable)
        with (logs/'server.log').open('ab') as out,(logs/'server-error.log').open('ab') as err:
            child=subprocess.Popen([python,'-X','utf8','-B',str(root/'app.py'),'--port',str(args.port)],cwd=root,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        (logs/'server.pid').write_text(str(child.pid),encoding='ascii')
        for _ in range(40):
            if ready(): break
            if child.poll() is not None: raise RuntimeError('服务启动失败，请查看 data/server-error.log')
            time.sleep(.5)
        else: raise RuntimeError('服务启动超时，请查看 data/server-error.log')
    print('证书审核 Demo 已就绪：'+url)
    if not args.no_browser: webbrowser.open(url)

if __name__=='__main__': main()
