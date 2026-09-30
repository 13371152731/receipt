"""Conservative OCR-to-fields parsing. Never fill from visual ground truth."""
import copy
import re
from datetime import date

FIELD_DEFS = [
    ('person_name', '姓名'), ('certificate_no', '证书编号'),
    ('certificate_name', '认证名称'), ('category', '作业类别'),
    ('operation', '准操项目'), ('direction', '认证方向'),
    ('initial_issue_date', '初领日期（业务开始日期）'),
    ('valid_from', '有效期限起始日'), ('valid_to', '有效期结束'),
    ('review_date', '复审信息'), ('issuer', '签发机关'),
]
LABELS = dict(FIELD_DEFS)
TEMPLATES = {
    'electrical': {'name':'电工作业证', 'applicable':['person_name','certificate_no','category','operation','initial_issue_date','valid_from','valid_to','review_date','issuer'], 'required':['person_name','certificate_no','category','operation','initial_issue_date','valid_to','review_date']},
    'hcip': {'name':'HCIP 认证证书','applicable':['person_name','certificate_no','certificate_name','direction','valid_to'], 'required':['person_name','certificate_no','certificate_name','direction','valid_to']},
    'unknown': {'name':'待确认类型','applicable':[k for k,_ in FIELD_DEFS], 'required':['person_name','certificate_no','valid_to']},
}

def compact(text):
    return re.sub(r'\s+', '', str(text)).replace('：', ':')

def elements(raw):
    items=[]
    for i,text in enumerate(raw.get('rec_texts', [])):
        poly=raw.get('rec_polys', [])[i]
        xs=[float(p[0]) for p in poly]; ys=[float(p[1]) for p in poly]
        box=[min(xs),min(ys),max(xs),max(ys)]
        items.append({'text':text, 'clean':compact(text), 'confidence':float(raw['rec_scores'][i]), 'box':box, 'index':i})
    return items

def blank():
    return {'value':'','confidence':None,'evidence':[]}

def value_from(value, parts):
    return {'value':value, 'confidence':min((p['confidence'] for p in parts),default=None),
            'evidence':[{'index':p['index'],'text':p['text'],'box':p['box']} for p in parts]}

def labeled(items, labels, accept=lambda text: bool(text)):
    """Match a label plus same-line value or nearby value in its column."""
    for item in items:
        for label in labels:
            match=re.match(r'^'+re.escape(label)+r':?(.*)$',item['clean'])
            if not match: continue
            inline=match.group(1).strip(':')
            if inline and accept(inline): return value_from(inline,[item])
            x1,y1,x2,y2=item['box']; height=max(10,y2-y1)
            choices=[]
            for other in items:
                if other is item or not accept(other['clean']): continue
                a,b,c,d=other['box']; oh=max(10,d-b)
                gap=b-y2
                same_line=abs((b+d-y1-y2)/2)<max(height,oh)*.6 and a>=x2-8 and a-x2<height*6
                # Perspective/large glyph boxes often overlap the label box.
                below=-height*.9 <= gap <= height*2.3 and (b+d-y1-y2)/2>height*.3 and abs(a-x1)<max(35,height*1.8)
                if same_line or below:
                    distance=abs((b+d-y1-y2)/2)+abs(a-x1)*.25
                    choices.append((distance,other))
            if choices:
                other=min(choices,key=lambda x:x[0])[1]
                return value_from(other['clean'],[item,other])
    return blank()

def dates(text):
    # A missing separator is left unresolved instead of silently repaired.
    return re.findall(r'(?<!\d)((?:19|20)\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})(?!\d)',text)

def normalized_date(parts):
    try: return date(*map(int,parts)).isoformat()
    except ValueError: return '-'.join(parts)

