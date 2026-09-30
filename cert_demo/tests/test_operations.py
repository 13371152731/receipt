import copy
from contextlib import closing
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from cert_demo.extraction import extract
from cert_demo import operations
from cert_demo.restore_backup import restore_backup


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cert-ops-test-')
        os.environ['CERT_DEMO_DATA'] = self.temp.name
        from cert_demo import app
        from fastapi.testclient import TestClient
        self.a = app
        self.previous = app.DATA, app.DB, app.OCR_PENDING
        app.OCR_PENDING = 0
        app.DATA = Path(self.temp.name)
        app.DB = app.DATA / 'demo.sqlite3'
        (app.DATA / 'images').mkdir()
        app.initialize()
        self.client = TestClient(app.app, headers={'X-Demo-Request': '1'})
        raw = json.loads((ROOT.parent / 'ocr_benchmark/gpu_standard/ocr_results.json').read_text(encoding='utf-8'))['T07'][0]
        image = app.DATA / 'images/fixture.png'
        from PIL import Image
        Image.new('RGB', (20, 20), 'white').save(image)
        self.record = dict(id='old', created_at=app.now(), filename='测试证书.png', sample=None, sha256='fixture', image_path=str(image), display_path=None,
                           job_status='done', parsed=extract(raw), raw=raw, corrections={'valid_to': (date.today()+timedelta(days=8)).isoformat()}, confirmed=[], type_override=None,
                           ocr_s=.3, version=1, reviewed_at=app.now(), reviewer='测试审核员', note='')
        app.write(self.record)

    def tearDown(self):
        self.client.close()
        self.a.DATA, self.a.DB, self.a.OCR_PENDING = self.previous
        self.temp.cleanup()

    def person(self, name='同名人员'):
        response = self.client.post('/api/people', json=dict(name=name, project='测试项目', role='电工', officer='测试安全员', availability='onsite'))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def link(self, rid, pid):
        r = self.a.read(rid)
        response = self.client.post(f'/api/records/{rid}/person', json=dict(version=r['version'], person_id=pid, note='已核对员工信息'))
        self.assertEqual(response.status_code, 200, response.text)

    def renew_fixture(self):
        p = self.person()
        self.link('old', p['id'])
        new = copy.deepcopy(self.record)
        new.update(id='new', corrections={'valid_to': (date.today()+timedelta(days=700)).isoformat()}, reviewed_at=None)
        self.a.write(new)
        self.link('new', p['id'])
        old, new = self.a.read('old'), self.a.read('new')
        response = self.client.post('/api/records/old/renewal', json=dict(version=old['version'], new_id='new', new_version=new['version'], note='核对换证资料'))
        self.assertEqual(response.status_code, 200, response.text)

    def test_same_name_people_separate_and_versions(self):
        p, q = self.person(), self.person()
        self.assertNotEqual(p['id'], q['id'])
        self.link('old', p['id'])
        rows = self.client.get('/api/state').json()['records']
        self.assertEqual(rows[0]['person']['id'], p['id'])
        bad = self.client.put('/api/people/'+p['id'], json={**p, 'version': 0})
        self.assertEqual(bad.status_code, 409)
        self.assertEqual(self.client.post('/api/records/old/person', json={'version': 1, 'person_id': q['id'], 'note': 'test'}).status_code, 409)

    def test_alert_dedup_close_escalate_and_reopen(self):
        first = operations.sync_alerts(self.a)
        self.assertEqual(len(first), 1)
        task = first[0]
        self.assertEqual(task['stage'], 'd10')
        self.assertEqual(operations.sync_alerts(self.a)[0]['version'], task['version'])
        self.assertEqual(self.client.patch('/api/alerts/'+task['id'], json={**task, 'status':'resolved','owner':'安全员','note':''}).status_code,422)
        response = self.client.patch('/api/alerts/'+task['id'], json={**task, 'status':'resolved','owner':'安全员','note':'已停止该人员作业，办理续证'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(operations.sync_alerts(self.a)[0]['status'], 'resolved')
        escalated = operations.sync_alerts(self.a, date.today()+timedelta(days=4))[0]
        self.assertEqual(escalated['id'], task['id'])
        self.assertEqual(escalated['status'], 'pending')
        self.assertEqual(escalated['stage'], 'd5')

    def test_policy_and_missing_date_verification(self):
        response = self.client.put('/api/alert-policy', json={'version':1,'days':[3]})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(t['active'] for t in operations.sync_alerts(self.a)))
        self.assertEqual(self.client.get('/api/state').json()['records'][0]['risk']['kind'], 'within')
        self.assertEqual(self.client.put('/api/alert-policy', json={'version':2,'days':[True]}).status_code,422)
        r = self.a.read('old');r['corrections']['valid_to']='';self.a.write(r)
        active = [t for t in operations.sync_alerts(self.a) if t['active']]
        self.assertEqual(active[0]['stage'], 'verify')

    def test_renewal_only_after_approval_and_reverts_when_deleted(self):
        self.renew_fixture()
        self.assertEqual(operations.historical_ids(self.a, self.a.all_records()), set())
        new = self.a.read('new')
        response = self.client.patch('/api/records/new', json={'version':new['version'],'approve':True,'reviewer':'测试审核员'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(operations.historical_ids(self.a, self.a.all_records()), {'old'})
        self.assertFalse(any(t['active'] and t['record_id']=='old' for t in operations.sync_alerts(self.a)))
        new = self.a.read('new')
        self.client.request('DELETE','/api/records/new',json={'version':new['version']})
        self.assertEqual(operations.historical_ids(self.a, self.a.all_records()), set())
        self.assertTrue(any(t['active'] and t['record_id']=='old' for t in operations.sync_alerts(self.a)))

    def test_renewal_cross_person_rejected_unlink_restores_editability(self):
        self.renew_fixture()
        old = self.a.read('old')
        self.assertEqual(self.client.post('/api/records/old/person',json={'version':old['version'],'person_id':'','note':'移除'}).status_code,409)
        response = self.client.post('/api/records/old/unlink-renewal',json={'version':old['version'],'note':'测试解除'})
        self.assertEqual(response.status_code,200)
        self.link('new',self.person('另一位人员')['id'])
        old,new=self.a.read('old'),self.a.read('new')
        response=self.client.post('/api/records/old/renewal',json={'version':old['version'],'new_id':'new','new_version':new['version'],'note':'错误关联'})
        self.assertEqual(response.status_code,422)
        self.assertNotIn('superseded_by',self.a.read('old'))

    def test_new_certificate_expiry_does_not_reactivate_historical_old(self):
        self.renew_fixture()
        new=self.a.read('new');new['reviewed_at']=self.a.now();self.a.write(new)
        future=date.today()+timedelta(days=800)
        self.assertEqual(operations.historical_ids(self.a,self.a.all_records(),future),{'old'})
        tasks=operations.sync_alerts(self.a,future)
        self.assertEqual([t['record_id'] for t in tasks if t['active']],['new'])

    def test_future_new_certificate_not_yet_effective(self):
        self.renew_fixture()
        new=self.a.read('new');new['reviewed_at']=self.a.now()
        # Electrical valid_from is an applicable field, unlike HCIP.
        new['type_override']='electrical'
        new['corrections'].update(person_name='测试人员',certificate_no='T000000199103120015',category='电工作业',operation='低压电工作业',initial_issue_date='2020-01-01',valid_from=(date.today()+timedelta(days=2)).isoformat(),review_date='2027-09-19')
        new['confirmed']=[k for k,_ in self.a.FIELD_DEFS];self.a.write(new)
        old=self.a.read('old');old['type_override']='electrical';old['corrections']={**new['corrections'],'valid_from':'2020-01-01','valid_to':(date.today()+timedelta(days=8)).isoformat()};old['confirmed']=new['confirmed'];self.a.write(old)
        self.assertEqual(operations.historical_ids(self.a,self.a.all_records()),set())

    def test_restore_all_or_nothing_and_preserves_data(self):
        new=copy.deepcopy(self.record);new['id']='second';self.a.write(new)
        self.client.post('/api/records/batch-delete',json={'records':[{'id':rid,'version':1} for rid in ['old','second']]})
        response=self.client.post('/api/trash/restore',json={'records':[{'id':'old','version':2},{'id':'second','version':1}]})
        self.assertEqual(response.status_code,409)
        self.assertEqual(len(self.a.all_records()),0)
        response=self.client.post('/api/trash/restore',json={'records':[{'id':rid,'version':2} for rid in ['old','second']]})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(self.a.all_records()),2)
        self.assertEqual(self.a.read('old')['corrections'],self.record['corrections'])
        self.assertEqual(self.a.read('old')['reviewed_at'],self.record['reviewed_at'])

    def test_backup_restore_validates_images_and_never_overwrites(self):
        p=self.person();self.link('old',p['id']);operations.sync_alerts(self.a)
        response=self.client.post('/api/backup')
        self.assertEqual(response.status_code,200,response.text if response.status_code!=200 else '')
        archive=self.a.DATA/'test.zip';archive.write_bytes(response.content)
        target=self.a.DATA/'restored'
        restore_backup(archive,target)
        with closing(sqlite3.connect(target/'demo.sqlite3')) as c:
            r=json.loads(c.execute('SELECT payload FROM records').fetchone()[0])
            self.assertTrue(Path(r['image_path']).is_file())
            self.assertTrue(Path(r['image_path']).is_relative_to(target))
            self.assertEqual(c.execute('SELECT count(*) FROM people').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM alerts').fetchone()[0],1)
        with self.assertRaises(ValueError):restore_backup(archive,target)
        broken=self.a.DATA/'bad.zip'
        with zipfile.ZipFile(io.BytesIO(response.content)) as z,zipfile.ZipFile(broken,'w') as out:
            for name in z.namelist():out.writestr(name,b'tampered' if name.endswith('.png') else z.read(name))
        with self.assertRaises(ValueError):restore_backup(broken,self.a.DATA/'bad-restore')
        self.assertFalse((self.a.DATA/'bad-restore').exists())

    def test_issuer_from_label_not_government_whitelist(self):
        def raw(texts):
            return {'rec_texts':texts,'rec_scores':[.99]*len(texts),'rec_polys':[[[0,i*40],[300,i*40],[300,i*40+20],[0,i*40+20]] for i in range(len(texts))]}
        self.assertEqual(extract(raw(['电工作业','签发机关：示例技能培训中心']))['fields']['issuer']['value'],'示例技能培训中心')
        self.assertEqual(extract(raw(['电工作业','签发机关','示例技能培训中心']))['fields']['issuer']['value'],'示例技能培训中心')
        self.assertEqual(extract(raw(['电工作业','签发机关','初领日期']))['fields']['issuer']['value'],'')


if __name__=='__main__':unittest.main()
