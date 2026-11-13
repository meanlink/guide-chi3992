import {datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify,date} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';

const OUTCOME_LABEL={added:'新增',corrected:'更正',ignored:'忽略',conflict:'冲突'};

function previewColumns(meta){return [...meta.columns,{key:'revision',label:'修订号'}];}
function previewRows(detail){return (detail?.records||[]).slice(0,30).map(r=>({...r,revision:detail.revisions?.[r.record]??1}));}

function reconcilePanel(summary,applied){
 const counts=[['added','新增'],['corrected','更正'],['ignored','忽略'],['conflict','冲突']];
 const blocked=summary.conflict>0;
 return '<div class="reconcile-panel '+(blocked?'blocked':'')+'">'
  +'<div class="section-title"><h2>'+(applied?'补报已落入原批次':'补报核对结果')+'</h2><span>共 '+summary.total+' 行</span></div>'
  +'<div class="reconcile-grid">'+counts.map(([k,label])=>'<div class="reconcile-count '+k+'"><span>'+label+'</span><strong>'+summary[k]+'</strong></div>').join('')+'</div>'
  +(blocked?'<p class="conflict-box">存在 '+summary.conflict+' 条同号同版内容冲突，整批未落入。请按冲突原因修正后重新上传，重试不会影响既有数据与分析。</p>'
    :'<p class="ok-box">核对通过：新增 '+summary.added+' 条、更正 '+summary.corrected+' 条、忽略 '+summary.ignored+' 条。确认后才会写入原批次。</p>')
  +'<div class="table-wrap reconcile-table"><table><thead><tr><th>行号</th><th>记录编号</th><th>修订号</th><th>判定</th><th>原因</th></tr></thead><tbody>'
  +summary.items.map(x=>'<tr class="outcome-row '+x.outcome+'"><td>'+x.line+'</td><td>'+esc(x.record)+'</td><td>'+x.revision+'</td><td><span class="outcome '+x.outcome+'">'+OUTCOME_LABEL[x.outcome]+'</span></td><td>'+esc(x.reason)+'</td></tr>').join('')
  +'</tbody></table></div>'
  +(blocked||applied?'':'<button type="button" class="primary" id="apply-supplement">确认落入原批次 ↗</button>')
  +'</div>';
}

function historyPanel(detail){
 const logs=detail.supplements||[];
 if(!logs.length)return '<div class="empty">该批次尚无补报记录。首版数据视为修订号 1。</div>';
 return '<div class="supplement-history">'+logs.map(s=>{
   const z=s.summary||{};
   return '<article class="supplement-item" data-log="'+s.id+'"><div class="supplement-head"><strong class="outcome '+s.status+'">'+(s.status==='applied'?'已落入':'已拒收')+'</strong><span>'+esc(s.source||'')+' · '+date(s.created_at)+' · '+esc(s.created_by||'')+'</span></div>'
    +'<p>新增 '+z.added+' · 更正 '+z.corrected+' · 忽略 '+z.ignored+' · 冲突 '+z.conflict+'（上传 '+z.total+' 行）</p>'
    +'<div class="supplement-detail" id="log-'+s.id+'" hidden>'+(z.items?('<div class="table-wrap"><table><thead><tr><th>行号</th><th>记录编号</th><th>修订号</th><th>判定</th><th>原因</th></tr></thead><tbody>'+z.items.map(x=>'<tr><td>'+x.line+'</td><td>'+esc(x.record)+'</td><td>'+x.revision+'</td><td><span class="outcome '+x.outcome+'">'+OUTCOME_LABEL[x.outcome]+'</span></td><td>'+esc(x.reason)+'</td></tr>').join('')+'</tbody></table></div>'):'')+'</div></article>';
 }).join('')+'</div>';
}

