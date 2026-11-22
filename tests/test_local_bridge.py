import base64
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_bridge import LocalBridge, BridgeError, load_gremlin
from bridge_protocol import invoke
from wall import Wall, canonical,digest

class LocalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.dir=Path(self.tmp.name)
        self.bridge=LocalBridge(self.dir/'bridge.sqlite3',self.dir/'wall.sqlite3')
        self.file=self.dir/'GREMLIN export.json'
        self.export({'version':2,'entries':[{'id':'alpha','text':'Capture original thought with exact source context.',
                                             'notes':'A note that stays preserved','kind':'QUESTION','deleted':False}]})
    def tearDown(self):self.tmp.cleanup()
    def export(self,doc):self.file.write_text(json.dumps(doc,indent=2),encoding='utf8')
    def preview(self):return self.bridge.preview(self.file,'one-pc')
    def commit(self,allow=False,ids=None):return self.bridge.commit(self.file,'one-pc',self.preview()['export_sha256'],allow,ids)
    def test_preview_never_imports(self):
        self.assertEqual(self.preview()['entries'][0]['state'],'new')
        self.assertEqual(self.bridge.receipts(),[])
        self.assertEqual(self.bridge.wall.stats()['marbles'],0)
    def test_import_preserves_raw_and_round_trip(self):
        result=self.commit();self.assertEqual(result['outcomes'][0]['status'],'imported')
        receipt=self.bridge.receipts()[0]
        self.assertEqual(json.loads(receipt['original_json'])['notes'],'A note that stays preserved')
        self.assertTrue(self.bridge.verify()['ok'])
        again=LocalBridge(self.dir/'bridge.sqlite3',self.dir/'wall.sqlite3')
        self.assertEqual(again.receipts()[0]['marble_id'],receipt['marble_id'])
        self.assertEqual(again.wall.ancestry(receipt['marble_id'])[-1]['id'],receipt['marble_id'])
    def test_duplicate_not_duplicated(self):
        self.commit();a=self.bridge.wall.stats()['marbles']
        self.assertEqual(self.commit()['outcomes'][0]['status'],'duplicate')
        self.assertEqual(self.bridge.wall.stats()['marbles'],a)
    def test_revision_block_and_approved_branch(self):
        old=self.commit()['outcomes'][0]['marble_id']
        self.export({'version':2,'entries':[{'id':'alpha','text':'Corrected source thought with recorded new evidence.','notes':'new details','deleted':False}]})
        self.assertEqual(self.preview()['entries'][0]['state'],'revision_requires_approval')
        self.assertEqual(self.commit()['outcomes'][0]['status'],'revision_blocked')
        new=self.commit(True)['outcomes'][0]['marble_id']
        self.assertEqual(self.bridge.wall.get(new)['parent_id'],old)
        self.assertEqual(self.bridge.wall.get(old)['body'],'Capture original thought with exact source context.')
        self.assertTrue(self.bridge.verify()['ok'])
    def test_sha_bound_to_preview(self):
        sha=self.preview()['export_sha256'];self.file.write_text(self.file.read_text()+'\n',encoding='utf8')
        with self.assertRaisesRegex(BridgeError,'changed since preview'):
            self.bridge.commit(self.file,'one-pc',sha)
        self.assertEqual(self.bridge.receipts(),[])
    def test_invalid_format_and_duplicate_source_id(self):
        self.export({'version':3,'entries':[]})
        with self.assertRaises(BridgeError):self.preview()
        self.export({'version':2,'entries':[{'id':'x','text':'x'},{'id':'x','text':'y'}]})
        with self.assertRaises(BridgeError):self.preview()
    def test_overlarge_file_denied(self):
        self.file.write_bytes(b'x'*2_000_001)
        with self.assertRaises(BridgeError):self.preview()
    def test_no_deleted_or_empty_import(self):
        self.export({'version':1,'entries':[{'id':'one','text':'  ','deleted':False},
                                             {'id':'two','text':'ignored','deleted':True}]})
        self.assertTrue(self.commit()['all_committed']);self.assertEqual(self.bridge.wall.stats()['marbles'],0)
    def test_multi_selected_ids_and_missing(self):
        self.export({'version':2,'entries':[{'id':'a','text':'First thought.'},{'id':'b','text':'Second thought.'}]})
        self.assertEqual(len(self.commit(ids=['b'])['outcomes']),1)
        self.assertEqual(self.bridge.receipts()[0]['source_id'],'b')
        with self.assertRaises(BridgeError):self.commit(ids=['missing'])
    def test_prepared_recovery_without_duplicate(self):
        source=load_gremlin(self.file);e=source['entries'][0]
        row,_=self.bridge._prepare('one-pc',e,source['file_sha256'],False)
        from local_bridge import digest,canonical
        key='aixo.grem.v1.'+digest(canonical(['one-pc',e['id'],row['revision']]))
        mid=self.bridge.wall.add(e['text'][:115],e['text'],'capture','gremlin://one-pc/alpha',key=key)
        self.assertFalse(self.bridge.verify()['ok'])
        result=self.commit()
        self.assertEqual(result['outcomes'][0]['marble_id'],mid)
        self.assertEqual(self.bridge.wall.stats()['marbles'],1)
        self.assertTrue(self.bridge.verify()['ok'])
    def test_two_projects_isolated_by_namespace(self):
        self.bridge.commit(self.file,'one',self.bridge.preview(self.file,'one')['export_sha256'])
        self.bridge.commit(self.file,'two',self.bridge.preview(self.file,'two')['export_sha256'])
        self.assertEqual(self.bridge.wall.stats()['marbles'],2)
    def test_concurrent_idempotent_imports(self):
        sha=self.preview()['export_sha256']
        with ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(lambda _:self.bridge.commit(self.file,'one-pc',sha),range(5)))
        self.assertTrue(all(r['all_committed'] for r in results))
        self.assertEqual(self.bridge.wall.stats()['marbles'],1)
        self.assertTrue(self.bridge.verify()['ok'])
    def test_review_export_markdown_and_receipt(self):
        self.commit()
        r=self.bridge.export_review(self.dir,'one-pc')
        md=Path(r['markdown_path']).read_text('utf8')
        self.assertIn('A note that stays preserved',md)
        self.assertIn('not a Thought Spine backup',md)
        rec=json.loads(Path(r['receipt_path']).read_text('utf8'))
        self.assertTrue(rec['not_a_thought_spine_backup'])
        self.assertEqual(rec['records'][0]['source_entry_id'],'alpha')
    def test_export_blocked_if_pending(self):
        s=load_gremlin(self.file)
        self.bridge._prepare('one-pc',s['entries'][0],s['file_sha256'],False)
        with self.assertRaisesRegex(BridgeError,'Integrity/pending'):
            self.bridge.export_review(self.dir,'one-pc')
    def test_original_json_tamper_detected(self):
        self.commit()
        with closing(sqlite3.connect(self.bridge.path)) as c:
            c.execute("UPDATE imports SET original_json=?",('{"text":"tampered"}',)); c.commit()
        self.assertFalse(self.bridge.verify()['ok'])
    def test_wall_change_detected(self):
        self.commit()
        with closing(sqlite3.connect(self.bridge.wall.path)) as c:
            c.execute('UPDATE marbles SET body=?',('altered',)); c.commit()
        self.assertFalse(self.bridge.verify()['ok'])
    def test_backup_pair_restorable(self):
        self.commit();r=self.bridge.backup_pair(self.dir)
        saved=Path(r['directory']);self.assertTrue((saved/'bridge.sqlite3').exists())
        restored=LocalBridge(saved/'bridge.sqlite3',saved/'wall.sqlite3')
        self.assertTrue(restored.verify()['ok'])
    def test_protocol_whitelist_and_schema(self):
        with self.assertRaises(BridgeError):invoke({'schema':'bad','action':'verify','args':{}},self.bridge)
        with self.assertRaises(BridgeError):invoke({'schema':'aixo.local-bridge.request.v1','action':'delete','args':{}},self.bridge)
        self.assertEqual(invoke({'schema':'aixo.local-bridge.request.v1','action':'health','args':{}},self.bridge)['bridge_version'],'0.2.0')
    def test_protocol_subprocess_json(self):
        request={'schema':'aixo.local-bridge.request.v1','action':'preview','args':{'path':str(self.file),'namespace':'one-pc'}}
        env=os.environ.copy();env['AIXO_BRIDGE_HOME']=str(self.dir/'api');env['AIXO_WALL_HOME']=str(self.dir/'api_wall')
        p=subprocess.run([sys.executable,str(ROOT/'bridge_protocol.py')],input=base64.b64encode(json.dumps(request).encode())+b'\n',capture_output=True,env=env,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr.decode())
        self.assertEqual(json.loads(p.stdout)['data']['entries'][0]['state'],'new')
    def test_schema_upgrade_rejected(self):
        with closing(sqlite3.connect(self.bridge.path)) as c:
            c.execute('UPDATE bridge_meta SET value=?',('future-9',)); c.commit()
        with self.assertRaises(BridgeError):LocalBridge(self.bridge.path,self.bridge.wall.path)

if __name__=='__main__':unittest.main()
