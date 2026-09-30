"""Region candidate parsing; only explicit user acceptance writes field values."""
import math
import re
from cert_demo.extraction import compact, dates, normalized_date

def validate_box(box,width,height):
    if not isinstance(box,list) or len(box)!=4 or any(type(n) not in (int,float) or not math.isfinite(n) for n in box):
        raise ValueError('框选坐标无效')
    x1,y1,x2,y2=[round(n) for n in box]
    if not (0<=x1<x2<=width and 0<=y1<y2<=height): raise ValueError('框选区域超出图片范围')
    if x2-x1<8 or y2-y1<8: raise ValueError('框选区域太小，请重新框选')
    if (x2-x1)*(y2-y1)>6_000_000: raise ValueError('区域过大，请只框选需要识别的文字')
    return [x1,y1,x2,y2]

def candidate_values(target,text):
    s=compact(text)
    if target in ['initial_issue_date','valid_from','valid_to','review_date']:
        found=dates(s)
        if target in ['valid_from','valid_to'] and re.search(r'至|到|~|～',s):
            a,b=re.split(r'至|到|~|～',s,maxsplit=1)
            result={}
            if dates(a): result['valid_from']=normalized_date(dates(a)[0])
            if dates(b): result['valid_to']=normalized_date(dates(b)[0])
            return result
        if len(found)==1: return {target:normalized_date(found[0])}
        if target=='review_date' and not found:
            m=re.search(r'((?:19|20)\d{2})[.\-/年](\d{1,2})(?!\d)',s)
            if m:return {target:f'{int(m[1]):04}-{int(m[2]):02}'}
        return {}  # Multiple unrelated dates require a tighter region.
    labels={'person_name':['姓名','姓','名'],'certificate_no':['CertificateNo.','CertificateNo','证书编号','证号','证号码'],
            'category':['作业类别'],'operation':['准操项目','操作项目'],'issuer':['签发机关'],
            'certificate_name':['认证名称'],'direction':['认证方向']}
    value=text.strip()
    for label in labels.get(target,[]):
        if s.startswith(label):
            value=s[len(label):].lstrip(':');break
    if target in ['person_name','category','operation','issuer','certificate_no'] and re.search(r'[\u4e00-\u9fff]',value):
        value=compact(value)
    if target=='certificate_no':value=compact(value)
    if target=='person_name':
        if re.search(r'[\u4e00-\u9fff]',value):
            if not re.fullmatch(r'[\u4e00-\u9fff·]{2,6}',value) or any(w in value for w in ['作业','日期','类别','项目','机关','性别','有效','证书']):return {}
        elif not re.fullmatch(r'[A-Za-z][A-Za-z.\-]*(?:\s+[A-Za-z][A-Za-z.\-]*){1,4}',value):return {}
    if target in ['category','operation'] and (not value.endswith('作业') or len(value)>20):return {}
    return {target:value[:200]} if value else {}
