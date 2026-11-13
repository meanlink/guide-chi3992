import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records),
            'checksum':d.checksum, 'created_at':d.created_at,
            'revisions':d.revisions or {}, 'supplement_count':getattr(d,'supplement_count',0) or 0}
def supplement_dict(s):
    return {'id':s.id, 'dataset_id':int(s.dataset_id), 'source':s.source,
            'status':s.status, 'summary':s.summary, 'created_by':s.created_by,
            'created_at':s.created_at, 'uploaded_count':len(s.uploaded_rows or [])}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','records_snapshot','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
