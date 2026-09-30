'use strict';
let regionSelections={},roiTarget=null,roiBox=null,roiStart=null,roiResult=null,roiBusy=false,roiSession=0;
function closeRegion(){
  roiSession++;roiTarget=null;roiBox=null;roiStart=null;roiResult=null;roiBusy=false;
  $('regionPanel').hidden=true;$('regionBox').hidden=true;$('regionCandidates').innerHTML='';
  $('imageStage').classList.remove('selecting');$('runRegion').disabled=true;
}
function resetRegion(){closeRegion();regionSelections={};}
function beginRegion(key){
  closeRegion();roiTarget=key;
  if(originalPreview){originalPreview=false;$('reviewImage').src=active.image_url+'?v='+active.version;$('previewMode').textContent='查看原始方向';}
  $('fieldHighlight').hidden=true;$('regionPanel').hidden=false;
  $('regionTarget').textContent='框选：'+active.fields[key].label;
  $('regionMessage').textContent='请在下方图片上拖动框选文字，随后点击“识别选区”。';
  $('regionMode').value='line';$('imageStage').classList.add('selecting');
  $('regionPanel').scrollIntoView({block:'nearest',behavior:'smooth'});
}
function imagePoint(e){
  const image=$('reviewImage'),rect=image.getBoundingClientRect();
  return [Math.round(Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width))*image.naturalWidth),
          Math.round(Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height))*image.naturalHeight)];
}
function drawRegion(){
  const im=$('reviewImage'),box=$('regionBox');
  if(!roiBox)return;
  box.style.left=roiBox[0]/im.naturalWidth*100+'%';box.style.top=roiBox[1]/im.naturalHeight*100+'%';
  box.style.width=(roiBox[2]-roiBox[0])/im.naturalWidth*100+'%';box.style.height=(roiBox[3]-roiBox[1])/im.naturalHeight*100+'%';box.hidden=false;
}
$('fieldInputs').addEventListener('click',e=>{const button=e.target.closest('[data-crop]');if(button&&!roiBusy)beginRegion(button.dataset.crop);});
$('fieldInputs').addEventListener('input',e=>{
  const key=e.target.dataset.field;if(!key)return;
  delete regionSelections[key];
  const checkbox=document.querySelector(`[data-confirm="${key}"]`);if(checkbox)checkbox.checked=false;
});
$('imageStage').addEventListener('pointerdown',e=>{
  if(!roiTarget||roiBusy||e.button!==0||!$('reviewImage').complete)return;
  e.preventDefault();roiStart=imagePoint(e);roiBox=[...roiStart,...roiStart];
  $('imageStage').setPointerCapture(e.pointerId);$('regionCandidates').innerHTML='';roiResult=null;drawRegion();
});
$('imageStage').addEventListener('pointermove',e=>{
  if(!roiStart)return;const end=imagePoint(e);
  roiBox=[Math.min(roiStart[0],end[0]),Math.min(roiStart[1],end[1]),Math.max(roiStart[0],end[0]),Math.max(roiStart[1],end[1])];drawRegion();
});
$('imageStage').addEventListener('pointerup',e=>{
  if(!roiStart)return;roiStart=null;
  if($('imageStage').hasPointerCapture(e.pointerId))$('imageStage').releasePointerCapture(e.pointerId);
  const valid=roiBox[2]-roiBox[0]>=8&&roiBox[3]-roiBox[1]>=8;$('runRegion').disabled=!valid;
  $('regionMessage').textContent=valid?`选区 ${roiBox[2]-roiBox[0]} × ${roiBox[3]-roiBox[1]} 像素，可重新拖动调整。`:'选区太小，请重新拖动框选。';
});
$('imageStage').addEventListener('pointercancel',()=>{roiStart=null;roiBox=null;$('regionBox').hidden=true;$('runRegion').disabled=true;});
$('cancelRegion').addEventListener('click',closeRegion);
$('previewMode').addEventListener('click',closeRegion);
$('closeReview').addEventListener('click',resetRegion);
$('reviewDialog').addEventListener('cancel',resetRegion);
$('runRegion').addEventListener('click',async()=>{
  if(!roiBox||roiBusy)return;
  const session=roiSession;roiBusy=true;$('runRegion').disabled=true;$('regionMessage').textContent='正在本地识别选区，首次调用可能需要加载模型…';
  try{
    const result=await(await api(`/api/records/${active.id}/region`,{method:'POST',body:JSON.stringify({version:active.version,box:roiBox,target:roiTarget,mode:$('regionMode').value})})).json();
    if(session!==roiSession)return;
    roiResult=result;
    $('regionMessage').textContent=`区域 OCR ${result.ocr_s.toFixed(3)} 秒。请核对候选文字后填入，最后点击“保存修正”。`;
    $('regionCandidates').innerHTML=result.candidates.map(c=>{
      const values=Object.entries(c.values),canUse=!!c.values[roiTarget];
      return `<div class="region-candidate"><b>${escapeHtml(c.variant)} · 置信度 ${(c.confidence*100).toFixed(1)}%</b><p>${escapeHtml(c.text||'未识别出文字')}</p><div>${values.map(([k,v])=>`<span>${escapeHtml(state.fields.find(f=>f.key===k)?.label||k)}：${escapeHtml(v)}</span>`).join('')}</div><button class="button small" data-use-region="${c.id}" ${!canUse?'disabled':''}>填入待保存字段</button>${!canUse?'<small>未提取到目标字段，请选其他候选、缩小选区或手动补录。</small>':''}</div>`;
    }).join('')||'<p>本区域未检测到文字，请缩小为单行并切换单行模式。</p>';
  }catch(e){if(session===roiSession)$('regionMessage').textContent=e.message;}
  finally{if(session===roiSession){roiBusy=false;$('runRegion').disabled=false;}}
});
$('regionCandidates').addEventListener('click',e=>{
  const button=e.target.closest('[data-use-region]');if(!button||!roiResult)return;
  const candidate=roiResult.candidates.find(c=>c.id===button.dataset.useRegion);if(!candidate)return;
  let count=0;
  for(const [key,value] of Object.entries(candidate.values)){
    const input=$('field-'+key);if(!input||input.disabled)continue;
    input.value=value;input.dataset.state='review';
    regionSelections[key]={run_id:roiResult.id,candidate_id:candidate.id};
    const row=input.closest('.field-row');row.querySelector('.field-state').textContent='区域候选 · 待保存';
    const check=row.querySelector('[data-confirm]');if(check)check.checked=false;
    count++;
  }
  $('saveMessage').textContent=`已填入 ${count} 项区域候选，点击“保存修正”后生效。`;
  toast('候选已填入，尚未保存');
});
