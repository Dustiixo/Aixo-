"""AIXO Collision Wall M0.1 -- dependency-free durable local reasoning-event engine.
No external IO, no authority over IXO/Thought Spine/VELA or other project stores.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from collections import Counter
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

MAX_TEXT = 12000
MAX_MARBLES = 10000
MAX_CHILDREN = 5
MAX_DEPTH = 4
MAX_JOB_ATTEMPTS = 3
MAX_PAIRS_PER_JOB = 12
LEASE_SECONDS = 30
GENESIS = '0' * 64
STOP = set('the a an and or this that with from about there here what where when who why how is are was were for into your you my its it to of on in at if as be by can have has do does did not but than then up down their our they those these i we he she them'.split())

def utc():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def uid():
    return uuid.uuid4().hex

def tokens(text):
    return set(w for w in re.findall(r'[\w]+', text.casefold()) if len(w) >= 3 and w not in STOP)

def overlap(a, b):
    x, y = tokens(a), tokens(b)
    if len(x & y) < 2 or not x or not y:
        return 0.0
    return round(len(x & y) / len(x | y), 5)

class WallError(Exception):
    pass

class Wall:
    def __init__(self, location):
        self.path = Path(location).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            # Existing stores must pass validation before any recovery write.
            result=self._verify_existing(self.path)
            if not result['ok']:
                raise WallError('Existing store failed integrity check: '+str(result['errors'])+'; preserve it and restore to a new workspace')
        else:
            self._setup()
        self.recover_expired()

    @contextmanager
    def connection(self, write=False):
        con = sqlite3.connect(str(self.path), timeout=8)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=8000')
        con.execute('PRAGMA synchronous=FULL')
        try:
            if write:
                con.execute('BEGIN IMMEDIATE')
            yield con
            if write:
                con.commit()
        except BaseException:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    def _setup(self):
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS marbles (
                  id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
                  kind TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL,
                  parent_id TEXT REFERENCES marbles(id), depth INTEGER NOT NULL,
                  body_hash TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_marbles_created ON marbles(created_at);
                CREATE INDEX IF NOT EXISTS idx_marbles_parent ON marbles(parent_id);
                CREATE TABLE IF NOT EXISTS edges (
                  id TEXT PRIMARY KEY, left_id TEXT NOT NULL REFERENCES marbles(id),
                  right_id TEXT NOT NULL REFERENCES marbles(id), relation TEXT NOT NULL,
                  created_at TEXT NOT NULL, UNIQUE(left_id,right_id,relation));
                CREATE TABLE IF NOT EXISTS candidates (
                  id TEXT PRIMARY KEY, a_id TEXT NOT NULL REFERENCES marbles(id),
                  b_id TEXT NOT NULL REFERENCES marbles(id), score REAL NOT NULL,
                  state TEXT NOT NULL DEFAULT 'suggested', created_at TEXT NOT NULL,
                  UNIQUE(a_id,b_id));
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, kind TEXT NOT NULL, marble_id TEXT NOT NULL REFERENCES marbles(id),
                  state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                  due_at REAL NOT NULL, lease_until REAL, error TEXT,
                  created_at TEXT NOT NULL, UNIQUE(kind,marble_id));
                CREATE INDEX IF NOT EXISTS idx_jobs_ready ON jobs(state,due_at);
                CREATE TABLE IF NOT EXISTS events (
                  seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                  action TEXT NOT NULL, subject TEXT NOT NULL, payload TEXT NOT NULL,
                  created_at TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS idempotency (
                  key TEXT PRIMARY KEY, op TEXT NOT NULL, request_hash TEXT NOT NULL,
                  result_id TEXT NOT NULL);
            ''')

    def _event(self, db, action, subject, payload):
        last = db.execute('SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        previous = last['event_hash'] if last else GENESIS
        event_id, when = uid(), utc()
        serialized = canonical(payload)
        data = canonical([previous, event_id, action, subject, serialized, when])
        h = digest(data)
        db.execute('INSERT INTO events(event_id,action,subject,payload,created_at,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?)',
                   (event_id,action,subject,serialized,when,previous,h))
        return event_id

    def _idempotency(self, db, key, op, data):
        if not key:
            return None
        row = db.execute('SELECT * FROM idempotency WHERE key=?',(key,)).fetchone()
        if row:
            if row['op'] != op or row['request_hash'] != digest(canonical(data)):
                raise WallError('Idempotency key reused for a different request')
            return row['result_id']
        return None

    def _save_key(self, db, key, op, data, result):
        if key:
            db.execute('INSERT INTO idempotency VALUES(?,?,?,?)',(key,op,digest(canonical(data)),result))

    def _get(self, db, mid):
        row = db.execute('SELECT * FROM marbles WHERE id=?',(mid,)).fetchone()
        if not row:
            raise WallError('Marble does not exist: '+mid)
        return row

    def _create(self, db, title, body, kind, source, parent=None, edge_relation=None):
        title, body, kind, source = [str(x).strip() for x in (title,body,kind,source)]
        if not title or len(title)>140 or not body or len(body)>MAX_TEXT:
            raise WallError('Title must be 1-140 characters; body 1-12000 characters')
        if not kind or len(kind)>45 or not source or len(source)>200:
            raise WallError('Invalid kind or source')
        if db.execute('SELECT COUNT(*) AS n FROM marbles').fetchone()['n'] >= MAX_MARBLES:
            raise WallError('Marble capacity reached; export/archive before adding more')
        depth = 0
        if parent:
            ancestor=self._get(db,parent)
            depth=ancestor['depth']+1
            if depth>MAX_DEPTH:
                raise WallError('Maximum branch depth reached')
            if db.execute('SELECT COUNT(*) AS n FROM marbles WHERE parent_id=?',(parent,)).fetchone()['n'] >= MAX_CHILDREN:
                raise WallError('Maximum direct children reached')
        mid=uid()
        now=utc()
        db.execute('INSERT INTO marbles VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (mid,title,body,kind,source,'candidate',parent,depth,digest(body),now))
        if parent and edge_relation:
            self._edge(db,parent,mid,edge_relation)
        db.execute('INSERT INTO jobs(id,kind,marble_id,state,attempts,due_at,lease_until,error,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                   (uid(),'scan',mid,'pending',0,0,None,None,now))
        self._event(db,'MARBLE_CREATED',mid,{'title':title,'body':body,'kind':kind,'source':source,'parent_id':parent,'depth':depth,'body_hash':digest(body)})
        return mid

    def add(self, title, body, kind='thought', source='user', key=None):
        data=[title,body,kind,source]
        with self.connection(True) as db:
            prior=self._idempotency(db,key,'add',data)
            if prior: return prior
            mid=self._create(db,title,body,kind,source)
            self._save_key(db,key,'add',data,mid)
            return mid

    def slice(self, mid, excerpt, title=None, key=None):
        with self.connection(True) as db:
            parent=self._get(db,mid)
            if not excerpt or excerpt not in parent['body']:
                raise WallError('A SLICE must be an exact excerpt of the original marble')
            title=title or parent['title']+' / slice'
            data=[mid,excerpt,title]
            prior=self._idempotency(db,key,'slice',data)
            if prior:return prior
            child=self._create(db,title,excerpt,'slice',parent['source'],mid,'SLICE')
            self._event(db,'SLICED',mid,{'child_id':child,'excerpt_hash':digest(excerpt)})
            self._save_key(db,key,'slice',data,child)
            return child

    def multiply(self, mid, branches, key=None):
        """Explicit user-authored child list; atomic all-or-none."""
        if not branches or len(branches)>MAX_CHILDREN:
            raise WallError('Supply 1 to 5 child branches')
        data=[mid,branches]
        with self.connection(True) as db:
            parent=self._get(db,mid)
            prior=self._idempotency(db,key,'multiply',data)
            if prior:return json.loads(prior)
            current=db.execute('SELECT COUNT(*) AS n FROM marbles WHERE parent_id=?',(mid,)).fetchone()['n']
            if current+len(branches)>MAX_CHILDREN:
                raise WallError('Total direct children would exceed the branch limit')
            created=[]
            for branch in branches:
                if not isinstance(branch,dict) or not branch.get('title') or not branch.get('body'):
                    raise WallError('Each branch needs title and body')
                created.append(self._create(db,branch['title'],branch['body'],'branch',parent['source'],mid,'MULTIPLY'))
            self._event(db,'MULTIPLIED',mid,{'children':created})
            self._save_key(db,key,'multiply',data,canonical(created))
            return created

    def mutate(self, mid, new_body, title=None, key=None):
        """Propose a traceable revision; original content stays unchanged."""
        with self.connection(True) as db:
            parent=self._get(db,mid)
            title=title or parent['title']+' / revision'
            data=[mid,new_body,title]
            prior=self._idempotency(db,key,'mutate',data)
            if prior:return prior
            if new_body.strip()==parent['body']:
                raise WallError('Revision must change the original content')
            child=self._create(db,title,new_body,'mutation',parent['source'],mid,'MUTATE')
            self._event(db,'MUTATION_PROPOSED',mid,{'child_id':child,'before_hash':parent['body_hash'],'after_hash':digest(new_body),'truth_verified':False})
            self._save_key(db,key,'mutate',data,child)
            return child

    def _edge(self, db, left, right, relation):
        if left==right:raise WallError('Self-edge is prohibited')
        self._get(db,left);self._get(db,right)
        if relation not in ('COLLIDE','RECONCILE','SLICE','MULTIPLY','MUTATE','SUPPORTS','CONTRADICTS'):
            raise WallError('Unsupported relationship')
        db.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?,?,?)',(uid(),left,right,relation,utc()))

    def connect(self, left, right, relation='COLLIDE'):
        with self.connection(True) as db:
            exists=db.execute('SELECT 1 FROM edges WHERE left_id=? AND right_id=? AND relation=?',(left,right,relation)).fetchone()
            if exists:return False
            self._edge(db,left,right,relation)
            self._event(db,'RELATION_RECORDED',left,{'target':right,'relation':relation,'verification':'unverified'})
            return True

    def review(self, mid, state, evidence):
        if state not in ('reviewed','rejected','candidate'):
            raise WallError('Unsupported review state')
        if not evidence or len(evidence.strip())<5 or len(evidence)>2000:
            raise WallError('Enter an evidence note of at least 5 characters')
        with self.connection(True) as db:
            self._get(db,mid)
            db.execute('UPDATE marbles SET status=? WHERE id=?',(state,mid))
            self._event(db,'HUMAN_REVIEW',mid,{'state':state,'evidence':evidence,'authority':'local_user','truth_independently_verified':False})

    def list_marbles(self, search='', limit=500):
        with self.connection() as db:
            if search:
                rows=db.execute('SELECT * FROM marbles WHERE title LIKE ? OR body LIKE ? ORDER BY created_at DESC,id DESC LIMIT ?',('%'+search+'%','%'+search+'%',limit)).fetchall()
            else:
                rows=db.execute('SELECT * FROM marbles ORDER BY created_at DESC,id DESC LIMIT ?',(limit,)).fetchall()
            return [dict(row) for row in rows]

    def get(self, mid):
        with self.connection() as db:return dict(self._get(db,mid))

    def stats(self):
        with self.connection() as db:
            r={}
            for table in ('marbles','edges','candidates','events'):
                r[table]=db.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n']
            r['jobs']={x['state']:x['n'] for x in db.execute('SELECT state,COUNT(*) n FROM jobs GROUP BY state')}
            return r

    def events(self, mid=None, limit=300):
        with self.connection() as db:
            if mid:
                rows=db.execute('SELECT * FROM events WHERE subject=? OR payload LIKE ? ORDER BY seq DESC LIMIT ?', (mid,'%'+mid+'%',limit))
            else:
                rows=db.execute('SELECT * FROM events ORDER BY seq DESC LIMIT ?', (limit,))
            return [dict(row) for row in rows]

    def candidates(self, limit=200):
        with self.connection() as db:
            rows=db.execute('''SELECT c.*,a.title a_title,b.title b_title FROM candidates c
                 JOIN marbles a ON a.id=c.a_id JOIN marbles b ON b.id=c.b_id
                 ORDER BY c.score DESC,c.created_at DESC LIMIT ?''',(limit,))
            return [dict(r) for r in rows]

    def jobs(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 500')]

    def recover_expired(self, force=False):
        with self.connection(True) as db:
            now=time.time()
            rows=db.execute("SELECT id,marble_id FROM jobs WHERE state='running' AND lease_until<=?",(now,)).fetchall()
            for row in rows:
                db.execute("UPDATE jobs SET state='pending',due_at=?,lease_until=NULL WHERE id=?",(now,row['id']))
                self._event(db,'JOB_RECLAIMED',row['marble_id'],{'job_id':row['id']})
            return len(rows)

    def process_one(self, simulate_failure=False):
        """Claim and process one due job with finite retries. Returns event status or None."""
        now=time.time()
        with self.connection(True) as db:
            job=db.execute("SELECT * FROM jobs WHERE state='pending' AND due_at<=? ORDER BY due_at,created_at,id LIMIT 1",(now,)).fetchone()
            if not job:return None
            db.execute("UPDATE jobs SET state='running',attempts=attempts+1,lease_until=? WHERE id=?",(now+LEASE_SECONDS,job['id']))
        try:
            if simulate_failure:raise RuntimeError('Simulated worker failure')
            with self.connection(True) as db:
                j=db.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone()
                if j['state']!='running':raise WallError('Job lease no longer owned')
                self._scan(db, j['marble_id'])
                db.execute("UPDATE jobs SET state='done',lease_until=NULL,error=NULL WHERE id=?",(job['id'],))
                self._event(db,'JOB_COMPLETED',job['marble_id'],{'job_id':job['id'],'attempts':j['attempts']})
                return 'done'
        except Exception as ex:
            with self.connection(True) as db:
                j=db.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone()
                if j['state']!='running':return 'lease_lost'
                dead=j['attempts']>=MAX_JOB_ATTEMPTS
                db.execute('UPDATE jobs SET state=?,due_at=?,lease_until=NULL,error=? WHERE id=?',
                           ('dead' if dead else 'pending',time.time()+min(2**j['attempts'],60),str(ex)[:500],job['id']))
                self._event(db,'JOB_DEAD' if dead else 'JOB_RETRY_SCHEDULED',job['marble_id'],{'job_id':job['id'],'attempts':j['attempts'],'error':str(ex)[:500]})
                return 'dead' if dead else 'retry'

    def _scan(self, db, mid):
        target=self._get(db,mid)
        others=db.execute('SELECT id,title,body FROM marbles WHERE id!=? ORDER BY created_at DESC LIMIT 2500',(mid,)).fetchall()
        matches=[]
        for other in others:
            score=overlap(target['title']+' '+target['body'],other['title']+' '+other['body'])
            if score>=0.15:
                matches.append((score,other['id']))
        if not matches:
            self._event(db,'PASS',mid,{'reason':'no_candidate_above_lexical_threshold','algorithm':'token_jaccard_v1'})
        for score,other_id in sorted(matches,key=lambda x:(-x[0],x[1]))[:MAX_PAIRS_PER_JOB]:
            a,b=sorted((mid,other_id))
            exists=db.execute('SELECT 1 FROM candidates WHERE a_id=? AND b_id=?',(a,b)).fetchone()
            if exists:continue
            cid=uid()
            db.execute('INSERT INTO candidates VALUES(?,?,?,?,?,?)',(cid,a,b,score,'suggested',utc()))
            self._event(db,'COLLISION_SUGGESTED',mid,{'candidate_id':cid,'other_id':other_id,'score':score,'algorithm':'token_jaccard_v1','verified':False})

    def process_ready(self, max_items=20):
        return [self.process_one() for _ in range(min(max_items,100)) if self._ready()]

    def _ready(self):
        with self.connection() as db:
            return bool(db.execute("SELECT 1 FROM jobs WHERE state='pending' AND due_at<=? LIMIT 1",(time.time(),)).fetchone())

    def decide_candidate(self,cid,accept,relation='COLLIDE'):
        with self.connection(True) as db:
            c=db.execute('SELECT * FROM candidates WHERE id=?',(cid,)).fetchone()
            if not c:raise WallError('Candidate does not exist')
            if c['state']!='suggested':return False
            if accept:self._edge(db,c['a_id'],c['b_id'],relation)
            db.execute('UPDATE candidates SET state=? WHERE id=?',('accepted' if accept else 'dismissed',cid))
            self._event(db,'COLLISION_DECIDED',c['a_id'],{'candidate_id':cid,'other_id':c['b_id'],'decision':'accepted' if accept else 'dismissed','relation':relation if accept else None,'truth_verified':False})
            return True

    def ancestry(self,mid):
        with self.connection() as db:
            self._get(db,mid)
            ancestors=[]
            seen=set()
            cur=mid
            while cur:
                if cur in seen:raise WallError('Cyclic parent pointers detected')
                seen.add(cur)
                row=self._get(db,cur)
                ancestors.append({'id':row['id'],'title':row['title'],'kind':row['kind'],'status':row['status']})
                cur=row['parent_id']
            return list(reversed(ancestors))

    def relationships(self,mid):
        with self.connection() as db:
            self._get(db,mid)
            query="""SELECT e.*,m.title AS other_title FROM edges e
                JOIN marbles m ON m.id=CASE WHEN e.left_id=? THEN e.right_id ELSE e.left_id END
                WHERE e.left_id=? OR e.right_id=? ORDER BY e.created_at,e.id"""
            return [dict(r) for r in db.execute(query,(mid,mid,mid))]

    def descendants(self,mid):
        with self.connection() as db:
            self._get(db,mid)
            rows=db.execute('''WITH RECURSIVE tree(id,title,parent_id,depth) AS (
                SELECT id,title,parent_id,0 FROM marbles WHERE id=?
                UNION ALL SELECT m.id,m.title,m.parent_id,t.depth+1 FROM marbles m JOIN tree t ON m.parent_id=t.id
                WHERE t.depth<?) SELECT * FROM tree ORDER BY depth,id''',(mid,MAX_DEPTH+1)).fetchall()
            return [dict(r) for r in rows]

    def replay_check(self):
        """Reconstruct graph/review state from the immutable event trail, then compare
        it against current materialized records. Queue scheduling is not replayed.
        """
        issues=[]
        reconstructed={}; links=set(); detected={}
        with self.connection() as db:
            for event in db.execute('SELECT action,subject,payload FROM events ORDER BY seq'):
                action=event['action']; subject=event['subject']
                try:payload=json.loads(event['payload'])
                except (ValueError,TypeError):
                    issues.append('Unreadable event payload for '+subject)
                    continue
                if action=='MARBLE_CREATED':
                    reconstructed[subject]={
                        'title':payload['title'],'body_hash':payload['body_hash'],
                        'kind':payload['kind'],'source':payload['source'],
                        'parent_id':payload['parent_id'],'depth':payload['depth'],'status':'candidate'}
                    if payload['parent_id']:
                        rel={'slice':'SLICE','branch':'MULTIPLY','mutation':'MUTATE'}.get(payload['kind'])
                        if rel:links.add((payload['parent_id'],subject,rel))
                elif action=='HUMAN_REVIEW':
                    if subject in reconstructed:reconstructed[subject]['status']=payload['state']
                    else:issues.append('Review without original '+subject)
                elif action=='RELATION_RECORDED':
                    links.add((subject,payload['target'],payload['relation']))
                elif action=='COLLISION_SUGGESTED':
                    detected[payload['candidate_id']]={'state':'suggested','pair':tuple(sorted((subject,payload['other_id'])))}
                elif action=='COLLISION_DECIDED':
                    c=detected.get(payload['candidate_id'])
                    if not c:issues.append('Decision without candidate '+payload['candidate_id'])
                    else:c['state']=payload['decision']
                    if payload['decision']=='accepted':links.add((subject,payload['other_id'],payload['relation']))
            existing={row['id']:dict(row) for row in db.execute('SELECT * FROM marbles')}
            if set(existing)!=set(reconstructed):
                issues.append('Event replay marble IDs differ from materialized state')
            for mid,fields in reconstructed.items():
                actual=existing.get(mid)
                if actual:
                    for k,v in fields.items():
                        if actual[k]!=v:issues.append('Event replay disagrees: '+mid+' / '+k)
            materialized={(row['left_id'],row['right_id'],row['relation']) for row in db.execute('SELECT * FROM edges')}
            if links!=materialized:issues.append('Event replay relationships differ from materialized edges')
            actual_candidates={row['id']:{'state':row['state'],'pair':(row['a_id'],row['b_id'])} for row in db.execute('SELECT * FROM candidates')}
            if detected!=actual_candidates:issues.append('Event replay collision candidates differ from materialized state')
        return issues

    def verify(self):
        errs=[]
        with self.connection() as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':errs.append('SQLite integrity_check failed')
            prev=GENESIS
            for row in db.execute('SELECT * FROM events ORDER BY seq'):
                expected=digest(canonical([prev,row['event_id'],row['action'],row['subject'],row['payload'],row['created_at']]))
                if row['previous_hash']!=prev or row['event_hash']!=expected:
                    errs.append('Event hash chain mismatch at seq '+str(row['seq']))
                prev=row['event_hash']
            for row in db.execute('SELECT * FROM marbles'):
                if digest(row['body'])!=row['body_hash']:errs.append('Content hash mismatch '+row['id'])
                if row['parent_id']:
                    parent=db.execute('SELECT depth FROM marbles WHERE id=?',(row['parent_id'],)).fetchone()
                    if not parent or row['depth']!=parent['depth']+1:errs.append('Depth invariant broken '+row['id'])
            for row in db.execute("SELECT * FROM edges WHERE relation IN ('SLICE','MULTIPLY','MUTATE')"):
                child=db.execute('SELECT parent_id FROM marbles WHERE id=?',(row['right_id'],)).fetchone()
                if not child or child['parent_id']!=row['left_id']:errs.append('Parent edge mismatch '+row['id'])
            for row in db.execute('SELECT parent_id,COUNT(*) n FROM marbles WHERE parent_id IS NOT NULL GROUP BY parent_id'):
                if row['n']>MAX_CHILDREN:errs.append('Branch quota exceeded '+row['parent_id'])
        errs.extend(self.replay_check())
        return {'ok':not errs,'errors':errs,'stats':self.stats(),'path':str(self.path)}

    def backup(self, folder=None):
        folder=Path(folder or self.path.parent/'backups').resolve();folder.mkdir(parents=True,exist_ok=True)
        target=folder/('AIXO_wall_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uid()[:6]+'.sqlite3')
        tmp=target.with_suffix('.partial')
        with self.connection() as src:
            dest=sqlite3.connect(str(tmp))
            try:src.backup(dest)
            finally:dest.close()
        try:
            check=Wall._verify_existing(tmp)
            if not check['ok']:raise WallError('Backup verification failed: '+str(check['errors']))
            os.replace(tmp,target)
        finally:
            if tmp.exists():tmp.unlink()
        return str(target)

    @staticmethod
    def _verify_existing(path):
        # On Windows, sqlite3.Connection.__exit__ commits but DOES NOT close.
        # A lingering handle blocks backup promotion and temp-directory cleanup.
        with closing(sqlite3.connect(str(path))) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':return {'ok':False,'errors':['SQLite integrity failed']}
        obj=object.__new__(Wall);obj.path=Path(path)
        try:return obj.verify()
        except Exception as e:return {'ok':False,'errors':[str(e)]}

    @classmethod
    def restore_new(cls,backup,target):
        backup=Path(backup).expanduser().resolve();target=Path(target).expanduser().resolve()
        if not backup.is_file():raise WallError('Backup not found')
        if target.exists():raise WallError('Restore target exists; choose an unused path')
        result=cls._verify_existing(backup)
        if not result['ok']:raise WallError('Backup failed integrity verification: '+str(result['errors']))
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=target.with_suffix('.restore-partial')
        if tmp.exists():raise WallError('A partial restoration exists; do not overwrite without inspection')
        # Explicit close is essential for Windows os.replace/unlink semantics.
        with closing(sqlite3.connect(str(backup))) as src:
            with closing(sqlite3.connect(str(tmp))) as dest:
                src.backup(dest)
        if not cls._verify_existing(tmp)['ok']:
            tmp.unlink(missing_ok=True)
            raise WallError('Copied restore verification failed')
        os.replace(tmp,target)
        return cls(target)

    def export_spine(self,target):
        result=self.verify()
        if not result['ok']:raise WallError('Integrity verification failed; export blocked')
        with self.connection() as db:
            export={'schema':'aixo.collision_wall.export.v1','owner':'AIXO Collision Wall (standalone)',
                 'thought_spine_state':'NOT_IMPORTED_REQUIRES_EXPLICIT_REVIEW',
                 'exported_at':utc(),'marbles':[dict(r) for r in db.execute('SELECT * FROM marbles ORDER BY created_at,id')],
                 'edges':[dict(r) for r in db.execute('SELECT * FROM edges ORDER BY created_at,id')],
                 'events':[dict(r) for r in db.execute('SELECT * FROM events ORDER BY seq')],
                 'candidates':[dict(r) for r in db.execute('SELECT * FROM candidates ORDER BY created_at,id')],
                 'verification':result}
        target=Path(target).expanduser().resolve()
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():raise WallError('Export already exists; choose a new file name')
        tmp=target.with_name(target.name+'.partial-'+uid()[:6])
        try:
            with tmp.open('x',encoding='utf-8') as f:
                json.dump(export,f,ensure_ascii=False,indent=2)
                f.flush();os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            tmp.unlink(missing_ok=True)
        return str(target)

    def demo(self):
        """Explicit opt-in demo, never populates a new DB silently."""
        ids=[]
        samples=[
            ('Concrete staircase estimate','Calculate concrete stairs six feet wide and eight steps with materials and delivery for a client estimate.','construction'),
            ('Bulk concrete delivery','Compare concrete volume and delivery for the staircase estimate; ready mix versus bagged material.','procurement'),
            ('Paving supplier comparison','Calculate patio paving stone price and delivery, checking exact slab specifications.','procurement'),
            ('AI cache safety','Cache computed quantities but recheck the supplier price and material specifications before quoting.','engineering'),
            ('Branch reliability','Use queue retries and idempotency when branching collision events so work cannot silently duplicate.','reliability'),
            ('Thought continuity','Preserve original thought history and collision event identities through export and reverse ancestry.','continuity'),
        ]
        for title,body,kind in samples:
            ids.append(self.add(title,body,kind,'explicit_demo'))
        self.process_ready(20)
        return ids


def default_path():
    base=os.environ.get('AIXO_WALL_HOME')
    if base:return str(Path(base)/'wall.sqlite3')
    local=os.environ.get('LOCALAPPDATA')
    root=Path(local) if local else Path.home()/'.local'/'share'
    return str(root/'OXsukra'/'AIXO_Collision_Wall_M0_1'/'wall.sqlite3')