export async function dataPage(){
 workspace.datasets=await datasets.list();
 const first=workspace.datasets[0];
 const selected=first?await datasets.get(first.id):null;
 const m=workspace.meta;
 const readOnly=session.user.role==='viewer';
 return heading('02 / DATA INTAKE','数据接入与批次追溯','保留原始业务字段、来源和内容指纹。支持向原批次补报：以记录编号和修订号识别新增与更正，分析任务始终绑定发起时的样本快照。')
  +'<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>业务批次</h2><span>'+workspace.datasets.length+' 批</span></div><div class="batch-list">'
  +workspace.datasets.map(d=>'<button class="batch-item" data-dataset="'+d.id+'"><strong>'+esc(d.name)+'</strong><span>'+d.rows+' 条 · 补报 '+(d.supplement_count||0)+' 次 · '+esc(d.source)+'</span><small>SHA256 '+esc(d.checksum.slice(0,18))+'…</small></button>').join('')
  +'</div><div class="section-title"><h2>接入新数据</h2></div><form id="dataset-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：11 月复测批次"></label><label>上传 CSV 或 JSON<input type="file" id="file-input" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="5" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">字段：'+m.columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。5–5,000 条记录，记录编号不可重复。</p><button type="submit" class="primary" '+(readOnly?'disabled':'')+'>校验并接入批次</button></form></section>'
  +'<section class="panel"><div class="section-title"><h2 id="preview-name">'+esc(selected?.name||'尚无批次')+'</h2><span>预览前 30 条 · 首版视为修订号 1</span></div><div id="data-preview">'+table(previewColumns(m),previewRows(selected))+'</div>'
  +'<div class="section-title supplement-title"><h2>向原批次补报</h2><span>同号同版冲突整批不落入</span></div>'
  +'<form id="supplement-form"><label>补报目标批次<select name="dataset_id" '+(readOnly?'disabled':'')+'>'+workspace.datasets.map(d=>'<option value="'+d.id+'" '+((selected&&d.id===selected.id)?'selected':'')+'>'+esc(d.name)+' · '+d.rows+' 条</option>').join('')+'</select></label>'
  +'<label>补报文件 CSV 或 JSON<input type="file" id="supplement-file" accept=".json,.csv" '+(readOnly?'disabled':'')+'></label><label>补报记录 JSON<textarea name="records" rows="5" placeholder="包含记录编号 record、修订号 revision 及业务字段；省略 revision 时按修订号 1 处理" '+(readOnly?'disabled':'')+'></textarea></label>'
  +'<p class="hint">口径：以记录编号 + 修订号识别。新编号为<strong>新增</strong>；修订号更高为<strong>更正</strong>；同版同内容重复补报或旧修订一律<strong>忽略</strong>，不增人数、不覆盖新值；同号同版内容冲突则<strong>整批不落入</strong>。</p>'
  +'<button type="submit" class="primary" '+(readOnly||!workspace.datasets.length?'disabled':'')+'>核对补报（先核对后落入）</button></form>'
  +'<div id="reconcile-result"></div>'
  +'<div class="section-title supplement-title"><h2>补报留痕</h2><span>含被拒收批次与冲突原因</span></div><div id="supplement-history">'+historyPanel(selected)+'</div>'
  +'</section></div>';
}

async function loadDetail(id){
 const detail=await datasets.get(id);
 document.querySelector('#preview-name').textContent=detail.name;
 document.querySelector('#data-preview').innerHTML=table(previewColumns(workspace.meta),previewRows(detail));
 document.querySelector('#supplement-history').innerHTML=historyPanel(detail);
 return detail;
}

export function bindData(refresh){
 let source='manual.json';
 let supplementSource='supplement.json';
 let currentSummary=null;
 let previewTarget=null;
 const readOnly=session.user.role==='viewer';
 document.querySelector('#file-input').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;source=file.name;const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('#dataset-form [name=records]').value=JSON.stringify(records,null,2);}catch(error){notify(error.message,true);}});
document.querySelectorAll('[data-dataset]').forEach(button=>button.onclick=async()=>{try{await loadDetail(Number(button.dataset.dataset));document.querySelector('#supplement-form [name=dataset_id]').value=button.dataset.dataset;currentSummary=null;previewTarget=null;document.querySelector('#reconcile-result').innerHTML='';}catch(error){notify(error.message,true);}});
 submit(document.querySelector('#dataset-form'),async f=>{await datasets.create({name:f.get('name'),source,records:JSON.parse(f.get('records'))});notify('数据已接入，可前往工作台执行分析');await refresh();});
 document.querySelector('#supplement-file').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;supplementSource=file.name;const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('#supplement-form [name=records]').value=JSON.stringify(records,null,2);}catch(error){notify(error.message,true);}});
 document.querySelector('#supplement-history').addEventListener('click',e=>{const item=e.target.closest('.supplement-item');if(!item)return;const box=document.querySelector('#log-'+item.dataset.log);if(box)box.hidden=!box.hidden;});
 if(readOnly)return;
 document.querySelector('#supplement-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const form=e.currentTarget;const button=form.querySelector('[type=submit]');
  let records;
  try{records=JSON.parse(form.records.value);}catch{notify('补报记录必须是 JSON 数组（CSV 请先在上方选择文件自动转换）',true);return;}
  const id=Number(form.dataset_id.value);
  button.disabled=true;
  try{
   currentSummary=await datasets.previewSupplement(id,{source:supplementSource,records});
   previewTarget=id;
   document.querySelector('#reconcile-result').innerHTML=reconcilePanel(currentSummary,false);
   notify(currentSummary.conflict?'核对发现冲突，整批将不会落入':'核对完成，可在下方确认落入');
  }catch(error){
   notify(error.message,true);
  }finally{button.disabled=false;}
 });
 document.querySelector('#reconcile-result').addEventListener('click',async e=>{
  if(!e.target.id||e.target.id!=='apply-supplement'||!currentSummary)return;
  const form=document.querySelector('#supplement-form');const id=Number(form.dataset_id.value);
  if(previewTarget!==id){notify('目标批次已切换，请重新核对后再落入',true);currentSummary=null;document.querySelector('#reconcile-result').innerHTML='';return;}
  let records;
  try{records=JSON.parse(form.records.value);}catch{notify('补报记录解析失败，请重新上传',true);return;}
  e.target.disabled=true;
  try{
   const out=await datasets.applySupplement(id,{source:supplementSource,records});
   currentSummary=null;
   document.querySelector('#reconcile-result').innerHTML=reconcilePanel(out.reconciliation,true);
   notify('补报已落入原批次，既有分析任务样本保持不变');
   await refresh();
  }catch(error){
   const reconciliation=error.payload?.reconciliation;
   if(reconciliation){document.querySelector('#reconcile-result').innerHTML=reconcilePanel(reconciliation,false);}
   notify(error.message,true);
   e.target.disabled=false;
  }
 });
}
