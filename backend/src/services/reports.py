import time, os, csv, io, hashlib, json
from fastapi import HTTPException
from src.models import Job, Report, Delivery
from src.config.settings import ARTIFACT_DIR
def create(db, data):
    j=db.get(Job,data.job_id)
    if not j or j.status!='completed' or not j.approved:
        raise HTTPException(409,'请先选择已完成且获批准的分析结果')
    r=Report(name=data.name, job_id=j.id, destination=data.destination, interval_seconds=data.interval_seconds, next_run=time.time()+data.delay_seconds, enabled=True)
    db.add(r); db.flush()
    return r
def _safe(v):
    if isinstance(v,(int,float)) and not isinstance(v,bool): return v
    text=str(v)
    return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
def _section(writer, title, table):
    writer.writerow([])
    writer.writerow([_safe(title)])
    cols=table.get('columns',[])
    writer.writerow([_safe(c['label']) for c in cols])
    for row in table.get('rows',[]): writer.writerow([_safe(row.get(c['key'],'')) for c in cols])
def deliver(db, report):
    j=db.get(Job,report.job_id)
    if not j or not j.approved: return
    out=io.StringIO()
    out.write('﻿')
    result=j.result or {}
    adjustment=result.get('adjustment') or {}
    writer=csv.writer(out)
    table=result.get('table',{})
    if not adjustment:
        # 旧口径任务继续输出原始格式，历史简报与既有下游消费不被改写。
        cols=table.get('columns',[])
        writer.writerow([_safe(c['label']) for c in cols])
        for row in table.get('rows',[]): writer.writerow([_safe(row.get(c['key'],'')) for c in cols])
        return _store(db,report,j,out.getvalue().encode('utf-8'))
    pooled=adjustment.get('pooled') or {}
    adjusted=adjustment.get('adjusted') or {}
    visitors=adjustment.get('visitors') or {}
    included=visitors.get('included') or {}
    excluded=visitors.get('excluded') or {}
    overall=visitors.get('overall') or {}
    writer.writerow([_safe('口径版本'),_safe(adjustment.get('rule_version') or result.get('rule_version') or '')])
    writer.writerow([_safe('校正方法'),_safe(adjustment.get('method',''))])
    writer.writerow([_safe('校正结论'),_safe(adjustment.get('summary',''))])
    writer.writerow([_safe('纳入/排除'),_safe(f"纳入 {len(adjustment.get('included_zones') or [])} 个展区 · {included.get('total',0)} 人；排除 {len(adjustment.get('excluded_zones') or [])} 个展区 · {excluded.get('total',0)} 人；全部 {overall.get('total',0)} 人")])
    writer.writerow([_safe('方向核对'),_safe(f"原始汇总 B−A {pooled.get('diff_pp','')} 个百分点（{pooled.get('direction','')}）；校正后 B−A {adjusted.get('diff_pp','')} 个百分点（{adjusted.get('direction','')}）；{'方向反转' if adjustment.get('direction_reversed') else '方向未反转'}")])
    cols=table.get('columns',[])
    writer.writerow([])
    writer.writerow([_safe('原始汇总明细（全部展区）')])
    writer.writerow([_safe(c['label']) for c in cols])
    for row in table.get('rows',[]): writer.writerow([_safe(row.get(c['key'],'')) for c in cols])
    if adjustment.get('table'):
        _section(writer,'校正纳入/排除核对',adjustment['table'])
    return _store(db,report,j,out.getvalue().encode('utf-8'))
def _store(db,report,j,data):
    delivery=Delivery(report_id=report.id, created_at=time.time(), checksum=hashlib.sha256(data).hexdigest(), filename='', destination=report.destination)
    db.add(delivery); db.flush()
    delivery.filename=f'report-{report.id}-delivery-{delivery.id}.csv'
    os.makedirs(ARTIFACT_DIR,exist_ok=True)
    with open(os.path.join(ARTIFACT_DIR,delivery.filename),'wb') as f:f.write(data)
    with open(os.path.join(ARTIFACT_DIR,delivery.filename+'.json'),'w') as f: json.dump({'job':j.name,'params':j.params,'result':j.result,'checksum':delivery.checksum},f,ensure_ascii=False,allow_nan=False)
    report.next_run=time.time()+report.interval_seconds
    return delivery
