"""Subprocess and file-handle regression tests (the RC0 Windows failures)."""
import base64
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from wall import Wall

ROOT=Path(__file__).resolve().parents[1]

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.env=os.environ.copy()
        self.env['AIXO_WALL_HOME']=str(self.home)
        self.env.pop('PYTHONHOME',None)
        self.env.pop('PYTHONPATH',None)

    def invoke(self,action,args=None):
        wire=base64.b64encode(json.dumps({'action':action,'args':args or {}}).encode('utf-8'))+b'\n'
        run=subprocess.run([sys.executable,str(ROOT/'bridge.py')],input=wire,
                           env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        try:
            payload=json.loads(run.stdout.decode('utf-8'))
        except Exception as exc:
            self.fail(f'bridge emitted invalid JSON: {run.stdout!r} {run.stderr!r}: {exc}')
        return run.returncode,payload

    def test_bridge_full_lifecycle_and_process_reopen(self):
        code,result=self.invoke('add',{'title':'Original','body':'Source and multiple related thoughts'})
        self.assertEqual(code,0,result)
        original=result['data']['id']
        code,slice_result=self.invoke('slice',{'id':original,'excerpt':'multiple related thoughts'})
        self.assertEqual(code,0,slice_result)
        child=slice_result['data']['id']
        code,result=self.invoke('scan')
        self.assertEqual(code,0,result)
        code,result=self.invoke('trace',{'id':child})
        self.assertEqual(code,0,result)
        self.assertEqual(result['data']['ancestors'][0]['id'],original)
        code,result=self.invoke('verify')
        self.assertTrue(result['data']['ok'],result)
        code,result=self.invoke('backup')
        self.assertEqual(code,0,result)
        backup=result['data']['path']
        target=str(self.home/'restored.sqlite3')
        code,result=self.invoke('restore-new',{'backup':backup,'target':target})
        self.assertEqual(code,0,result)
        self.assertTrue(Path(target).exists())
        code,result=self.invoke('export',{'path':str(self.home/'spine.json')})
        self.assertEqual(code,0,result)
        self.assertEqual(json.loads((self.home/'spine.json').read_text())['thought_spine_state'],
                         'NOT_IMPORTED_REQUIRES_EXPLICIT_REVIEW')
        self.assertEqual(self.invoke('verify')[1]['data']['stats']['marbles'],2)

    def test_bridge_unknown_action_rejected(self):
        code,result=self.invoke('exec',{'command':'calc.exe'})
        self.assertEqual(code,2)
        self.assertFalse(result['ok'])

    def test_bridge_bad_args_rejected(self):
        code,result=self.invoke('add',{'title':'A','body':'B','unexpected':'unsafe'})
        self.assertEqual(code,2)
        self.assertFalse(result['ok'])

    def test_bridge_unicode_multiline(self):
        body='Music × code\nLine 2: 文字'
        code,result=self.invoke('add',{'title':'Thought with Unicode','body':body})
        self.assertEqual(code,0,result)
        code,result=self.invoke('get',{'id':result['data']['id']})
        self.assertEqual(result['data']['body'],body)

    def test_verify_and_backup_close_sqlite_handles(self):
        db_path=self.home/'isolated.sqlite3'
        w=Wall(db_path)
        w.add('test','windows file handle release')
        self.assertTrue(w.verify()['ok'])
        saved=Path(w.backup())
        self.assertTrue(saved.exists())
        renamed=saved.with_name('renamed.sqlite3')
        saved.replace(renamed)  # fails under Windows if backup file handle leaks
        renamed.replace(saved)
        mirror=db_path.with_name('relocated.sqlite3')
        db_path.replace(mirror)  # fails on Windows if verifier left a handle open
        mirror.replace(db_path)
        restored=Wall.restore_new(saved,self.home/'fresh.sqlite3')
        self.assertTrue(restored.verify()['ok'])
        fresh=self.home/'fresh.sqlite3'
        fresh.replace(self.home/'fresh2.sqlite3')
        (self.home/'fresh2.sqlite3').replace(fresh)

if __name__ == '__main__':unittest.main()
