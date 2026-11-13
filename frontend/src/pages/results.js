import {jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {esc,fmt,date,notify} from '../utils/dom.js';

function adjustmentPanel(r){
 const a=r.adjustment;
 if(!a)return '<section class="panel"><div class="section-title"><h2>构成校正比较</h2><span>旧口径快照</span></div><p class="warning">该结果为旧口径快照，未包含按展区两方案合计客流占比校正的完成率比较。历史结果与已分发简报保持原样；如需校正比较，请使用本页“重算另存”。</p><p class="hint">当前口径：'+esc(workspace.meta?.rule_label||'按各展区两方案合计客流占比校正')+'（'+esc(workspace.meta?.rule_version||'')+'）。</p></section>';
 const pooled=a.pooled||{},adjusted=a.adjusted||{},v=a.visitors||{},inc=v.included||{},exc=v.excluded||{},overall=v.overall||{};
 const directionClass=a.direction_reversed?'warning':'hint';
 return '<section class="panel" id="adjustment-panel"><div class="section-title"><h2>按客流构成校正的完成率比较</h2><span>口径 '+esc(a.rule_version||'')+' · 原始汇总保留</span></div>'+
  '<p class="'+directionClass+'"><strong>'+esc(a.summary||'')+'</strong></p>'+
  '<p class="hint">'+esc(a.method||'')+'</p>'+
  '<div class="metrics">'+[['纳入展区',(a.included_zones||[]).length,'个'],['纳入人数',inc.total||0,'人'],['排除展区',(a.excluded_zones||[]).length,'个'],['排除人数',exc.total||0,'人'],['全部人数',overall.total||0,'人'],['原始 B−A',pooled.diff_pp,'pp'],['校正 B−A',a.computable?adjusted.diff_pp:'—','pp'],['方向反转',a.computable?(a.direction_reversed?'是':'否'):'—','']].map(([k,n,u])=>'<div><span>'+esc(k)+'</span><strong>'+esc(fmt(n))+'<small>'+esc(u)+'</small></strong></div>').join('')+'</div>'+
  '<div class="two-columns"><section><div class="section-title"><h2>两口径完成率</h2><span>百分点</span></div>'+table([{key:'label',label:'口径'},{key:'a_rate',label:'A 完成率 %'},{key:'b_rate',label:'B 完成率 %'},{key:'diff_pp',label:'B−A 百分点'},{key:'direction',label:'方向'}],[pooled,...(a.computable?[adjusted]:[])])+'<p class="hint">校正完成率=Σ(展区两方案合计客流占比×该展区各方案完成率)。原始汇总仍按全部记录合并人数计算。逐展区校正表含纳入与排除人数，可与下方明细核对。</p></section>'+
  '<section><div class="section-title"><h2>纳入 / 排除核对</h2><span>排除项不参与校正权重</span></div>'+
  '<p class="hint">排除展区：'+((a.excluded_zones||[]).map(e=>esc(e.zone)+'（'+esc(e.reason)+'，'+esc(fmt(e.visitors.total))+' 人）').join('；')||'无')+'</p>'+
  ((a.excluded_zones||[]).length?'<p class="warning">以上展区缺少任一方案记录，仅保留在原始汇总与下方明细中。</p>':'')+
  '</section></div>'+
  (a.chart?'<div class="section-title"><h2>校正前后对照</h2><span>数值来自后端结果</span></div>'+chart(a.chart):'')+
  '<div class="section-title"><h2>逐展区核对</h2><span>含缺失方案原因</span></div>'+table(a.table?.columns||[],a.table?.rows||[])+
  '</section>';
}

function body(j){
 const r=j.result||{};
 if(j.status!=='completed')return '<section class="panel empty">'+(j.status==='failed'?'计算失败：'+esc(j.error)+'。请返回工作台调整参数或数据。':'后台正在执行计算。点击刷新结果查看最新进展。')+'<a href="#/workbench">返回工作台 ↗</a></section>';
 const canRecompute=session.user.role==='admin'||session.user.role==='analyst';
 return '<section class="result-lead"><p class="eyebrow">COMPUTED FINDING</p><h2>'+esc(r.summary)+'</h2><div class="metrics">'+(r.metrics||[]).map(m=>'<div><span>'+esc(m.label)+'</span><strong>'+esc(fmt(m.value))+'<small>'+esc(m.unit||'')+'</small></strong></div>').join('')+'</div></section>'+
  '<section class="panel">'+chart(r.chart)+'</section>'+
  adjustmentPanel(r)+
  '<div class="two-columns"><section class="panel"><div class="section-title"><h2>业务解释</h2><span>由计算结果生成</span></div><ol class="questions">'+(r.findings||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol>'+(r.warnings||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+'</section><section class="method-sheet compact"><p class="eyebrow">REPRODUCIBILITY</p><h3>计算口径与参数</h3><p>'+esc(r.method)+'</p><pre>'+esc(JSON.stringify(j.params,null,2))+'</pre>'+(session.user.role==='admin'&&!j.approved?'<button class="primary" id="approve-job">批准此业务结论</button>':'')+(canRecompute?'<button class="button" id="recompute-job" data-job="'+j.id+'">按当前口径重算另存</button>':'')+'<p class="hint">重算会生成一条新任务，当前结果与历史分发简报不被改写。仅批准结果可进入定时分发档案。</p></section></div>'+
  '<section class="panel"><div class="section-title"><h2>原始汇总明细</h2><span>'+(r.table?.rows?.length||0)+' 行 · 全部展区</span></div>'+table(r.table?.columns||[],r.table?.rows||[])+'</section>';
}

export async function results(id){
 workspace.jobs=await jobs.list();const j=id?await jobs.get(id):(workspace.jobs.find(j=>j.id===workspace.selectedJob)||workspace.jobs[0]);
 if(j&&!workspace.jobs.some(x=>x.id===j.id))workspace.jobs.push(j);
 if(!j)return heading('04 / REVIEW','结果复核','尚无分析结果。')+'<div class="empty">先到分析工作台，选择批次并提交一次计算。<a href="#/workbench">前往工作台 ↗</a></div>';
 workspace.selectedJob=j.id;const r=j.result||{};
 return heading('04 / REVIEW','结果复核与业务解释',j.name,'<button class="button" id="refresh-results">刷新结果 ↻</button>')+'<div class="result-selector"><label>分析记录<select id="select-job">'+workspace.jobs.map(x=>'<option value="'+x.id+'" '+(x.id===j.id?'selected':'')+'>'+esc(x.name)+' · '+esc(x.status)+'</option>').join('')+'</select></label>'+status(j.status)+'<span>'+date(j.created_at)+'</span><span class="approval">'+(j.approved?'已获业务批准':'待负责人复核')+'</span>'+(r.rule_version?'<span>口径 '+esc(r.rule_version)+'</span>':'')+'</div>'+body(j);
}
export function bindResults(refresh){
 document.querySelector('#refresh-results')?.addEventListener('click',refresh);
 document.querySelector('#select-job')?.addEventListener('change',e=>{workspace.selectedJob=Number(e.target.value);location.hash='#/results/'+e.target.value;});
 document.querySelector('#approve-job')?.addEventListener('click',async()=>{try{await jobs.approve(workspace.selectedJob);notify('已批准，可创建分发计划');await refresh();}catch(e){notify(e.message,true);}});
 document.querySelector('#recompute-job')?.addEventListener('click',async e=>{const b=e.currentTarget;b.disabled=true;try{const j=await jobs.recompute(b.dataset.job);notify('已按当前口径另存为新任务，正在计算');workspace.selectedJob=j.id;const target='#/results/'+j.id;if(location.hash===target)await refresh();else location.hash=target;}catch(err){b.disabled=false;notify(err.message,true);}});
}
