'use strict';
let management={people:[],tasks:[],trash:[],historical_ids:[],policy:{days:[10,5],version:1}};
let managementTab='people',editingPerson=null,editingTask=null,linkRecord=null;
const pageLabels={workbench:'提取与审核',people:'人员档案',alerts:'预警任务',trash:'回收站',backup:'数据备份'};
const pageNav={workbench:'workbenchNav',people:'peopleNav',alerts:'alertsNav',trash:'trashNav',backup:'backupNav'};
let navigationVersion=0;
function showPage(page,writeHistory=true){
  $('workbenchPage').hidden=page!=='workbench';
  $('managementPage').hidden=page==='workbench';
  $('currentPageLabel').textContent=pageLabels[page];
  document.title=pageLabels[page]+' · 证书台账';
  $('managementTitle').textContent=pageLabels[page];
  Object.entries(pageNav).forEach(([key,id])=>{$(id).classList.toggle('active',key===page);if(key===page)$(id).setAttribute('aria-current','page');else $(id).removeAttribute('aria-current');});
  if(writeHistory&&location.hash!==`#${page}`)history.pushState(null,'',`#${page}`);
  window.scrollTo(0,0);
}
function showWorkbench(writeHistory=true){navigationVersion++;showPage('workbench',writeHistory);render();}
const availabilityLabels={onsite:'在岗',available:'可调配',away:'离岗'};
const taskLabels={pending:'待处理',processing:'处理中',resolved:'已解决'};
const stageLabels={verify:'日期待核实',overdue:'已逾期',due_today:'今日截止'};
const option=(value,label,selected)=>`<option value="${escapeHtml(value)}" ${value===selected?'selected':''}>${escapeHtml(label)}</option>`;
async function loadManagement(){management=await(await api('/api/management')).json();}
async function openManagement(tab='people',writeHistory=true){
  const version=++navigationVersion;
  managementTab=tab;editingPerson=null;editingTask=null;showPage(tab,writeHistory);
  $('managementContent').innerHTML='<p role="status" class="ops-note">正在加载…</p>';
  try{await loadManagement();if(!state.settings)state=await(await api('/api/state')).json();if(version!==navigationVersion)return;renderManagement();}
  catch(e){if(version===navigationVersion)$('managementContent').innerHTML='<p role="alert">加载失败，请点击左侧菜单重试。</p>';toast(e.message,true);}
}
function renderManagement(){
  document.querySelectorAll('[data-management-tab]').forEach(b=>b.classList.toggle('selected',b.dataset.managementTab===managementTab));
  const content=$('managementContent');
  if(managementTab==='people'){
    const p=editingPerson||{name:'',project:'',role:'',officer:'',availability:'onsite'};
    content.innerHTML=`<div class="ops-intro"><p>使用独立人员编号管理。同名人员可分别建档，证书在列表“归属 / 换证”中手工关联。</p></div>
    <form id="personForm" class="ops-form"><h4>${p.id?'编辑人员档案':'新建人员档案'}</h4><div class="ops-grid">
    ${[['name','姓名'],['project','所属项目'],['role','岗位'],['officer','负责安全员']].map(([k,l])=>`<label>${l}<input name="${k}" value="${escapeHtml(p[k])}" maxlength="80" ${k==='name'?'required':''}></label>`).join('')}
    <label>人员状态<select name="availability">${Object.entries(availabilityLabels).map(([v,l])=>option(v,l,p.availability)).join('')}</select></label></div>
    <button class="button primary" type="submit">保存人员档案</button>${p.id?'<button class="button" type="button" data-new-person>取消编辑</button>':''}</form>
    <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>姓名 / 人员编号</th><th>项目 / 岗位</th><th>安全员</th><th>状态</th><th>证书数</th><th>操作</th></tr></thead><tbody>${management.people.map(p=>`<tr><td><b>${escapeHtml(p.name)}</b><small>${escapeHtml(p.id)}</small></td><td>${escapeHtml(p.project||'未分配项目')}<small>${escapeHtml(p.role||'未设置岗位')}</small></td><td>${escapeHtml(p.officer||'未分配')}</td><td>${availabilityLabels[p.availability]}</td><td>${state.records.filter(r=>r.person_id===p.id).length}</td><td><button class="table-link" data-edit-person="${p.id}">编辑</button><button class="table-link" data-person-records="${p.id}">查看证书</button></td></tr>`).join('')||'<tr><td colspan="6">暂无人员档案，请先新建。</td></tr>'}</tbody></table></div>`;
    $('personForm').onsubmit=async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));if(p.id)body.version=p.version;await opsAction(async()=>{await api(p.id?`/api/people/${p.id}`:'/api/people',{method:p.id?'PUT':'POST',body:JSON.stringify(body)});editingPerson=null;},'人员档案已保存');};
  }else if(managementTab==='alerts'){
    const t=editingTask;
    content.innerHTML=`<div class="ops-intro"><p>服务运行时每分钟检查，打开此页面立即检查。没有发送外部消息。关闭任务仅记录处理结果，证书风险仍会显示；进入更紧急阶段会重新待处理。</p></div>
    <form id="policyForm" class="ops-inline"><label>提前提醒天数（逗号分隔）<input id="alertDays" value="${management.policy.days.join(',')}" required></label><button class="button" type="submit">保存提醒规则</button><button class="button" type="button" data-refresh-ops>重新检查</button></form>
    ${t?`<form id="taskForm" class="ops-form"><h4>处理 ${escapeHtml(t.person_name)} 的${t.kind==='expiry'?'有效期':'复审'}任务</h4><div class="ops-grid"><label>责任人<input name="owner" value="${escapeHtml(t.owner||t.suggested_owner)}" maxlength="80" required></label><label>处理状态<select name="status">${Object.entries(taskLabels).map(([k,l])=>option(k,l,t.status)).join('')}</select></label></div><label>处理记录 / 解决依据<textarea name="note" maxlength="1000" required>${escapeHtml(t.note)}</textarea></label><button class="button primary">保存处理记录</button><button class="button" type="button" data-cancel-task>取消</button><details><summary>处理历史（${t.history.length}）</summary>${t.history.map(h=>`<p>${escapeHtml(h.at)} · ${escapeHtml(taskLabels[h.action]||h.action)} · ${escapeHtml(h.owner||'')} ${escapeHtml(h.note||'')}</p>`).join('')}</details></form>`:''}
    <div class="ops-inline"><label>任务范围<select id="taskScope"><option value="open">待处理 / 处理中</option><option value="all">全部含历史</option></select></label><span>当前待处理 ${management.tasks.filter(t=>t.active&&t.status!=='resolved').length} 项</span></div>
    <div class="ops-table-wrap"><table class="ops-table"><thead><tr><th>人员 / 项目</th><th>事项 / 截止日</th><th>风险阶段</th><th>责任人</th><th>状态</th><th>操作</th></tr></thead><tbody id="tasksBody"></tbody></table></div>`;
    const renderTasks=()=>{$('tasksBody').innerHTML=management.tasks.filter(t=>$('taskScope').value==='all'||t.active&&t.status!=='resolved').map(t=>`<tr><td>${escapeHtml(t.person_name)}<small>${escapeHtml(t.project||'未分配项目')}</small></td><td>${t.kind==='expiry'?'证书有效期':'复审'}<small>${escapeHtml(t.due||'需核实日期')}</small></td><td>${t.active?escapeHtml(stageLabels[t.stage]||(t.days+' 天后截止')):'已退出风险条件'}</td><td>${escapeHtml(t.owner||t.suggested_owner||'未分配')}</td><td>${taskLabels[t.status]}</td><td><button class="table-link" data-edit-task="${t.id}">${t.active?'处理':'查看记录'}</button>${state.records.some(r=>r.id===t.record_id)?`<button class="table-link" data-task-record="${t.record_id}">核对证书</button>`:''}</td></tr>`).join('')||'<tr><td colspan="6">当前没有此类任务。</td></tr>';};
    renderTasks();$('taskScope').onchange=renderTasks;
    $('policyForm').onsubmit=async e=>{e.preventDefault();await opsAction(()=>api('/api/alert-policy',{method:'PUT',body:JSON.stringify({version:management.policy.version,days:$('alertDays').value.split(/[,，]/).map(x=>Number(x.trim()))})}),'提醒规则已更新');};
    if(t){$('taskForm').onsubmit=async e=>{e.preventDefault();const body={...Object.fromEntries(new FormData(e.target)),version:t.version};await opsAction(async()=>{await api(`/api/alerts/${t.id}`,{method:'PATCH',body:JSON.stringify(body)});editingTask=null;},'处理记录已保存');};if(!t.active)$('taskForm').querySelector('button').disabled=true;}
  }else if(managementTab==='trash'){
    content.innerHTML=`<div class="ops-intro"><p>删除的证书保留原图、修正值和审核记录。恢复后会重新检查期限风险。</p></div><button id="restoreSelected" class="button primary">恢复所选证书</button><div class="ops-table-wrap"><table class="ops-table"><thead><tr><th><input id="selectTrash" type="checkbox" aria-label="全选回收站"></th><th>姓名</th><th>文件</th><th>删除时间</th></tr></thead><tbody>${management.trash.map(r=>`<tr><td><input data-trash-id="${r.id}" type="checkbox" aria-label="恢复 ${escapeHtml(r.filename)}"></td><td>${escapeHtml(r.person_name||'未识别姓名')}</td><td>${escapeHtml(r.filename)}</td><td>${escapeHtml(r.deleted_at)}</td></tr>`).join('')||'<tr><td colspan="4">回收站为空。</td></tr>'}</tbody></table></div>`;
    $('selectTrash').onchange=e=>document.querySelectorAll('[data-trash-id]').forEach(x=>x.checked=e.target.checked);
    $('restoreSelected').onclick=async()=>{const ids=[...document.querySelectorAll('[data-trash-id]:checked')].map(x=>x.dataset.trashId);if(!ids.length){toast('请勾选需要恢复的证书');return;}await opsAction(()=>api('/api/trash/restore',{method:'POST',body:JSON.stringify({records:management.trash.filter(r=>ids.includes(r.id)).map(({id,version})=>({id,version}))})}),'所选证书已恢复');};
  }else{
    content.innerHTML='<div class="ops-intro"><p>下载包含全部证书图片、原始识别、人工修正、人员档案、任务和操作记录的备份包，也包含回收站记录。识别进行时不能备份。</p><p>恢复采用离线工具，先校验文件完整性并恢复到新目录，再切换数据目录；不在网页直接覆盖现有数据。</p></div><button id="downloadBackup" class="button primary">下载完整备份 ZIP</button><p class="ops-note">备份包含个人证书信息，请存放在受控位置。</p>';
    $('downloadBackup').onclick=async()=>{const b=$('downloadBackup');b.disabled=true;try{await downloadResponse(await api('/api/backup',{method:'POST'}),`证书完整备份_${state.today}.zip`);toast('备份已生成');}catch(e){toast(e.message,true);}finally{b.disabled=false;}};
  }
}
async function opsAction(action,message){
  const version=navigationVersion;
  const buttons=[...$('managementPage').querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try{await action();await refresh();await loadManagement();if(version===navigationVersion)renderManagement();toast(message);}
  catch(e){toast(e.message,true);}
  finally{buttons.forEach(b=>b.disabled=false);}
}
async function downloadResponse(response,name){const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
async function openLinks(id){
  try{
    await loadManagement();linkRecord=await(await api(`/api/records/${id}`)).json();const r=linkRecord;
    const candidates=state.records.filter(x=>x.id!==r.id&&r.person_id&&x.person_id===r.person_id&&x.type===r.type&&!x.replaces_id&&!x.superseded_by&&x.job_status==='done');
    $('linkTitle').textContent=`${r.fields.person_name.value||r.filename} · 归属与换证`;
    $('linkContent').innerHTML=`<form id="linkPersonForm" class="ops-form"><label>关联人员档案<select name="person_id">${option('','未关联',r.person_id||'')}${management.people.map(p=>option(p.id,`${p.name} · ${p.project||'未分配项目'} · ${p.id.slice(0,8)}`,r.person_id)).join('')}</select></label><label>核对依据<input name="note" placeholder="例如：已核对员工编号与证书持有人" maxlength="500" required></label><p>证面姓名：${escapeHtml(r.fields.person_name.value||'未识别')}。请核对身份后关联，同名不代表同一人。</p><button class="button primary" ${r.superseded_by||r.replaces_id?'disabled':''}>保存人员归属</button></form>
    <form id="renewalForm" class="ops-form"><h4>此证书的后续新证</h4><p>先上传新证并关联同一人员，再在这里选择。新证字段审核通过、有效期延长且已经生效后，旧证才进入历史。</p>
    ${r.superseded_by?`<p>已关联新证编号：${escapeHtml(r.superseded_by)} · ${management.historical_ids.includes(r.id)?'旧证已归档':'等待新证审核或生效'}</p>`:`<label>选择新证<select name="new_id" required><option value="">请选择</option>${candidates.map(n=>option(n.id,`${n.filename} · 到期 ${n.fields.valid_to.value||'待核实'} · ${statusText[n.status]}`,'')).join('')}</select></label>`}
    <label>关联 / 解除依据<input name="note" maxlength="500" required></label><button class="button" ${!r.superseded_by&&!candidates.length?'disabled':''}>${r.superseded_by?'解除后续新证关联':'关联后续新证'}</button>${r.replaces_id?`<p>此证替代旧证：${escapeHtml(r.replaces_id)}。如需更换人员，请从旧证解除关联。</p>`:''}</form>`;
    $('linkPersonForm').onsubmit=async e=>{e.preventDefault();await linkAction(`/api/records/${r.id}/person`,{...Object.fromEntries(new FormData(e.target)),version:r.version});};
    $('renewalForm').onsubmit=async e=>{e.preventDefault();const body={...Object.fromEntries(new FormData(e.target)),version:r.version};body.new_version=candidates.find(n=>n.id===body.new_id)?.version;await linkAction(`/api/records/${r.id}/${r.superseded_by?'unlink-renewal':'renewal'}`,body);};
    if(!$('linkDialog').open)$('linkDialog').showModal();
  }catch(e){toast(e.message,true);}
}
async function linkAction(url,body){
  const buttons=[...$('linkDialog').querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try{await api(url,{method:'POST',body:JSON.stringify(body)});$('linkDialog').close();await refresh();toast('关联已保存');}
  catch(e){toast(e.message,true);}finally{buttons.forEach(b=>b.disabled=false);}
}
$('managementContent').addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.hasAttribute('data-new-person')){editingPerson=null;renderManagement();}
  if(b.dataset.editPerson){editingPerson=management.people.find(p=>p.id===b.dataset.editPerson);renderManagement();}
  if(b.dataset.personRecords){personFilter=b.dataset.personRecords;filter='all';$('search').value='';$('typeFilter').value='all';$('riskFilter').value='all';$('lifecycleFilter').value='all';document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('selected',x.dataset.filter==='all'));showWorkbench();}
  if(b.dataset.editTask){editingTask=management.tasks.find(t=>t.id===b.dataset.editTask);renderManagement();}
  if(b.hasAttribute('data-cancel-task')){editingTask=null;renderManagement();}
  if(b.dataset.taskRecord){openRecord(b.dataset.taskRecord);}
  if(b.hasAttribute('data-refresh-ops'))opsAction(async()=>{},'风险已重新检查');
});
document.querySelectorAll('[data-management-tab]').forEach(b=>b.onclick=()=>{managementTab=b.dataset.managementTab;editingPerson=null;editingTask=null;renderManagement();});
$('peopleNav').onclick=()=>openManagement('people');$('alertsNav').onclick=()=>openManagement('alerts');$('trashNav').onclick=()=>openManagement('trash');$('backupNav').onclick=()=>openManagement('backup');
$('closeLinks').onclick=()=>$('linkDialog').close();
$('workbenchNav').addEventListener('click',()=>showWorkbench());
function restorePage(){const page=location.hash.slice(1);if(Object.hasOwn(pageLabels,page)&&page!=='workbench')openManagement(page,false);else showWorkbench(false);}
window.addEventListener('popstate',restorePage);
restorePage();
$('recordBody').addEventListener('click',e=>{const b=e.target.closest('[data-links]');if(b)openLinks(b.dataset.links);});
$('clearPersonFilter').onclick=()=>{personFilter=null;render();};
$('sortOrder').onchange=render;$('lifecycleFilter').onchange=render;
$('exportSelected').onclick=async()=>{if(!selectedRecords.size)return;try{await downloadResponse(await api('/api/export',{method:'POST',body:JSON.stringify({format:'xlsx',ids:[...selectedRecords.keys()]})}),`所选证书_${state.today}.xlsx`);}catch(e){toast(e.message,true);}};
