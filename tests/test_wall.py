from contextlib import closing
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from wall import Wall, WallError, MAX_JOB_ATTEMPTS

class WallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'isolated.sqlite3'
        self.w=Wall(self.path)
    def tearDown(self):self.tmp.cleanup()

    def test_empty_db_integrity(self):
        self.assertTrue(self.w.verify()['ok'])
        self.assertEqual(self.w.stats()['events'],0)

    def test_add_restart_and_content_integrity(self):
        mid=self.w.add('Original idea','A thought with a source')
        self.assertEqual(Wall(self.path).get(mid)['body'],'A thought with a source')
        self.assertTrue(Wall(self.path).verify()['ok'])

    def test_create_rejects_invalid(self):
        for title,body in [('', 'foo'),('ok',''),('ok','x'*12001)]:
            with self.assertRaises(WallError):self.w.add(title,body)
        self.assertEqual(self.w.stats()['marbles'],0)

    def test_duplicate_idempotency(self):
        x=self.w.add('Name','Text','thought',key='unique-00001')
        y=self.w.add('Name','Text','thought',key='unique-00001')
        self.assertEqual(x,y)
        with self.assertRaises(WallError):self.w.add('Name','Different','thought',key='unique-00001')
        self.assertEqual(self.w.stats()['marbles'],1)

    def test_slice_exact_and_parent_chain(self):
        root=self.w.add('Parent','one two three four')
        with self.assertRaises(WallError):self.w.slice(root,'made up excerpt')
        child=self.w.slice(root,'two three')
        self.assertEqual(self.w.ancestry(child)[0]['id'],root)
        self.assertEqual(self.w.ancestry(child)[1]['id'],child)
        self.assertEqual(self.w.get(child)['body'],'two three')
        self.assertTrue(self.w.verify()['ok'])

    def test_multiply_all_or_nothing(self):
        root=self.w.add('Parent','The initial thought')
        with self.assertRaises(WallError):self.w.multiply(root,[{'title':'Valid','body':'Yep'},{'title':'Invalid','body':''}])
        self.assertEqual(self.w.stats()['marbles'],1)
        ids=self.w.multiply(root,[{'title':'Path A','body':'Explore possibility A'}, {'title':'Path B','body':'Explore possibility B'}],key='multiply1')
        self.assertEqual(len(ids),2)
        self.assertEqual(self.w.multiply(root,[{'title':'Path A','body':'Explore possibility A'}, {'title':'Path B','body':'Explore possibility B'}],key='multiply1'),ids)
        self.assertEqual(len(self.w.descendants(root)),3)
        self.assertTrue(self.w.verify()['ok'])

    def test_branch_limits_depth(self):
        p=self.w.add('Root','original premise')
        for i in range(4):p=self.w.multiply(p,[{'title':f'child{i}','body':'Meaningful branch'}])[0]
        with self.assertRaises(WallError):self.w.multiply(p,[{'title':'more','body':'cannot grow'}])

    def test_child_quota(self):
        p=self.w.add('Root','original premise')
        self.w.multiply(p,[{'title':f'{i}','body':'content'} for i in range(5)])
        with self.assertRaises(WallError):self.w.slice(p,'original')

    def test_collision_candidates_need_approval(self):
        a=self.w.add('Concrete staircase volume','Concrete staircase six feet wide calculate concrete material and volume')
        b=self.w.add('Concrete staircase supplier','Concrete staircase six feet wide calculate concrete price and delivery')
        self.w.process_ready()
        c=self.w.candidates()
        self.assertGreaterEqual(len(c),1)
        self.assertEqual(self.w.stats()['edges'],0)
        self.assertTrue(self.w.decide_candidate(c[0]['id'],True))
        self.assertFalse(self.w.decide_candidate(c[0]['id'],True))
        self.assertEqual(self.w.stats()['edges'],1)
        self.assertTrue(self.w.verify()['ok'])

    def test_candidate_dismissal(self):
        a=self.w.add('Music planning','compare musical pulse frequency and layers')
        b=self.w.add('Audio planning','compare musical pulse frequency and bass')
        self.w.process_ready()
        c=self.w.candidates()[0]
        self.w.decide_candidate(c['id'],False)
        self.assertEqual(self.w.stats()['edges'],0)

    def test_review_is_not_truth_claim(self):
        a=self.w.add('Claim','An unproven calculation')
        with self.assertRaises(WallError):self.w.review(a,'verified','some evidence')
        self.w.review(a,'reviewed','Manually looked at this')
        self.assertEqual(self.w.get(a)['status'],'reviewed')
        self.assertFalse(json.loads(self.w.events(a)[0]['payload'])['truth_independently_verified'])

    def test_event_hash_tamper_detected(self):
        a=self.w.add('Claim','This is an original fact')
        with closing(sqlite3.connect(self.path)) as db:
            with db:db.execute('UPDATE events SET payload=? WHERE seq=1',('tamper',))
        self.assertFalse(self.w.verify()['ok'])

    def test_content_tamper_detected(self):
        a=self.w.add('Claim','This is original text')
        with closing(sqlite3.connect(self.path)) as db:
            with db:db.execute('UPDATE marbles SET body=? WHERE id=?',('wrong',a))
        self.assertFalse(self.w.verify()['ok'])

    def test_retry_and_dead_letter_queue(self):
        self.w.add('Task','This will fail temporarily')
        for i in range(MAX_JOB_ATTEMPTS):
            with closing(sqlite3.connect(self.path)) as db:
                with db:db.execute("UPDATE jobs SET due_at=0 WHERE state='pending'")
            state=self.w.process_one(simulate_failure=True)
            self.assertEqual(state,'dead' if i==MAX_JOB_ATTEMPTS-1 else 'retry')
        self.assertEqual(self.w.jobs()[0]['state'],'dead')
        self.assertEqual(len([e for e in self.w.events() if e['action']=='JOB_DEAD']),1)
        self.assertTrue(self.w.verify()['ok'])

    def test_recover_expired_lease(self):
        self.w.add('Crash simulation','An intentionally abandoned running job')
        with closing(sqlite3.connect(self.path)) as db:
            with db:db.execute("UPDATE jobs SET state='running',lease_until=0")
        self.assertEqual(Wall(self.path).jobs()[0]['state'],'pending')
        self.assertGreater(len([e for e in self.w.events() if e['action']=='JOB_RECLAIMED']),0)

    def test_backup_restore_preserves_everything(self):
        a=self.w.add('Original','Original text content')
        b=self.w.slice(a,'text content')
        self.w.process_ready()
        backup=self.w.backup()
        target=Path(self.tmp.name)/'restored.sqlite3'
        restored=Wall.restore_new(backup,target)
        self.assertEqual(restored.get(b)['body'],'text content')
        self.assertEqual(restored.stats(),self.w.stats())
        self.assertTrue(restored.verify()['ok'])
        with self.assertRaises(WallError):Wall.restore_new(backup,target)

    def test_export_requires_integrity_and_explicit_review(self):
        a=self.w.add('Idea','Proof of concept')
        export=Path(self.tmp.name)/'review.json'
        self.w.export_spine(export)
        obj=json.loads(export.read_text())
        self.assertEqual(obj['thought_spine_state'],'NOT_IMPORTED_REQUIRES_EXPLICIT_REVIEW')
        self.assertEqual(obj['marbles'][0]['id'],a)
        with self.assertRaises(WallError):self.w.export_spine(export)

    def test_mutation_preserves_original(self):
        a=self.w.add('Original','Some original statement')
        b=self.w.mutate(a,'Some corrected statement',key='mutate-once')
        self.assertEqual(self.w.get(a)['body'],'Some original statement')
        self.assertEqual(self.w.get(b)['body'],'Some corrected statement')
        self.assertEqual(self.w.get(b)['parent_id'],a)
        self.assertEqual(self.w.mutate(a,'Some corrected statement',key='mutate-once'),b)
        self.assertTrue(self.w.verify()['ok'])

    def test_status_tamper_detected_by_event_replay(self):
        self.w.add('Original','Some original statement')
        with closing(sqlite3.connect(self.path)) as db:
            with db:db.execute("UPDATE marbles SET status='reviewed'")
        result=self.w.verify()
        self.assertFalse(result['ok'])
        self.assertTrue(any('Event replay disagrees' in x for x in result['errors']))

    def test_corrupt_store_blocks_open(self):
        self.w.add('Original','Some original statement')
        with closing(sqlite3.connect(self.path)) as db:
            with db:db.execute("UPDATE marbles SET body='tampered'")
        with self.assertRaises(WallError):Wall(self.path)

    def test_reconcile_preserves_parents(self):
        a=self.w.add('A','One independent origin')
        b=self.w.add('B','Another independent origin')
        self.assertTrue(self.w.connect(a,b,'RECONCILE'))
        self.assertFalse(self.w.connect(a,b,'RECONCILE'))
        self.assertIsNone(self.w.get(a)['parent_id'])
        self.assertIsNone(self.w.get(b)['parent_id'])

    def test_concurrent_create_preserves_hash_chain(self):
        results=[];errs=[]
        def make(i):
            try:results.append(self.w.add('T'+str(i),'A meaningful independent event '+str(i)))
            except Exception as e:errs.append(str(e))
        threads=[threading.Thread(target=make,args=(i,)) for i in range(12)]
        [t.start() for t in threads];[t.join() for t in threads]
        self.assertEqual(errs,[])
        self.assertEqual(len(set(results)),12)
        self.assertTrue(self.w.verify()['ok'])

    def test_demo_local_scoring(self):
        ids=self.w.demo()
        self.assertEqual(len(ids),6)
        self.assertEqual(self.w.stats()['jobs'].get('done'),6)
        self.assertTrue(self.w.verify()['ok'])

if __name__=='__main__':unittest.main()
