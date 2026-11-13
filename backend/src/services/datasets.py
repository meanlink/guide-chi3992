import math
import time
from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset, DatasetSupplement
from src.services.business import metadata
from src.utils.serialization import checksum

BUSINESS_KEYS = [c['key'] for c in metadata()['columns']]
CONTENT_KEYS = [k for k in BUSINESS_KEYS if k != 'record']
REVISION_KEY = 'revision'
FIRST_REVISION = 1


class SupplementConflict(HTTPException):
    """同号同版内容冲突：整批不落入，携带逐行核对结果。"""
    def __init__(self, summary):
        super().__init__(422, {'message': '存在同号同版内容冲突，整批未落入，请修正后重新上传', 'reconciliation': summary})


def _validate_rows(rows):
    """与数据接入一致的字段级校验，返回规整后的行（数值转 float，修订号转 int）。"""
    cleaned = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise HTTPException(422, f'第 {index + 1} 行必须为记录对象')
        item = dict(row)
        for c in metadata()['columns']:
            value = item.get(c['key'])
            if value is None or value == '':
                raise HTTPException(422, f'第 {index + 1} 行缺少字段 {c["label"]}')
            if c['type'] == 'number':
                try:
                    if isinstance(value, bool) or not math.isfinite(float(value)):
                        raise ValueError()
                    item[c['key']] = float(value)
                except (TypeError, ValueError, OverflowError):
                    raise HTTPException(422, f'第 {index + 1} 行 {c["label"]} 必须为有限数值')
        item[REVISION_KEY] = _revision_of(item, index + 1)
        cleaned.append(item)
    return cleaned


def _revision_of(row, line_no):
    raw = row.get(REVISION_KEY, FIRST_REVISION)
    if raw is None or raw == '':
        return FIRST_REVISION
    try:
        if isinstance(raw, bool):
            raise ValueError()
        rev = int(raw)
        if float(raw) != rev or rev < 1:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(422, f'第 {line_no} 行修订号必须为不小于 1 的整数')
    return rev


def _content_of(row):
    """参与同号同版内容比较的业务内容（不含记录编号与修订号）。

    数值统一转 float 后比较，避免 10 与 10.0 这类纯表示差异被误判为冲突。
    """
    content = {}
    for k in CONTENT_KEYS:
        value = row.get(k)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = float(value)
        content[k] = value
    return content


def _same_content(a, b):
    return checksum(_content_of(a)) == checksum(_content_of(b))


def _canonical(row):
    """落库与指纹只保留业务字段，修订号由批次 revisions 映射维护。"""
    return {k: row[k] for k in BUSINESS_KEYS}


def reconcile(dataset, incoming):
    """
    以记录编号 + 修订号对补报行做核对（不写库）。
    - added 新增：批次中不存在的记录编号
    - corrected 更正：修订号高于批次内现版
    - ignored 忽略：重复补报（同号同版同内容）或旧修订（不覆盖新值）
    - conflict 冲突：同号同版但内容不一致 → 整批不落入
    批次内部重复编号同样按上述口径处理，冲突也阻断整批。
    """
    rows = _validate_rows(incoming)
    current = {r['record']: r for r in dataset.records}
    revisions = dict(dataset.revisions or {})
    pending = {}  # 本批已处理编号 -> (行, 核对结果)
    results = []
    conflicts = []

    def classify(row, line_no):
        key, rev = row['record'], row[REVISION_KEY]
        if key in pending:
            prev_row, prev_status = pending[key]
            if prev_row[REVISION_KEY] != rev:
                reason = f'同一批次内记录 {key} 出现多个修订号（{prev_row[REVISION_KEY]} 与 {rev}）'
            elif _same_content(prev_row, row):
                return {'line': line_no, 'record': key, 'revision': rev, 'outcome': 'ignored',
                        'reason': '同一批次内重复出现，内容一致，仅保留首条'}
            else:
                reason = f'同一批次内记录 {key} 同号同版（修订号 {rev}）内容不一致'
            return {'line': line_no, 'record': key, 'revision': rev, 'outcome': 'conflict', 'reason': reason}
        if key not in current:
            outcome, reason = 'added', f'新记录编号，按修订号 {rev} 新增'
        else:
            current_rev = int(revisions.get(key, FIRST_REVISION))
            if rev < current_rev:
                outcome, reason = 'ignored', f'现版为修订号 {current_rev}，旧修订（{rev}）不覆盖新值'
            elif rev == current_rev:
                if _same_content(current[key], row):
                    outcome, reason = 'ignored', f'与修订号 {rev} 现版内容一致，重复补报不计入'
                else:
                    outcome, reason = 'conflict', f'同号同版（修订号 {rev}）内容与已入库记录不一致'
            else:
                outcome, reason = 'corrected', f'修订号 {current_rev} → {rev}，以新内容更正'
        return {'line': line_no, 'record': key, 'revision': rev, 'outcome': outcome, 'reason': reason}

    for line_no, row in enumerate(rows, start=1):
        item = classify(row, line_no)
        if item['outcome'] == 'conflict':
            conflicts.append(item)
        pending.setdefault(row['record'], (row, item['outcome']))
        results.append(item)

    summary = {
        'total': len(rows),
        'added': sum(1 for x in results if x['outcome'] == 'added'),
        'corrected': sum(1 for x in results if x['outcome'] == 'corrected'),
        'ignored': sum(1 for x in results if x['outcome'] == 'ignored'),
        'conflict': len(conflicts),
        'items': results,
        'conflicts': conflicts,
        'ok': not conflicts,
    }
    return rows, summary


