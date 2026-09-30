"""Local personnel, certificate renewal and alert workflows."""
import hashlib
import io
import json
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import date
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import Response


DEFAULT_POLICY = {'version': 1, 'days': [10, 5]}


def initialize(a):
    with a.connection() as c:
        c.execute('CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('alerts', json.dumps(DEFAULT_POLICY)))


def load_rows(a, table):
    with a.connection() as c:
        return [json.loads(row[0]) for row in c.execute(f'SELECT payload FROM {table}')]


def save(c, table, value):
    if table == 'records':
        c.execute('UPDATE records SET payload=? WHERE id=?', (json.dumps(value, ensure_ascii=False), value['id']))
    else:
        c.execute(f'INSERT OR REPLACE INTO {table}(id,payload) VALUES (?,?)', (value['id'], json.dumps(value, ensure_ascii=False)))


def policy(a):
    with a.connection() as c:
        return json.loads(c.execute("SELECT payload FROM settings WHERE key='alerts'").fetchone()[0])


def check_version(value, body):
    if type(body.get('version')) is not int or body['version'] != value['version']:
        raise HTTPException(409, '数据已更新，请重新打开后操作')


def text(body, key, required=False, limit=200):
    value = body.get(key, '')
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise HTTPException(422, f'{key} 不能为空或超出长度限制')
    return value.strip()


async def object_body(request):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(422, '请求格式错误')
    if not isinstance(body, dict):
        raise HTTPException(422, '请求格式错误')
    return body


def historical_ids(a, records, today=None):
    today = today or date.today()
    lookup = {r['id']: r for r in records}
    result = set()
    templates = a.settings()['templates']
    for old in records:
        new = lookup.get(old.get('superseded_by'))
        if not new or new.get('replaces_id') != old['id'] or not old.get('person_id') or old.get('person_id') != new.get('person_id'):
            continue
        nv, ov = a.evaluate(new, templates), a.evaluate(old, templates)
        nf, of = nv['fields'], ov['fields']
        # Re-check dynamically: later edits/deletion must not hide the old risk.
        same = nv['type'] == ov['type'] and nf['operation']['value'] == of['operation']['value'] and nf['direction']['value'] == of['direction']['value']
        start = nf['valid_from']['value']
        try:
            valid = date.fromisoformat(nf['valid_to']['value']) > date.fromisoformat(of['valid_to']['value'])
            # For types without a printed period start, approval is the activation point.
            valid = valid and (not start or date.fromisoformat(start) <= today)
        except ValueError:
            valid = False
        if new.get('job_status') == 'done' and nv['status'] == 'approved' and same and valid:
            result.add(old['id'])
    return result


def sync_alerts(a, today=None):
    today = today or date.today()
    with a.LOCK:
        records = a.all_records()
        historical = historical_ids(a, records, today)
        people = {p['id']: p for p in load_rows(a, 'people')}
        existing = {x['id']: x for x in load_rows(a, 'alerts')}
        thresholds = sorted(policy(a)['days'], reverse=True)
        templates = a.settings()['templates']
        desired = {}
        for r in records:
            if r['id'] in historical or r['job_status'] != 'done':
                continue
            v = a.evaluate(r, templates, today=today)
            person = people.get(r.get('person_id'), {})
            for kind, due in [('expiry', v['fields']['valid_to']['value']), ('review', v['review_info']['next_due_date'] if v['type'] == 'electrical' else '')]:
                if kind == 'review' and v['type'] != 'electrical':
                    continue
                # An unconfirmed date produces a verification task, never assumed safe.
                if kind == 'expiry' and v['fields']['valid_to']['state'] != 'extracted':
                    due = ''
                try:
                    days = (date.fromisoformat(due) - today).days
                except ValueError:
                    due, days = '', None
                if days is not None and days > max(thresholds):
                    continue
                stage = 'verify' if days is None else 'overdue' if days < 0 else 'due_today' if days == 0 else f'd{min(d for d in thresholds if days <= d)}'
                aid = hashlib.sha256(f'{r["id"]}|{kind}|{due}'.encode()).hexdigest()[:32]
                old = existing.get(aid)
                values = dict(record_id=r['id'], person_id=person.get('id'), person_name=person.get('name') or v['fields']['person_name']['value'] or '未识别姓名', project=person.get('project', ''), suggested_owner=person.get('officer', ''), kind=kind, due=due, stage=stage, days=days, active=True)
                task = dict(old or dict(id=aid, version=0, status='pending', owner=person.get('officer', ''), note='', created_at=a.now(), history=[]))
                if old and (old.get('stage') != stage or not old.get('active')):
                    task['status'] = 'pending'
                    task['history'].append({'at': a.now(), 'action': '风险变化，重新待处理', 'stage': stage})
                task.update(values)
                desired[aid] = task
        for aid, old in existing.items():
            if aid not in desired:
                task = dict(old)
                if task.get('active'):
                    task.update(active=False, status='resolved')
                    task['history'].append({'at': a.now(), 'action': '风险条件已变化或证书已归档/删除，系统关闭'})
                desired[aid] = task
        with a.connection() as c:
            for aid, task in desired.items():
                if task != existing.get(aid):
                    task['version'] += 1
                    save(c, 'alerts', task)
        return list(desired.values())


def register(a):
    app = a.app

    @app.get('/api/management')
    def management():
        with a.LOCK:
            tasks = sync_alerts(a)
            records = a.all_records()
            historical = historical_ids(a, records)
            deleted = [r for r in load_rows(a, 'records') if r.get('deleted_at')]
            return {'people': load_rows(a, 'people'), 'policy': policy(a), 'tasks': sorted(tasks, key=lambda t: (not t['active'], t['due'] or '0000', t['id'])), 'historical_ids': sorted(historical),
                    'trash': [{'id': r['id'], 'version': r['version'], 'filename': r['filename'], 'deleted_at': r['deleted_at'], 'person_name': a.evaluate(r)['fields']['person_name']['value']} for r in deleted]}

    @app.post('/api/people')
    async def create_person(request: Request):
        return await upsert_person(None, request)

    @app.put('/api/people/{pid}')
    async def upsert_person(pid: str, request: Request):
        body = await object_body(request)
        with a.LOCK:
            old = next((p for p in load_rows(a, 'people') if p['id'] == pid), None)
            if pid and not old:
                raise HTTPException(404, '人员档案不存在')
            if old:
                check_version(old, body)
            p = {'id': pid or uuid.uuid4().hex, 'version': (old or {}).get('version', 0) + 1,
                 **{k: text(body, k, k == 'name', 80) for k in ['name', 'project', 'role', 'officer']}, 'availability': text(body, 'availability', True)}
            if p['availability'] not in ['onsite', 'available', 'away']:
                raise HTTPException(422, '人员状态不合法')
            with a.connection() as c:
                save(c, 'people', p)
            a.audit(None, 'person_saved', {'before': old, 'after': p})
            return p

    @app.post('/api/records/{rid}/person')
    async def associate(rid: str, request: Request):
        body = await object_body(request)
        with a.LOCK:
            r = a.read(rid)
            check_version(r, body)
            if r['job_status'] in ['queued', 'running']:
                raise HTTPException(409, '请等待识别完成')
            if r.get('superseded_by') or r.get('replaces_id'):
                raise HTTPException(409, '换证链已关联，请先解除换证关联再更改人员')
            pid = text(body, 'person_id')
            if pid and not any(p['id'] == pid for p in load_rows(a, 'people')):
                raise HTTPException(404, '人员档案不存在')
            note = text(body, 'note', True, 500)
            previous = r.get('person_id')
            r.update(person_id=pid or None, version=r['version'] + 1)
            a.write(r)
            a.audit(rid, 'person_linked', {'before': previous, 'after': pid, 'note': note})
            return a.present(r)

    @app.post('/api/records/{rid}/renewal')
    async def renewal(rid: str, request: Request):
        body = await object_body(request)
        with a.LOCK:
            old = a.read(rid)
            check_version(old, body)
            new = a.read(text(body, 'new_id', True))
            if body.get('new_version') != new['version']:
                raise HTTPException(409, '新证已更新，请重新选择')
            note = text(body, 'note', True, 500)
            if old['id'] == new['id'] or old['job_status'] != 'done' or new['job_status'] != 'done':
                raise HTTPException(422, '请选择两张不同的已识别证书')
            if not old.get('person_id') or old.get('person_id') != new.get('person_id'):
                raise HTTPException(422, '请先将新旧证书关联到同一个人员档案')
            if old.get('superseded_by') or new.get('replaces_id') or new.get('superseded_by'):
                raise HTTPException(409, '证书已有关联，请勿重复或形成循环')
            ov, nv = a.present(old), a.present(new)
            if ov['type'] == 'unknown' or ov['type'] != nv['type'] or any(ov['fields'][k]['value'] != nv['fields'][k]['value'] for k in ['operation', 'direction']):
                raise HTTPException(422, '新旧证书须为同一类型和作业项目/认证方向')
            try:
                if date.fromisoformat(nv['fields']['valid_to']['value']) <= date.fromisoformat(ov['fields']['valid_to']['value']):
                    raise ValueError()
            except ValueError:
                raise HTTPException(422, '请先核对到期日，新证有效期须晚于旧证')
            old.update(superseded_by=new['id'], version=old['version'] + 1)
            new.update(replaces_id=old['id'], version=new['version'] + 1)
            with a.connection() as c:
                save(c, 'records', old)
                save(c, 'records', new)
            a.audit(rid, 'renewal_linked', {'new_id': new['id'], 'note': note})
            return {'linked': True}

    @app.post('/api/records/{rid}/unlink-renewal')
    async def unlink_renewal(rid: str, request: Request):
        body = await object_body(request)
        with a.LOCK:
            old = a.read(rid)
            check_version(old, body)
            linked = old.get('superseded_by')
            new = next((r for r in load_rows(a, 'records') if r['id'] == linked), None)
            if not new:
                raise HTTPException(422, '此记录没有后续新证')
            note = text(body, 'note', True, 500)
            old.pop('superseded_by', None)
            new.pop('replaces_id', None)
            old['version'] += 1
            new['version'] += 1
            with a.connection() as c:
                save(c, 'records', old)
                save(c, 'records', new)
            a.audit(rid, 'renewal_unlinked', {'new_id': linked, 'note': note})
            return {'unlinked': True}

    @app.put('/api/alert-policy')
    async def update_policy(request: Request):
        body = await object_body(request)
        with a.LOCK:
            old = policy(a)
            check_version(old, body)
            days = body.get('days')
            if not isinstance(days, list) or not 1 <= len(days) <= 6 or any(type(d) is not int or not 1 <= d <= 365 for d in days) or len(set(days)) != len(days):
                raise HTTPException(422, '提前天数须为 1–365 的不重复整数，最多 6 个')
            new = {'version': old['version'] + 1, 'days': sorted(days, reverse=True)}
            with a.connection() as c:
                c.execute("UPDATE settings SET payload=? WHERE key='alerts'", (json.dumps(new),))
            a.audit(None, 'alert_policy_updated', {'before': old, 'after': new})
            sync_alerts(a)
            return new

    @app.patch('/api/alerts/{aid}')
    async def update_alert(aid: str, request: Request):
        body = await object_body(request)
        with a.LOCK:
            task = next((t for t in sync_alerts(a) if t['id'] == aid), None)
            if not task:
                raise HTTPException(404, '任务不存在')
            check_version(task, body)
            if not task['active']:
                raise HTTPException(409, '风险条件已变化，请刷新任务')
            status = text(body, 'status', True)
            if status not in ['pending', 'processing', 'resolved']:
                raise HTTPException(422, '任务状态不合法')
            owner, note = text(body, 'owner', True, 80), text(body, 'note', True, 1000)
            task.update(status=status, owner=owner, note=note, version=task['version'] + 1)
            task['history'].append({'at': a.now(), 'action': status, 'owner': owner, 'note': note})
            with a.connection() as c:
                save(c, 'alerts', task)
            a.audit(task['record_id'], 'alert_handled', {'id': aid, 'owner': owner, 'status': status, 'note': note})
            return task

    @app.post('/api/trash/restore')
    async def restore(request: Request):
        body = await object_body(request)
        items = body.get('records')
        if not isinstance(items, list) or not 1 <= len(items) <= 500 or any(not isinstance(i, dict) or not isinstance(i.get('id'), str) for i in items) or len({i['id'] for i in items}) != len(items):
            raise HTTPException(422, '请选择 1–500 条不重复记录')
        with a.LOCK:
            rows = {r['id']: r for r in load_rows(a, 'records')}
            restored = []
            for item in items:
                r = rows.get(item['id'])
                if not r or not r.get('deleted_at'):
                    raise HTTPException(409, '记录已恢复或不存在，本次没有恢复任何记录')
                check_version(r, item)
                r.pop('deleted_at')
                r['version'] += 1
                restored.append(r)
            with a.connection() as c:
                for r in restored:
                    save(c, 'records', r)
                    c.execute('INSERT INTO audit(record_id,at,action,payload) VALUES (?,?,?,?)', (r['id'], a.now(), 'record_restored', json.dumps({'version': r['version']})))
            return {'restored': len(restored)}

    @app.post('/api/backup')
    def backup():
        with a.LOCK:
            if a.OCR_PENDING or any(r['job_status'] in ['queued', 'running'] for r in a.all_records()):
                raise HTTPException(409, '识别任务完成后再备份')
            output = io.BytesIO()
            with tempfile.TemporaryDirectory(prefix='cert-backup-') as folder:
                target = Path(folder) / 'demo.sqlite3'
                with a.connection() as source:
                    dest = sqlite3.connect(target)
                    try:
                        source.backup(dest)
                    finally:
                        dest.close()
                contents = {'demo.sqlite3': target.read_bytes()}
                image_paths = {}
                for r in load_rows(a, 'records'):
                    for key in ['image_path', 'display_path']:
                        if not r.get(key):
                            continue
                        path = Path(r[key]).resolve()
                        try:
                            rel = path.relative_to((a.DATA / 'images').resolve())
                        except ValueError:
                            raise HTTPException(409, '图片路径不在数据目录内，不能生成完整备份')
                        if not path.is_file():
                            raise HTTPException(409, f'证书图片缺失：{r["filename"]}')
                        archive_name = 'images/' + rel.as_posix()
                        contents[archive_name] = path.read_bytes()
                        image_paths[r[key]] = archive_name
                manifest = {'format': 1, 'created_at': a.now(), 'image_paths': image_paths, 'files': {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}}
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
                    for name, content in contents.items():
                        z.writestr(name, content)
                    z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
            return Response(output.getvalue(), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="certificate-backup.zip"'})
