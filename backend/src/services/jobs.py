import time
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services.business import metadata, RULE_VERSION
def _params(values, strict=True):
    allowed={p['key']:p for p in metadata().get('parameters',[])}
    unknown=set(values)-set(allowed)
    if unknown and strict: raise HTTPException(422,'包含未知分析参数')
    params={k:p['default'] for k,p in allowed.items()}
    params.update({k:v for k,v in values.items() if k in allowed})
    for key,p in allowed.items():
        v=params[key]
        if p['type']=='number':
            try:
                v=float(v)
                if not (p.get('min',-1e9)<=v<=p.get('max',1e9)): raise ValueError()
                params[key]=v
            except (ValueError,TypeError): raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options',[])]:
            raise HTTPException(422,f'{p["label"]} 不是有效选项')
    return params
def create(db, data, user):
    if not db.get(Dataset,data.dataset_id): raise HTTPException(404,'数据批次不存在')
    j=Job(name=data.name, dataset_id=data.dataset_id, params=_params(data.params), created_by=user.id, created_at=time.time(), status='queued')
    db.add(j); db.flush()
    return j
def recompute(db, source, data, user):
    """按当前口径重算另存：复用原批次与参数，形成新的任务，原任务与历史下载保持不变。"""
    if not source: raise HTTPException(404,'原分析任务不存在')
    if source.status!='completed': raise HTTPException(409,'仅已完成的分析可以按新口径重算')
    if not db.get(Dataset,source.dataset_id): raise HTTPException(404,'原数据批次不存在')
    name=((data.name if data else None) or f"{source.name} · 重算（{RULE_VERSION}）").strip()
    if len(name)<2: raise HTTPException(422,'重算任务名称至少需要两个字符')
    j=Job(name=name[:160], dataset_id=source.dataset_id, params=_params(dict(source.params or {}), strict=False), created_by=user.id, created_at=time.time(), status='queued')
    db.add(j); db.flush()
    return j
def enqueue(job_id):
    try:
        r=Redis.from_url(REDIS_URL); r.rpush('analysis:queue',job_id); r.close()
    except Exception:
        pass # SQL queued status is the durable fallback
