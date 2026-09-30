"""Exercise the live local OCR service and preserve its actual responses."""
import csv
import json
from pathlib import Path
import sys
import time
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cert_demo.extraction import extract,evaluate

OUT=ROOT/'outputs'/'真人风格证书测试样图'/'实测结果'
OUT.mkdir(exist_ok=True)
session=requests.Session();session.headers['X-Demo-Request']='1'
base='http://127.0.0.1:8765'
def call(method,path,**kwargs):
    response=session.request(method,base+path,timeout=30,**kwargs)
    response.raise_for_status()
    return response

expected=[
dict(person_name='林晓辰',certificate_no='T000000199103120015',category='电工作业',operation='低压电工作业',initial_issue_date='2020-06-15',valid_from='2024-09-20',valid_to='2030-09-19',review_date='2027-09-19',issuer='示例技能培训中心'),
dict(person_name='陈思远',certificate_no='T000000198305210027',category='电工作业',operation='高压电工作业',initial_issue_date='2018-09-20',valid_from='2020-09-20',valid_to='2026-09-19',review_date='2023-09-19',issuer='示例技能培训中心'),
dict(person_name='周雨晴',certificate_no='T000000199204080036',category='电工作业',operation='低压电工作业',initial_issue_date='2016-03-10',valid_from='2020-09-01',valid_to='2026-08-31',review_date='2023-08',issuer='示例技能培训中心')]
files=sorted((OUT.parent).glob('*.png'))
assert len(files)==3
before=call('GET','/api/state').json()
results=[];rows=[]
for file,truth in zip(files,expected):
    start=time.perf_counter()
    with file.open('rb') as source:
        uploaded=call('POST','/api/upload',files={'file':(file.name,source,'image/png')}).json()
    rid=uploaded['record']['id']
    if uploaded['duplicate']:
        call('POST',f'/api/records/{rid}/retry')
    deadline=time.monotonic()+180
    while True:
        detail=call('GET',f'/api/records/{rid}').json()
        if detail['job_status'] in ['done','error']:break
        if time.monotonic()>deadline:raise TimeoutError('OCR 等待超时')
        time.sleep(.5)
    observed=time.perf_counter()-start
    if detail['job_status']=='error':raise RuntimeError(detail['error'])
    # Grade only this run's raw extraction, not earlier manual corrections.
    assessment=evaluate({'parsed':extract(detail['raw'])},templates=before['settings']['templates'])
    results.append({'file':file.name,'record_id':rid,'ocr_s':detail['ocr_s'],'observed_end_to_end_s':round(observed,3),'expected':truth,'assessment':assessment,'response':detail})
    for key,value in truth.items():
        f=assessment['fields'][key]
        rows.append([file.name,f['label'],value,f['value'],'正确' if f['value']==value else '未提取' if not f['value'] else '错误',f['confidence'],detail['ocr_s']])
    print(json.dumps({'file':file.name,'ocr_s':detail['ocr_s'],'observed_end_to_end_s':round(observed,3),'fields':{k:assessment['fields'][k]['value'] for k in truth},'risks':assessment['risks'],'missing':assessment['missing'],'review':assessment['needs_review']},ensure_ascii=False),flush=True)
after=call('GET','/api/state').json()
(OUT/'实际OCR与字段比对.json').write_text(json.dumps({'engine_before':before['engine'],'engine_after':after['engine'],'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'逐字段对照.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['图片','字段','期望值','实际提取值','结果','置信度','本张OCR秒']);w.writerows(rows)
export=call('POST','/api/export',json={'format':'xlsx','ids':[r['record_id'] for r in results]})
(OUT/'三张证书实测提取.xlsx').write_bytes(export.content)
print('完成：'+str(OUT),flush=True)
