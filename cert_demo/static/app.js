'use strict';
const $=id=>document.getElementById(id);
const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusText={missing:'待补录',review:'待核对',ready:'待审核',approved:'字段已核对',queued:'排队中',running:'识别中',error:'识别失败'};
let personFilter=null;
let selectedRecords=new Map(),batchDeleting=false;
let reviewQueue=[],lastIssueKey=null;
let state={records:[],fields:[],settings:null,engine:{}},filter='all',active=null,ruleDraft=null,ruleType='electrical',originalPreview=false,refreshing=false,toastTimer;
async function api(url,options={}){
  const headers={'X-Demo-Request':'1',...options.headers};
  if(options.body && !(options.body instanceof FormData))headers['Content-Type']='application/json';
  const response=await fetch(url,{...options,headers});
  if(!response.ok){let msg=`请求失败 (${response.status})`;try{const j=await response.json();msg=typeof j.detail==='string'?j.detail:msg;}catch{}throw new Error(msg);}
  return response;
}
function toast(message,error=false){const t=$('toast');t.textContent=message;t.className='toast'+(error?' error':'');t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.hidden=true,4500);}
function recordStatus(r){return r.job_status==='done'?r.status:r.job_status;}
function visibleRecords(){
  const search=$('search').value.trim().toLowerCase(),type=$('typeFilter').value;
  return state.records.filter(r=>{
    const s=recordStatus(r);
    const matches=filter==='all'||(filter==='review'?['review','ready'].includes(s):filter===s);
    const hay=[r.filename,r.sample,...Object.values(r.fields).map(f=>f.value)].join(' ').toLowerCase();
    const rf=$('riskFilter').value;const risks=r.risks||[r.risk];const riskMatch=rf==='all'||(rf==='review'?r.type==='electrical'&&['unknown','review_due'].includes(r.review_risk?.kind):risks.some(x=>x.kind===rf));
    const lifecycle=$('lifecycleFilter').value;
    return (!personFilter||r.person_id===personFilter)&&(lifecycle==='all'||(lifecycle==='historical'?r.historical:!r.historical))&&riskMatch&&matches&&(type==='all'||type===r.type)&&(!search||hay.includes(search));
  }).sort((a,b)=>$('sortOrder').value==='expiry'?(a.fields.valid_to.value||'9999').localeCompare(b.fields.valid_to.value||'9999'):$('sortOrder').value==='name'?(a.fields.person_name.value||'').localeCompare(b.fields.person_name.value||'','zh-CN'):0);
}
function personGroups(records){
  const groups=new Map();
  for(const r of records){
    const name=(r.fields.person_name.value||'').trim();
    const key=r.person_id?`${r.person?.name||name} · 人员 ${r.person_id}`:name||'未识别姓名';
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(r);
  }
  return [...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0],'zh-CN'));
}
function cell(field,cls=''){
  if(!field.applicable)return '<span class="na">不适用</span>';
  if(!field.value)return field.required?'<span class="missing-tag">未识别</span>':'<span class="na">—</span>';
  return `<span class="${cls} ${field.state==='review'?'review-value':''}" title="${escapeHtml(field.issues.join('；'))}">${escapeHtml(field.value)}</span>`;
}
function render(){
  const records=state.records,visible=visibleRecords();
  $('today').textContent=state.today||'';
  const e=state.engine,loading=e.status==='loading';
  const engineLabels={idle:'○ OCR 未启动',loading:'◌ OCR 加载中',ready:'● OCR 已启动',stopping:'◌ OCR 关闭中',error:'○ OCR 异常'};
  $('engineBadge').textContent=engineLabels[e.status]||'○ OCR 状态未知';
  $('engineBadge').className='engine-badge '+(['loading','stopping'].includes(e.status)?'loading':e.status==='error'?'error':'');
  $('engineBadge').title=[e.message,e.device,e.initialization_s!=null?`加载耗时 ${e.initialization_s} 秒`:'',`待处理任务 ${e.pending_tasks||0}`].filter(Boolean).join('；');
  $('startModel').disabled=['loading','ready','stopping'].includes(e.status);
  $('stopModel').disabled=!e.loaded||['loading','stopping'].includes(e.status)||e.pending_tasks>0;
  $('totalStat').textContent=records.length;
  $('missingStat').textContent=records.filter(r=>recordStatus(r)==='missing').length;
  $('reviewStat').textContent=records.filter(r=>['review','ready'].includes(recordStatus(r))).length;
  $('approvedStat').textContent=records.filter(r=>recordStatus(r)==='approved').length;
  const jobs=records.filter(r=>['queued','running'].includes(r.job_status));
  $('queueBar').hidden=!jobs.length;
  $('queueText').textContent=loading?`正在加载本地 OCR 模型，还有 ${jobs.length} 张待处理`:`正在识别证书，还有 ${jobs.length} 张待处理`;
  $('resultCount').textContent=records.length;
  $('visibleCount').textContent=`显示 ${visible.length} 条 / 共 ${records.length} 条记录`;
  $('exportCsv').disabled=!visible.length;$('exportXlsx').disabled=!visible.length;
  const selectable=visible.filter(r=>!['queued','running'].includes(r.job_status));
  const available=new Set(selectable.map(r=>r.id));
  for(const id of selectedRecords.keys())if(!available.has(id))selectedRecords.delete(id);
  const grouped=$('viewMode').value==='people',groups=personGroups(visible);
  const ordered=grouped?groups.flatMap(x=>x[1]):visible;
  const starts=new Map(groups.map(([name,items])=>[items[0].id,{name,count:items.length}]));
  $('groupHint').textContent=grouped?`当前 ${groups.length} 个人员分组。已关联按人员编号分组，未关联仍按姓名展示。`:'全选仅作用于当前筛选结果，切换筛选会取消隐藏条目的勾选。';
  $('clearPersonFilter').hidden=!personFilter;
  $('exportSelected').disabled=!selectedRecords.size;
  $('selectionCount').textContent=`已选 ${selectedRecords.size} 条`;
  $('batchDelete').disabled=!selectedRecords.size||batchDeleting;
  $('clearSelection').disabled=!selectedRecords.size||batchDeleting;
  $('selectAll').disabled=!selectable.length||batchDeleting;
  $('selectAll').checked=!!selectable.length&&selectedRecords.size===selectable.length;
  $('selectAll').indeterminate=selectedRecords.size>0&&selectedRecords.size<selectable.length;
  $('recordBody').innerHTML=ordered.map((r,i)=>{ 
    const f=r.fields,s=recordStatus(r),isDone=r.job_status==='done';
    const op=r.type==='hcip'?f.direction:f.operation;
    const name=isDone?cell(f.person_name):'<span class="na">等待识别</span>';
    const no=f.certificate_no.value;
    const noDisplay=no&&no.length>14?no.slice(0,7)+'···'+no.slice(-5):no;
    const noCell=isDone?(no?`<span class="mono" title="${escapeHtml(no)}">${escapeHtml(noDisplay)}</span>`:cell(f.certificate_no)):'<span class="na">—</span>';
    const group=grouped?starts.get(r.id):null;
    return `${group?`<tr class="person-group"><td colspan="11"><strong>${escapeHtml(group.name)}</strong><span>${group.count} 张证书</span><small>已关联按人员编号 · 未关联按姓名</small></td></tr>`:''}<tr data-record="${r.id}"><td class="selection-col"><input type="checkbox" data-select="${r.id}" aria-label="选择证书：${escapeHtml(f.person_name.value||r.filename)}" ${selectedRecords.has(r.id)?'checked':''} ${['queued','running'].includes(r.job_status)||batchDeleting?'disabled':''}></td><td class="index-col"><span class="record-index">${String(i+1).padStart(2,'0')}</span></td><td><div class="person-line">${name}${r.historical?'<span class="sample-id">历史证书</span>':''}${r.sample?`<span class="sample-id">${escapeHtml(r.sample)}</span>`:''}</div><div class="sub-line" title="${escapeHtml(r.filename)}">${isDone?escapeHtml(r.type_label):escapeHtml(r.filename)}</div><div class="sub-line">${r.person?escapeHtml(r.person.project||'未分配项目')+' · 已关联人员':'未关联人员档案'}</div></td><td>${noCell}</td><td class="field-text">${isDone?cell(op):'<span class="na">—</span>'}</td><td>${isDone?cell(f.initial_issue_date,'date'):'<span class="na">—</span>'}</td><td>${isDone?cell(f.valid_to,'date'):'<span class="na">—</span>'}</td><td>${isDone?`<span class="date">${escapeHtml(r.review_info?.next_due_date||f.review_date.value||'—')}</span><div class="sub-line">${r.review_info?.next_due_date?'下次应复审':'证面复审信息'}</div>`:'<span class="na">—</span>'}</td><td>${isDone?(r.risks||[r.risk]).map(x=>`<span class="risk ${x.kind}">${escapeHtml(x.label)}</span>`).join(''):'<span class="na">等待识别</span>'}</td><td><span class="status ${s}">${statusText[s]}</span><div class="sub-line">${isDone?(r.missing.length?`缺 ${r.missing.length} 项必填`:`${r.completed_required}/${r.required_count} 项必填完整`):escapeHtml(r.error||'本地识别队列')}</div></td><td><button class="table-link" data-open="${r.id}" ${['queued','running'].includes(s)?'disabled':''}>${s==='error'?'查看异常':'核对 →'}</button><button class="table-link" data-links="${r.id}" ${!isDone?'disabled':''}>归属 / 换证</button><button class="table-link delete-link" data-delete="${r.id}" ${['queued','running'].includes(s)?'disabled':''}>删除</button>${r.ocr_s!=null?`<div class="sub-line mono">${r.ocr_s.toFixed(3)} s</div>`:''}</td></tr>`;
  }).join('');
  $('emptyState').hidden=!!visible.length;
  if(!records.length){$('emptyState').querySelector('h3').textContent='从第一张证书开始';$('emptyState').querySelector('p').innerHTML='上传真实证书，或导入已准备好的 9 张样例。<br>系统会调用本地 OCR，并检查每个必填字段。';$('emptySamples').hidden=false;}
  else if(!visible.length){$('emptyState').querySelector('h3').textContent='没有符合筛选条件的记录';$('emptyState').querySelector('p').textContent='可以尝试切换状态、证书类型或搜索关键词。';$('emptySamples').hidden=true;}
}
async function refresh(){if(refreshing)return;refreshing=true;try{const next=await (await api('/api/state')).json();if(JSON.stringify(next)!==JSON.stringify(state)||$('engineBadge').textContent.includes('未连接')){state=next;render();}}catch(e){$('engineBadge').textContent='○ 本地服务未连接';$('engineBadge').title=e.message;}finally{refreshing=false;}}
async function importSamples(){
  $('sampleButton').disabled=true;$('emptySamples').disabled=true;
  try{const r=await(await api('/api/samples',{method:'POST'})).json();toast(r.added?`已添加 ${r.added} 张样例，开始本地识别`:`${r.duplicates} 张样例已存在，可在记录中重新识别`);await refresh();}catch(e){toast(e.message,true);}finally{$('sampleButton').disabled=false;$('emptySamples').disabled=false;}
}
async function uploadFiles(files){
  if(!files.length)return;if(files.length>20){toast('每批最多上传 20 张图片',true);return;}
  $('uploadButton').disabled=true;let added=0,duplicates=0;
  for(const file of files){
    if(file.size>15*1024*1024){toast(`${file.name} 超过 15 MB`,true);continue;}
    try{const form=new FormData();form.append('file',file);const r=await(await api('/api/upload',{method:'POST',body:form})).json();r.duplicate?duplicates++:added++;await refresh();}catch(e){toast(`${file.name}：${e.message}`,true);}
  }
  $('uploadButton').disabled=false;$('fileInput').value='';
  if(added||duplicates)toast(`新增 ${added} 张，跳过 ${duplicates} 张重复图片`);
}
function confirmBatchDeletion(message){
  return new Promise(resolve=>{
    const dialog=$('batchConfirm');$('batchConfirmText').textContent=message;
    const finish=value=>{dialog.close();resolve(value);};
    $('cancelBatch').onclick=()=>finish(false);$('confirmBatch').onclick=()=>finish(true);
    dialog.oncancel=e=>{e.preventDefault();finish(false);};dialog.showModal();
  });
}
async function batchDeleteRecords(){
  if(batchDeleting||!selectedRecords.size)return;
  const items=[...selectedRecords].map(([id,version])=>({id,version}));
  const preview=items.slice(0,8).map(x=>{const r=state.records.find(r=>r.id===x.id);return `${r.fields.person_name.value||'未识别姓名'} · ${r.filename}`;}).join('\n');
  if(!await confirmBatchDeletion(`确认批量删除 ${items.length} 条证书？\n${preview}${items.length>8?'\n……':''}\n删除后退出列表、统计和导出，后台保留原图和审核记录。`))return;
  batchDeleting=true;render();
  try{
    const result=await(await api('/api/records/batch-delete',{method:'POST',body:JSON.stringify({records:items})})).json();
    const ids=new Set(result.ids);state.records=state.records.filter(r=>!ids.has(r.id));selectedRecords.clear();
    if(active&&ids.has(active.id)){$('reviewDialog').close();active=null;}
    toast(`已删除 ${result.deleted} 条证书`);
  }catch(e){selectedRecords.clear();toast(e.message,true);}
  finally{batchDeleting=false;render();await refresh();}
}
async function deleteRecord(id){
  const r=state.records.find(x=>x.id===id);if(!r)return;
  if(!await confirmBatchDeletion(`确认删除这条证书？\n${r.fields.person_name.value||'未识别姓名'} · ${r.filename}\n删除后不再显示在列表、统计或导出中，后台保留原图和审核记录。`))return;
  try{
    await api(`/api/records/${id}`,{method:'DELETE',body:JSON.stringify({version:r.version})});
    state.records=state.records.filter(x=>x.id!==id);render();
    if(active?.id===id){$('reviewDialog').close();active=null;}
    toast('证书已删除');await refresh();
  }catch(e){toast(e.message,true);await refresh();}
}
async function openRecord(id,continueQueue=false){if(!continueQueue)reviewQueue=visibleRecords().filter(r=>r.job_status==='done'&&r.status!=='approved').map(r=>r.id);lastIssueKey=null;try{active=await(await api(`/api/records/${id}`)).json();renderReview();if(!$('reviewDialog').open)$('reviewDialog').showModal();}catch(e){toast(e.message,true);}}
function renderReview(){
  const r=active;originalPreview=false;if(typeof resetRegion==='function')resetRegion();
  $('reviewTitle').textContent=(r.fields.person_name.value||'未识别姓名')+' · 核对证书';
  $('reviewFilename').textContent=r.filename;
  $('reviewImage').src=r.image_url+'?v='+r.version;
  $('previewMode').textContent='查看原始方向';$('fieldHighlight').hidden=true;
  $('recordType').value=r.type;
  $('ocrTiming').textContent=r.ocr_s==null?'':`OCR ${r.ocr_s.toFixed(3)} 秒`;
  $('reviewer').value=r.reviewer||'';$('reviewNote').value=r.note||'';
  $('reviewNotice').className='review-notice'+(r.status==='approved'?' good':'');
  $('reviewNotice').textContent=r.job_status==='error'?r.error:r.status==='approved'?`字段已由 ${r.reviewer} 确认。期限提示：${r.risk.label}。`:r.missing.length?`有 ${r.missing.length} 项必填字段未识别，请对照原图补录。${r.notes.join('；')}`:r.needs_review.length||r.notes.length?'有字段需要确认格式、精度或含义，核对后勾选“已核对”。':'必填字段已完整，请核对原图后填写审核人并确认。';
  $('rawText').textContent=(r.raw?.rec_texts||[]).join('\n')||'暂无识别文字';
  const actions={uploaded:'上传图片',ocr_completed:'本地 OCR 完成',fields_updated:'保存字段修正',approved:'确认字段审核',ocr_retry:'重新识别',region_ocr:'框选区域识别'};
  $('auditList').innerHTML=(r.audit||[]).map(a=>`<div class="audit-item">${escapeHtml(a.at.replace('T',' '))}<br>${escapeHtml(actions[a.action]||a.action)}</div>`).join('');
  $('saveMessage').textContent='保存修正后重新检查必填字段';
  $('saveRecord').disabled=r.job_status!=='done';$('approveRecord').disabled=r.job_status!=='done';
  $('approveNext').disabled=r.job_status!=='done';
  const info=r.review_info||{};
  $('lastReviewDate').value=info.last_review_date||'';$('nextReviewDate').value=info.next_due_date||'';
  $('reviewProof').value=info.proof_status||'unknown';$('reviewProofNote').value=info.proof_note||'';
  $('reviewDetailsPanel').hidden=r.type!=='electrical';
  $('riskNotice').textContent='证书风险：'+(r.risks||[r.risk]).map(x=>x.label).join('；')+'。字段审核不代表上岗资格确认。';
  renderFields();
}
function renderFields(preserved=null){
  const r=active,template=state.settings.templates[$('recordType').value];
  $('fieldInputs').innerHTML=[...state.fields].sort((a,b)=>issueRank(r.fields[a.key])-issueRank(r.fields[b.key])).map(({key,label})=>{
    const f=r.fields[key],applicable=template.applicable.includes(key),required=template.required.includes(key);
    const value=preserved?.[key]??f.value;
    const stateLabel=!applicable?'不适用':!value?(required?'未识别':'选填'):f.source==='manual'?'人工修正':f.source==='region_ocr'?'区域识别':f.state==='review'?'待核对':'已提取';
    const fieldState=!applicable?'na':!value&&required?'missing':f.state;
    return `<div class="field-row"><label for="field-${key}">${required?'<span class="required-star">*</span>':''}${escapeHtml(label)}<span class="field-state ${fieldState}">${stateLabel}</span></label><input id="field-${key}" data-field="${key}" data-state="${fieldState}" value="${escapeHtml(applicable?value:'不适用')}" ${!applicable?'disabled':''} placeholder="${required?'未识别，请对照原图补录':'选填'}" maxlength="200" autocomplete="off"><button type="button" class="crop-trigger" data-crop="${key}" ${!applicable||r.job_status!=='done'?'hidden':''} aria-label="框选重识别：${escapeHtml(label)}">框选重识别</button><div class="field-origin">${applicable?`整图 OCR：${escapeHtml(f.raw_value||'未提取')}${f.source==='region_ocr'?' · 区域识别值：'+escapeHtml(f.value):''}${f.confidence!=null?' · 置信度 '+Math.round(f.confidence*100)+'%':''}`:'此证书类型不使用该字段'}</div>${applicable&&f.issues.length?`<div class="field-issues">${escapeHtml(f.issues.join('；'))}</div>`:''}${applicable?`<label class="field-confirm"><input type="checkbox" data-confirm="${key}" ${(r.confirmed||[]).includes(key)?'checked':''}>已对照原图核对该字段</label>`:''}</div>`;
  }).join('');
}
function issueRank(f){return f.state==='missing'?0:f.state==='review'?1:f.applicable?2:3;}
function nextIssue(){
  const inputs=[...document.querySelectorAll('[data-field]:not(:disabled)')].filter(el=>{
    const key=el.dataset.field,checked=document.querySelector(`[data-confirm="${key}"]`)?.checked;
    return (state.settings.templates[$('recordType').value].required.includes(key)&&!el.value.trim()) || (active.fields[key].state==='review'&&!checked);
  });
  if(!inputs.length){toast('当前没有未处理的缺失或待核对字段，可继续检查复审管理信息');return;}
  const current=inputs.findIndex(el=>el.dataset.field===lastIssueKey),input=inputs[(current+1)%inputs.length];
  lastIssueKey=input.dataset.field;input.focus();input.scrollIntoView({block:'center',behavior:'smooth'});highlight(lastIssueKey);
}
function highlight(key){
  const box=active.fields[key]?.evidence?.find(e=>e.box)?.box;
  const image=$('reviewImage'),overlay=$('fieldHighlight');
  if(!box||originalPreview||!image.naturalWidth){overlay.hidden=true;return;}
  overlay.style.left=(box[0]/image.naturalWidth*100)+'%';overlay.style.top=(box[1]/image.naturalHeight*100)+'%';overlay.style.width=((box[2]-box[0])/image.naturalWidth*100)+'%';overlay.style.height=((box[3]-box[1])/image.naturalHeight*100)+'%';overlay.hidden=false;
}
function nextReviewId(queue,currentId,records){
  const position=queue.indexOf(currentId);
  const ordered=[...queue.slice(position+1),...queue.slice(0,Math.max(position,0))];
  return ordered.find(id=>id!==currentId&&records.some(r=>r.id===id&&r.job_status==='done'&&r.status!=='approved'));
}
async function saveRecord(approve=false,goNext=false){
  if(!active)return;
  const changes={};document.querySelectorAll('[data-field]:not(:disabled)').forEach(i=>{if(i.value!==active.fields[i.dataset.field].value&&!regionSelections[i.dataset.field])changes[i.dataset.field]=i.value;});
  const confirmed=[...document.querySelectorAll('[data-confirm]:checked')].map(i=>i.dataset.confirm);
  const payload={version:active.version,type:$('recordType').value,changes,confirmed,reviewer:$('reviewer').value,note:$('reviewNote').value,region_selections:regionSelections,approve};
  if($('recordType').value==='electrical')payload.review_details={last_review_date:$('lastReviewDate').value,next_due_date:$('nextReviewDate').value,proof_status:$('reviewProof').value,proof_note:$('reviewProofNote').value};
  const previousId=active.id,previousReviewer=$('reviewer').value;
  $('saveRecord').disabled=true;$('approveRecord').disabled=true;$('approveNext').disabled=true;
  try{active=await(await api(`/api/records/${active.id}`,{method:'PATCH',body:JSON.stringify(payload)})).json();renderReview();$('saveMessage').textContent=approve?'字段审核已确认':'修正已保存，已重新检查字段';await refresh();toast(approve?'已确认字段审核':'字段修正已保存');
    if(goNext){
      const next=nextReviewId(reviewQueue,previousId,state.records);
      if(next){await openRecord(next,true);if(!$('reviewer').value)$('reviewer').value=previousReviewer;}
      else{$('reviewDialog').close();toast('当前审核队列已完成');}
    }
  }catch(e){$('saveMessage').textContent=e.message;toast(e.message,true);}finally{$('saveRecord').disabled=false;$('approveRecord').disabled=false;$('approveNext').disabled=false;}
}
function openRules(){if(!state.settings){toast('正在连接本地服务，请稍后再试');return;}ruleDraft=structuredClone(state.settings);ruleType='electrical';renderRules();$('rulesDialog').showModal();}
function renderRules(){
  $('ruleTabs').innerHTML=Object.entries(ruleDraft.templates).map(([key,t])=>`<button data-rule-type="${key}" class="${key===ruleType?'selected':''}">${escapeHtml(t.name)}</button>`).join('');
  const t=ruleDraft.templates[ruleType];
  $('ruleFields').innerHTML=state.fields.map(f=>{const applicable=t.applicable.includes(f.key);return `<label class="rule-option ${applicable?'':'inactive'}"><input type="checkbox" data-required="${f.key}" ${t.required.includes(f.key)?'checked':''} ${applicable?'':'disabled'}>${escapeHtml(f.label)}<small>${applicable?(t.required.includes(f.key)?'必填':'选填'):'不适用'}</small></label>`;}).join('');
  $('rulesVersion').textContent=`规则版本 v${ruleDraft.version} · ${t.required.length} 项必填`;
}
async function saveRules(){
  $('saveRules').disabled=true;
  try{await api('/api/settings',{method:'PUT',body:JSON.stringify({version:ruleDraft.version,required:Object.fromEntries(Object.entries(ruleDraft.templates).map(([k,t])=>[k,t.required]))})});$('rulesDialog').close();await refresh();toast('字段规则已保存，现有记录已重新检查');}catch(e){toast(e.message,true);}finally{$('saveRules').disabled=false;}
}
async function exportRecords(format){
  try{const response=await api('/api/export',{method:'POST',body:JSON.stringify({format,ids:visibleRecords().map(r=>r.id)})});const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`证书提取结果_${state.today}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);toast(`已导出当前筛选的 ${visibleRecords().length} 条记录`);}catch(e){toast(e.message,true);}
}
$('sampleButton').addEventListener('click',importSamples);$('emptySamples').addEventListener('click',importSamples);
$('uploadButton').addEventListener('click',()=>$('fileInput').click());$('fileInput').addEventListener('change',e=>uploadFiles([...e.target.files]));
['dragenter','dragover'].forEach(event=>$('dropZone').addEventListener(event,e=>{e.preventDefault();$('dropZone').classList.add('drag');}));
['dragleave','drop'].forEach(event=>$('dropZone').addEventListener(event,e=>{e.preventDefault();$('dropZone').classList.remove('drag');}));
$('dropZone').addEventListener('drop',e=>uploadFiles([...e.dataTransfer.files]));
$('filterTabs').addEventListener('click',e=>{const b=e.target.closest('[data-filter]');if(!b)return;filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('selected',x===b));render();});
$('riskFilter').addEventListener('change',render);$('nextIssue').addEventListener('click',nextIssue);$('approveNext').addEventListener('click',()=>saveRecord(true,true));
$('search').addEventListener('input',render);$('typeFilter').addEventListener('change',render);
$('recordBody').addEventListener('click',e=>{const del=e.target.closest('[data-delete]');if(del){deleteRecord(del.dataset.delete);return;}const b=e.target.closest('[data-open]');if(b)openRecord(b.dataset.open);});
$('fieldInputs').addEventListener('focusin',e=>{if(e.target.dataset.field)highlight(e.target.dataset.field);});
$('recordType').addEventListener('change',()=>{$('reviewDetailsPanel').hidden=$('recordType').value!=='electrical';resetRegion();const values={};document.querySelectorAll('[data-field]:not(:disabled)').forEach(i=>values[i.dataset.field]=i.value);renderFields(values);$('reviewNotice').textContent='证书类型已更改，保存修正后按新类型重新检查。';});
$('closeReview').addEventListener('click',()=>$('reviewDialog').close());
$('saveRecord').addEventListener('click',()=>saveRecord(false));$('approveRecord').addEventListener('click',()=>saveRecord(true));
$('previewMode').addEventListener('click',()=>{originalPreview=!originalPreview;$('reviewImage').src=(originalPreview?active.original_url:active.image_url+(active.image_url.includes('?')?'&':'?')+'v='+active.version);$('previewMode').textContent=originalPreview?'查看识别方向':'查看原始方向';$('fieldHighlight').hidden=true;});
$('retryOcr').addEventListener('click',async()=>{try{await api(`/api/records/${active.id}/retry`,{method:'POST'});$('reviewDialog').close();toast('已加入重新识别队列，保留人工修正值');await refresh();}catch(e){toast(e.message,true);}});
['rulesButton','rulesNav'].forEach(id=>$(id).addEventListener('click',openRules));$('closeRules').addEventListener('click',()=>$('rulesDialog').close());$('saveRules').addEventListener('click',saveRules);
$('ruleTabs').addEventListener('click',e=>{const b=e.target.closest('[data-rule-type]');if(b){ruleType=b.dataset.ruleType;renderRules();}});
$('ruleFields').addEventListener('change',e=>{const k=e.target.dataset.required;if(!k)return;const t=ruleDraft.templates[ruleType];t.required=e.target.checked?[...new Set([...t.required,k])]:t.required.filter(x=>x!==k);e.target.closest('label').querySelector('small').textContent=e.target.checked?'必填':'选填';$('rulesVersion').textContent=`规则版本 v${ruleDraft.version} · ${t.required.length} 项必填`;});
$('exportCsv').addEventListener('click',()=>exportRecords('csv'));$('exportXlsx').addEventListener('click',()=>exportRecords('xlsx'));
$('helpButton').addEventListener('click',()=>$('helpDialog').showModal());$('closeHelp').addEventListener('click',()=>$('helpDialog').close());
$('workbenchNav').addEventListener('click',()=>{personFilter=null;$('lifecycleFilter').value='all';filter='all';$('riskFilter').value='all';$('search').value='';$('typeFilter').value='all';document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('selected',x.dataset.filter==='all'));render();});
refresh();setInterval(refresh,1800);

$('viewMode').addEventListener('change',render);
$('clearSelection').addEventListener('click',()=>{selectedRecords.clear();render();});
$('batchDelete').addEventListener('click',batchDeleteRecords);
$('selectAll').addEventListener('change',e=>{
  selectedRecords.clear();if(e.target.checked)visibleRecords().filter(r=>!['queued','running'].includes(r.job_status)).slice(0,500).forEach(r=>selectedRecords.set(r.id,r.version));render();
});
$('recordBody').addEventListener('change',e=>{
  const id=e.target.dataset.select;if(!id)return;
  const r=state.records.find(x=>x.id===id);if(!r)return;
  if(e.target.checked){if(selectedRecords.size>=500){toast('每批最多选择 500 条',true);}else selectedRecords.set(id,r.version);}else selectedRecords.delete(id);
  render();
});

async function controlModel(action){
  $('startModel').disabled=true;$('stopModel').disabled=true;
  try{const result=await(await api('/api/engine/'+action,{method:'POST'})).json();state.engine=result;render();toast(result.message);}
  catch(e){toast(e.message,true);render();}
}
$('startModel').addEventListener('click',()=>controlModel('start'));
$('stopModel').addEventListener('click',()=>controlModel('stop'));
