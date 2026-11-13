from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Dataset
from src.schemas.dataset import DatasetInput, SupplementInput
from src.middlewares.auth import current_user, can_write
from src.services import datasets
from src.services.datasets import SupplementConflict
from src.services.audit import record
from src.utils.serialization import dataset_dict, supplement_dict
router=APIRouter(prefix='/datasets')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [dataset_dict(d) for d in db.scalars(select(Dataset).order_by(Dataset.id.desc()))]
@router.post('',status_code=201)
def create(data:DatasetInput,db=Depends(get_db),u=Depends(can_write)):
    d=datasets.create(db,data); record(db,u.email,'dataset.create',{'id':d.id,'rows':len(d.records)})
    db.commit(); return dataset_dict(d)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    return {**dataset_dict(d),'records':d.records,'revisions':d.revisions,
            'supplements':[supplement_dict(s) for s in datasets.supplement_history(db,id)]}
@router.post('/{id}/supplement/preview')
def preview_supplement(id:int,data:SupplementInput,db=Depends(get_db),u=Depends(can_write)):
    # 核对只读：即使存在冲突也返回 200 与逐行结果，由接入页展示，不产生任何写入。
    try:
        _,summary=datasets.supplement(db,id,data,u,persist=False)
    except SupplementConflict as exc:
        summary=exc.detail['reconciliation']
    return summary
@router.post('/{id}/supplement',status_code=201)
def apply_supplement(id:int,data:SupplementInput,db=Depends(get_db),u=Depends(can_write)):
    d,summary=datasets.supplement(db,id,data,u,persist=True)
    record(db,u.email,'dataset.supplement',
           {'id':d.id,'supplement_id':summary.get('supplement_id'),
            'added':summary['added'],'corrected':summary['corrected'],
            'ignored':summary['ignored'],'rows':len(d.records)})
    db.commit()
    return {'dataset':dataset_dict(d),'reconciliation':summary}
@router.get('/{id}/supplements')
def supplements(id:int,db=Depends(get_db),u=Depends(current_user)):
    return [supplement_dict(s) for s in datasets.supplement_history(db,id)]