def _apply(dataset, rows, summary):
    """根据核对结果把新增/更正落入原批次；忽略与冲突不改变数据。"""
    updated = list(dataset.records)  # 整体重赋，确保 JSON 列变更被持久化
    revisions = dict(dataset.revisions or {})
    seen = set()
    for item in summary['items']:
        if item['outcome'] not in ('added', 'corrected'):
            continue
        key = item['record']
        if key in seen:  # 批内重复的同号行只落一次
            continue
        seen.add(key)
        row = next(r for r in rows if r['record'] == key)
        canonical = _canonical(row)
        if item['outcome'] == 'added':
            updated.append(canonical)
        else:
            index = next(i for i, r in enumerate(updated) if r['record'] == key)
            updated[index] = canonical
        revisions[key] = item['revision']
    dataset.records = updated
    dataset.revisions = revisions
    dataset.checksum = checksum(updated)
    dataset.supplement_count = int(dataset.supplement_count or 0) + 1


def create(db, data):
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name == name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    rows = _validate_rows(data.records)
    keys = [r['record'] for r in rows]
    if len(set(keys)) != len(keys):
        dup = sorted({k for k in keys if keys.count(k) > 1})
        raise HTTPException(422, f'记录编号在批次内重复：{"、".join(dup[:5])}')
    records = [_canonical(r) for r in rows]
    revisions = {r['record']: r[REVISION_KEY] for r in rows}
    d = Dataset(name=name, source=data.source, records=records, revisions=revisions,
                checksum=checksum(records), created_at=time.time(), supplement_count=0)
    db.add(d)
    db.flush()
    return d


def supplement(db, dataset_id, data, user, persist):
    """
    persist=False 仅核对（dry-run）；persist=True 原子落入。
    冲突时不修改批次，并保留一条 rejected 留痕；失败重试不影响既有任务与结果。
    """
    d = db.get(Dataset, dataset_id)
    if not d:
        raise HTTPException(404, '数据批次不存在')
    rows, summary = reconcile(d, data.records)
    if not summary['ok']:
        if persist:
            # 拒收留痕独立提交：批次数据零变更，冲突原因仍可追溯，且失败重试不受影响。
            rejected = DatasetSupplement(
                dataset_id=d.id, source=data.source, uploaded_rows=data.records,
                status='rejected', summary=summary, created_by=getattr(user, 'email', str(user)),
                created_at=time.time())
            db.add(rejected)
            db.commit()
            db.refresh(d)
            summary['supplement_id'] = rejected.id
        raise SupplementConflict(summary)
    if persist:
        before_rows = len(d.records)
        _apply(d, rows, summary)
        summary['rows_before'] = before_rows
        summary['rows_after'] = len(d.records)
        log = DatasetSupplement(
            dataset_id=d.id, source=data.source, uploaded_rows=data.records,
            status='applied', summary=summary, created_by=getattr(user, 'email', str(user)),
            created_at=time.time())
        db.add(log)
        db.flush()
        summary['supplement_id'] = log.id
        return d, summary
    return d, summary


def supplement_history(db, dataset_id):
    if not db.get(Dataset, dataset_id):
        raise HTTPException(404, '数据批次不存在')
    logs = db.scalars(
        select(DatasetSupplement)
        .where(DatasetSupplement.dataset_id == dataset_id)
        .order_by(DatasetSupplement.id.desc())
    ).all()
    return logs