def extract(raw):
    items=elements(raw); joined=' '.join(i['clean'] for i in items)
    typ='unknown'
    if 'Huawei' in joined and re.search('HCIP', joined,re.I): typ='hcip'
    elif '电工作业' in joined or (re.search(r'T\d{18}', joined) and ('初领日期' in joined or '特种作业' in joined)): typ='electrical'
    f={key:blank() for key,_ in FIELD_DEFS}
    notes=[]; review_kind='unknown'
    chinese_name=lambda s:bool(re.fullmatch(r'[\u4e00-\u9fff·]{2,6}',s)) and not any(w in s for w in ['作业','日期','机关','证书','姓名','类别','项目','有效','性别','签发','培训'])
    if typ!='hcip':
        f['person_name']=labeled(items,['姓名','名','姓'],chinese_name)
        for item in items:
            m=re.search(r'T\d{16,20}(?!\d)',item['clean'])
            if m:
                f['certificate_no']=value_from(m.group(),[item]); break
        f['category']=labeled(items,['作业类别'],lambda s: s.endswith('作业') and len(s)<16)
        f['operation']=labeled(items,['准操项目','操作项目'],lambda s:s.endswith('作业') and len(s)<20)
        # Use the printed label and geometry, not a whitelist of government names.
        f['issuer']=labeled(items,['签发机关','发证机关','发证机构'],lambda s:bool(re.fullmatch(r'[\u4e00-\u9fffA-Za-z（）()·]{4,50}',s)) and not any(w in s for w in ['日期','作业','姓名','性别','有效期','证书编号','证号','准操项目','操作项目','签发机关','发证机关','发证机构','特种作业']))
        initial=labeled(items,['初领日期'],lambda s:bool(dates(s)))
        if initial['value']:
            initial['value']=normalized_date(dates(initial['value'])[0])
            f['initial_issue_date']=initial
        period=labeled(items,['有效期限','有效期'],lambda s:bool(dates(s)))
        if period['value']:
            txt=period['value']; parts=re.split(r'至|到|~|～',txt,maxsplit=1)
            if len(parts)==2:
                for key,txtpart in [('valid_from',parts[0]),('valid_to',parts[1])]:
                    found=dates(txtpart)
                    if found: f[key]={**copy.deepcopy(period),'value':normalized_date(found[-1 if key=='valid_to' else 0])}
            else:
                notes.append('有效期限没有明确起止分隔，请核对原图')
        rv=labeled(items,['应复审日期','复审日期','审日期'],lambda s:bool(re.search(r'(?:19|20)\d{2}[.\-/年]\d',s)))
        if rv['value']:
            found=dates(rv['value'])
            if found: rv['value']=normalized_date(found[0])
            else:
                m=re.search(r'((?:19|20)\d{2})[.\-/年](\d{1,2})(?!\d)',rv['value'])
                if m: rv['value']=f'{int(m[1]):04}-{int(m[2]):02}'
            f['review_date']=rv
            if any('应复审日期' in compact(x['text']) for x in rv['evidence']): review_kind='due'
            else: review_kind='unspecified'
    else:
        for item in items:
            m=re.search(r'CertificateNo\.?[:：]?(\w[\w-]{6,40})',item['clean'],re.I)
            if m: f['certificate_no']=value_from(m[1],[item])
            if item['clean'].upper()=='HCIP': f['certificate_name']=value_from('HCIP',[item])
            if 'FacilityDeployment' in item['clean']:
                f['direction']=value_from(item['text'],[item])
        english_name=lambda s:bool(re.fullmatch(r'[A-Za-z][A-Za-z .\-]{2,50}',s)) and not any(w in compact(s).lower() for w in ['huawei','certif','valid','center','deployment','through','office','technolog','requirements','ceo','hcip','has','copy'])
        title=next((i for i in items if 'HuaweiCertification' in i['clean']),None)
        if title:
            candidates=[i for i in items if english_name(i['text']) and i['box'][1]>title['box'][3] and i['box'][1]-title['box'][3]<300]
            if candidates:
                i=min(candidates,key=lambda x:x['box'][1]); f['person_name']=value_from(i['text'],[i])
        months={m.lower():n for n,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
        for item in items:
            m=re.search(r'ValidThrough([A-Za-z]+)(\d{1,2}),?((?:19|20)\d{2})',item['clean'],re.I)
            if m and m[1].lower() in months:
                f['valid_to']=value_from(normalized_date([m[3],str(months[m[1].lower()]),m[2]]),[item])
    return {'type':typ,'fields':f,'notes':notes,'review_kind':review_kind}

def evaluate(record, templates=None, today=None, warning_days=10):
    templates=templates or TEMPLATES; today=today or date.today()
    parsed=record.get('parsed') or {'type':'unknown','fields':{},'notes':[],'review_kind':'unknown'}
    typ=record.get('type_override') or parsed['type']
    template=templates[typ]
    corrections=record.get('corrections',{})
    confirmed=set(record.get('confirmed',[]))
    fields={}; missing=[]; review=[]; errors=[]
    for key,label in FIELD_DEFS:
        orig=parsed['fields'].get(key,blank())
        field={**copy.deepcopy(orig),'raw_value':orig['value'],'label':label,'required':key in template['required'],'applicable':key in template['applicable'],'source':'ocr','issues':[]}
        if key in record.get('region_overrides',{}):
            field.update(copy.deepcopy(record['region_overrides'][key]))
            field['source']='region_ocr'
        if key in corrections:
            field['value']=corrections[key]; field['source']='manual'
        v=field['value']; issues=field['issues']; invalid=False
        if not field['applicable']:
            field['state']='na'; fields[key]=field; continue
        if not v:
            field['state']='missing' if field['required'] else 'empty'
            if field['required']: missing.append(key)
            fields[key]=field; continue
        if field['source'] in ['ocr','region_ocr'] and field['confidence'] is not None and field['confidence']<.90 and key not in confirmed:
            issues.append('识别置信度偏低，请核对原图')
        if key in ['initial_issue_date','valid_from','valid_to','review_date']:
            try:
                if key=='review_date' and re.fullmatch(r'\d{4}-\d{2}',v):
                    date.fromisoformat(v+'-01')
                    if key not in confirmed: issues.append('原文仅到年月，需核对日期精度')
                else:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v): raise ValueError()
                    date.fromisoformat(v)
            except ValueError:
                issues.append('日期格式或日期值无效'); invalid=True
        if key=='certificate_no' and typ=='electrical' and not re.fullmatch(r'T\d{18}',v):
            issues.append('证书编号格式待核对')
        if key=='review_date' and parsed.get('review_kind')!='due' and key not in confirmed:
            issues.append('未明确标为应复审截止日，请核对其含义')
        field['state']='review' if issues else 'extracted'
        if issues: review.append(key)
        if invalid: errors.append(key)
        fields[key]=field
    start,end=fields['valid_from'],fields['valid_to']
    if start['applicable'] and end['applicable'] and re.fullmatch(r'\d{4}-\d{2}-\d{2}',start['value']) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',end['value']) and start['value']>end['value']:
        end['state']='review'; end['issues'].append('有效期结束早于开始'); errors.append('valid_to'); review.append('valid_to')
    initial=fields['initial_issue_date']
    if initial['applicable'] and initial['state']=='extracted' and end['state']=='extracted' and initial['value']>end['value']:
        initial['state']='review';initial['issues'].append('初领日期晚于有效期结束');errors.append('initial_issue_date');review.append('initial_issue_date')
    extra=[]
    if typ=='unknown': extra.append('请选择证书类型')
    notes=parsed.get('notes',[]) if not {'valid_from','valid_to'}.issubset(set(corrections)|confirmed|set(record.get('region_overrides',{}))) else []
    extra.extend(notes)
    status='missing' if missing else ('review' if review or extra else ('approved' if record.get('reviewed_at') else 'ready'))
    risk={'kind':'unknown','label':'期限待核实'}
    if end['state']=='extracted':
        try:
            days=(date.fromisoformat(end['value'])-today).days
            if days<0: risk={'kind':'expired','label':'已过期','days':days}
            elif days<=warning_days: risk={'kind':'expiring','label':f'{days} 天后到期','days':days}
            else: risk={'kind':'within','label':'有效期内','days':days}
        except ValueError: pass
    review_info=review_details(record)
    review_risk={'kind':'na','label':'不适用'}
    if typ=='electrical':
        due=review_info['next_due_date']
        review_risk={'kind':'unknown','label':'复审情况待核实'}
        if due:
            days=(date.fromisoformat(due)-today).days
            review_risk={'kind':'review_due' if days<0 else 'expiring' if days<=warning_days else 'within',
                         'label':'应复审日期已过，需核实' if days<0 else f'距应复审还有 {days} 天' if days<=warning_days else '未到应复审日期','days':days}
        if review_info['proof_status']=='pending':
            review_risk={'kind':'unknown','label':'复审证明待补充'}
            if due and due<today.isoformat():review_risk['label']='应复审日期已过，证明待补充'
    risks=[risk]+([review_risk] if typ=='electrical' else [])
    return {'type':typ,'type_label':template['name'],'fields':fields,'missing':missing,'needs_review':sorted(set(review)),'errors':sorted(set(errors)),'notes':extra,'status':status,'risk':risk,'risks':risks,'review_risk':review_risk,'review_info':review_info,'required_count':len(template['required']),'completed_required':len(template['required'])-len(missing)}


def review_details(record):
    info={'last_review_date':'','next_due_date':'','proof_status':'unknown','proof_note':''}
    parsed=record.get('parsed') or {}
    # Explicit due-date labels may be reused; ambiguous legacy dates remain untouched.
    if parsed.get('review_kind')=='due' and 'review_date' not in record.get('corrections',{}) and 'review_date' not in record.get('region_overrides',{}):
        value=parsed.get('fields',{}).get('review_date',{}).get('value','')
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
            try:date.fromisoformat(value);info['next_due_date']=value
            except ValueError:pass
    info.update(record.get('review_details',{}))
    return info
