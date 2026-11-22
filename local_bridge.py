"""AIXO M0.2 local, explicit, one-process-per-request adapter.
Owns only bridge.sqlite3. GREMLIN exports are read-only, Thought Spine files are
new review artifacts, and the existing RC1 wall SQLite format is not migrated.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from wall import Wall, WallError, canonical, digest

SCHEMA = 'aixo.local-bridge.v0.2'
MAX_FILE = 2_000_000
MAX_ENTRIES = 250
MAX_COMMIT = 50
MAX_SOURCE_ID = 120
NS = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,49}$')

class BridgeError(WallError):
    pass

def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def bridge_default_path():
    base = os.environ.get('AIXO_BRIDGE_HOME')
    if base:
        return str(Path(base) / 'bridge.sqlite3')
    local = os.environ.get('LOCALAPPDATA')
    root = Path(local) if local else Path.home()/'.local'/'share'
    return str(root / 'OXsukra' / 'AIXO_Local_Bridge_M0_2' / 'bridge.sqlite3')

def bridge_wall_default_path():
    base = os.environ.get('AIXO_WALL_HOME') or os.environ.get('AIXO_BRIDGE_HOME')
    if base:
        return str(Path(base) / 'wall.sqlite3')
    local = os.environ.get('LOCALAPPDATA')
    root = Path(local) if local else Path.home()/'.local'/'share'
    return str(root / 'OXsukra' / 'AIXO_Local_Bridge_M0_2' / 'wall.sqlite3')

def bytes_sha(value):
    return hashlib.sha256(value).hexdigest()

def load_gremlin(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise BridgeError('Export missing or larger than 2 MB; no records imported')
    with path.open('rb') as f:
        payload = f.read(MAX_FILE + 1)
    if len(payload) > MAX_FILE:
        raise BridgeError('Export too large')
    try:
        document = json.loads(payload.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as ex:
        raise BridgeError('GREMLIN export is not valid UTF-8 JSON') from ex
    if not isinstance(document, dict) or type(document.get('version')) is not int or document.get('version') not in (1, 2):
        raise BridgeError('Expected GREMLIN version 1 or 2 export; do not guess formats')
    entries = document.get('entries')
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise BridgeError('GREMLIN entries must be an array of at most 250')
    seen = set()
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get('id'), str) or not (1 <= len(e['id']) <= MAX_SOURCE_ID):
            raise BridgeError('Entry id missing/invalid')
        if any(ord(ch)<32 for ch in e['id']):
            raise BridgeError('Entry ID contains control characters')
        if e['id'] in seen:
            raise BridgeError('Duplicate source entry id in export: ' + e['id'])
        seen.add(e['id'])
        if not isinstance(e.get('text'), str) or len(e['text']) > 12_000:
            raise BridgeError('Invalid text for entry ' + e['id'])
        if e.get('deleted', False) not in (True, False, None):
            raise BridgeError('Invalid deletion marker')
    return {'path': str(path), 'file_sha256': bytes_sha(payload), 'entries': entries, 'version': document['version']}

class LocalBridge:
    def __init__(self, registry=None, wall=None):
        self.path = Path(registry or bridge_default_path()).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.wall = Wall(wall or bridge_wall_default_path())
        if not self.path.exists():
            self._setup()
        self._check_schema()

    @contextmanager
    def conn(self, write=False):
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
        with self.conn() as c:
            c.execute('PRAGMA journal_mode=WAL')
        with self.conn(True) as c:
            c.executescript('''
              CREATE TABLE bridge_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE imports (
                id TEXT PRIMARY KEY, namespace TEXT NOT NULL, source_id TEXT NOT NULL,
                revision TEXT NOT NULL, export_hash TEXT NOT NULL,
                original_json TEXT NOT NULL, original_hash TEXT NOT NULL,
                marble_body TEXT NOT NULL, body_hash TEXT NOT NULL,
                previous_marble_id TEXT, state TEXT NOT NULL,
                marble_id TEXT, created_at TEXT NOT NULL, completed_at TEXT,
                UNIQUE(namespace,source_id,revision)
              );
              CREATE INDEX ix_imports_source ON imports(namespace,source_id,created_at);
              CREATE INDEX ix_imports_marble ON imports(marble_id);
            ''')
            c.execute('INSERT INTO bridge_meta VALUES(?,?)', ('schema',SCHEMA))

    def _check_schema(self):
        try:
            with self.conn() as c:
                if c.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise BridgeError('Bridge database SQLite integrity failed')
                r = c.execute('SELECT value FROM bridge_meta WHERE key=?',('schema',)).fetchone()
                if not r or r['value'] != SCHEMA:
                    raise BridgeError('Unsupported bridge database schema; preserve it and use a new location')
        except sqlite3.DatabaseError as ex:
            raise BridgeError('Bridge database invalid; preserve it: '+str(ex)) from ex

    @staticmethod
    def _namespace(ns):
        if not isinstance(ns, str) or not NS.fullmatch(ns):
            raise BridgeError('Namespace must be 1-50 characters, letters/numbers/._-')
        return ns

    @staticmethod
    def _revision(entry):
        return digest(canonical(entry))

    def preview(self, path, namespace):
        self._namespace(namespace)
        source = load_gremlin(path)
        rows = []
        with self.conn() as c:
            for e in source['entries']:
                rev = self._revision(e)
                old = c.execute('SELECT revision,state,marble_id FROM imports WHERE namespace=? AND source_id=? ORDER BY created_at DESC,id DESC',
                                (namespace,e['id'])).fetchall()
                existing = next((r for r in old if r['revision'] == rev),None)
                if e.get('deleted',False):
                    state='deleted_skip'
                elif not e['text'].strip():
                    state='empty_skip'
                elif existing:
                    state='already_imported' if existing['state']=='committed' else 'needs_recovery'
                elif old:
                    state='revision_requires_approval'
                else:
                    state='new'
                rows.append({'id': e['id'], 'text_preview': e['text'][:130], 'revision':rev,
                             'state':state,'previous_marble_id':old[0]['marble_id'] if old else None})
        return {'schema':'aixo.gremlin.preview.v1','namespace':namespace,'export_sha256':source['file_sha256'],
                'source_version':source['version'],'count':len(rows),'entries':rows,'writes':0}

    def _prepare(self, ns, entry, export_hash, allow_revisions):
        rev = self._revision(entry)
        with self.conn(True) as db:
            found=db.execute('SELECT * FROM imports WHERE namespace=? AND source_id=? AND revision=?',
                             (ns,entry['id'],rev)).fetchone()
            if found:
                return dict(found), False
            previous=db.execute('SELECT * FROM imports WHERE namespace=? AND source_id=? ORDER BY created_at DESC,id DESC LIMIT 1',
                                (ns,entry['id'])).fetchone()
            if previous and previous['state']!='committed':
                raise BridgeError('Previous revision is pending; resume it first')
            if previous and not allow_revisions:
                return None, False
            record={'id':uuid.uuid4().hex,'namespace':ns,'source_id':entry['id'],'revision':rev,
                    'export_hash':export_hash,'original_json':canonical(entry),'original_hash':digest(canonical(entry)),
                    'marble_body':entry['text'].strip(),'body_hash':digest(entry['text'].strip()),
                    'previous_marble_id':previous['marble_id'] if previous else None,
                    'state':'prepared','marble_id':None,'created_at':now(),'completed_at':None}
            db.execute('''INSERT INTO imports(id,namespace,source_id,revision,export_hash,original_json,original_hash,
                           marble_body,body_hash,previous_marble_id,state,marble_id,created_at,completed_at)
                           VALUES(:id,:namespace,:source_id,:revision,:export_hash,:original_json,:original_hash,
                           :marble_body,:body_hash,:previous_marble_id,:state,:marble_id,:created_at,:completed_at)''',record)
            return record, True

    def _fulfill(self, item):
        if item['state']=='committed':
            return item['marble_id'],False
        ns, eid, rev = item['namespace'],item['source_id'],item['revision']
        key = 'aixo.grem.v1.'+digest(canonical([ns,eid,rev]))
        if item['previous_marble_id']:
            mid = self.wall.mutate(item['previous_marble_id'],item['marble_body'],key=key)
        else:
            title = item['marble_body'].splitlines()[0][:115] or 'GREMLIN capture'
            mid = self.wall.add(title,item['marble_body'],'capture','gremlin://'+ns+'/'+eid,key=key)
        # A crash between the Wall write and the registry update is safe to retry
        # because the Wall uses the same stable, request-bound idempotency key.
        with self.conn(True) as db:
            found=db.execute('SELECT state,marble_id FROM imports WHERE id=?',(item['id'],)).fetchone()
            if not found:
                raise BridgeError('Prepared receipt disappeared; preserve stores for investigation')
            if found['marble_id'] not in (None,mid):
                raise BridgeError('Conflicting marble ID; blocked')
            db.execute('UPDATE imports SET state=?,marble_id=?,completed_at=? WHERE id=?',
                       ('committed',mid,now(),item['id']))
        return mid,True

    def commit(self, path, namespace, expected_sha256, allow_revisions=False, selected_ids=None):
        self._namespace(namespace)
        src=load_gremlin(path)
        if not isinstance(expected_sha256,str) or src['file_sha256']!=expected_sha256:
            raise BridgeError('Export changed since preview; re-preview before approving')
        if type(allow_revisions) is not bool:
            raise BridgeError('allow_revisions must be true/false')
        if selected_ids is not None:
            if not isinstance(selected_ids,list) or len(selected_ids)>MAX_COMMIT or any(not isinstance(x,str) for x in selected_ids):
                raise BridgeError('selected_ids must be a list of <= 50 source IDs')
            if len(selected_ids)!=len(set(selected_ids)):
                raise BridgeError('Duplicate selected IDs')
            all_ids={e['id'] for e in src['entries']}
            if any(x not in all_ids for x in selected_ids):
                raise BridgeError('Selection includes unknown source entry')
        chosen=[e for e in src['entries'] if selected_ids is None or e['id'] in selected_ids]
        if len(chosen)>MAX_COMMIT:
            raise BridgeError('At most 50 entries per approved import')
        outcomes=[]
        for e in chosen:
            if e.get('deleted',False) or not e['text'].strip():
                outcomes.append({'source_id':e['id'],'status':'skipped_deleted_or_empty'});continue
            item,fresh=self._prepare(namespace,e,src['file_sha256'],allow_revisions)
            if item is None:
                outcomes.append({'source_id':e['id'],'status':'revision_blocked'});continue
            try:
                mid,changed=self._fulfill(item)
                outcomes.append({'source_id':e['id'],'status':'imported' if changed else 'duplicate',
                                 'marble_id':mid,'revision':item['revision']})
            except Exception as ex:
                outcomes.append({'source_id':e['id'],'status':'prepared_needs_recovery','error':str(ex)[:220]})
                # Stop: next attempt must resume this first. Never skip a failed source update.
                break
        return {'schema':'aixo.gremlin.commit.v1','namespace':namespace,'export_sha256':src['file_sha256'],
                'outcomes':outcomes,'all_committed':not any(r['status']=='prepared_needs_recovery' for r in outcomes)}

    def receipts(self, namespace=None):
        if namespace is not None:self._namespace(namespace)
        with self.conn() as c:
            if namespace:
                rows=c.execute('SELECT * FROM imports WHERE namespace=? ORDER BY created_at,id',(namespace,)).fetchall()
            else:
                rows=c.execute('SELECT * FROM imports ORDER BY created_at,id').fetchall()
            return [dict(r) for r in rows]

    def verify(self):
        result=self.wall.verify()
        issues=list(result['errors'])
        try:
            self._check_schema()
            for item in self.receipts():
                if digest(item['original_json'])!=item['original_hash']:
                    issues.append('Original JSON changed: '+item['id']);continue
                try:
                    parsed=json.loads(item['original_json'])
                except ValueError:
                    issues.append('Unreadable original: '+item['id']);continue
                if self._revision(parsed)!=item['revision']:
                    issues.append('Source revision differs: '+item['id'])
                if digest(item['marble_body'])!=item['body_hash'] or parsed.get('text','').strip()!=item['marble_body']:
                    issues.append('Original text no longer matches: '+item['id'])
                if item['state']=='prepared':
                    issues.append('Unfinished prepared import (safe to retry): '+item['id'])
                elif item['state']=='committed':
                    try:
                        m=self.wall.get(item['marble_id'])
                        if m['body']!=item['marble_body'] or m['body_hash']!=item['body_hash']:
                            issues.append('Wall receipt mismatch: '+item['id'])
                        if item['previous_marble_id'] and m['parent_id']!=item['previous_marble_id']:
                            issues.append('Revision ancestry mismatch: '+item['id'])
                    except (WallError,TypeError):
                        issues.append('Missing Wall marble: '+item['id'])
                else:issues.append('Unknown receipt state: '+item['id'])
        except (BridgeError,sqlite3.DatabaseError) as ex:
            issues.append('Bridge schema/integrity: '+str(ex))
        return {'ok':not issues,'errors':issues,'imports':len(self.receipts()),'wall':result['stats']}

    def export_review(self, folder, namespace):
        self._namespace(namespace)
        check=self.verify()
        if not check['ok']:
            raise BridgeError('Integrity/pending import check failed; export blocked: '+str(check['errors'][:3]))
        records=[r for r in self.receipts(namespace) if r['state']=='committed']
        if not records:raise BridgeError('No committed imports for namespace')
        base=Path(folder).expanduser().resolve()
        if not base.is_dir():raise BridgeError('Select an existing export directory; no directories are created implicitly')
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        prefix='AIXO_Spine_Review_'+namespace+'_'+stamp+'_'+uuid.uuid4().hex[:6]
        md=base/(prefix+'.md'); js=base/(prefix+'.json')
        payload={'schema':'aixo.thought-spine.review.v1','owner':'AIXO Local Bridge',
                 'not_a_thought_spine_backup':True,'namespace':namespace,'exported_at':now(),
                 'records':[],'not_verified_facts':True}
        lines=['# AIXO Collision Wall — Thought Spine review',
               '','**Review-only source document.** Import this Markdown as a source using Thought Spine Capture.',
               'This is not a Thought Spine backup, live synchronization, a fact approval, or permission to execute.',
               '', 'Namespace: `'+namespace+'`','']
        for r in records:
            entry=json.loads(r['original_json']); m=self.wall.get(r['marble_id']); ancestry=self.wall.ancestry(r['marble_id'])
            rec={'source_app':'GREMLIN','source_entry_id':r['source_id'], 'original_entry':entry,
                 'original_entry_sha256':r['revision'],'source_export_sha256_at_import':r['export_hash'],
                 'marble_id':m['id'],'marble_body_sha256':m['body_hash'],
                 'ancestry':[x['id'] for x in ancestry], 'status':'unverified',
                 'related_events':[e['event_id'] for e in self.wall.events(m['id'],limit=150)]}
            payload['records'].append(rec)
            lines.extend(['## GREMLIN entry '+r['source_id'].replace('\n',' ').replace('\r',' '),
                          '', 'AIXO marble: `'+m['id']+'`',
                          'Revision SHA-256: `'+r['revision']+'`',
                          'Source export SHA-256: `'+r['export_hash']+'`',
                          'Ancestry (root → current): `'+ ' → '.join(rec['ancestry'])+'`',
                          'Status: unverified capture','', '### Original text','',
                          '```text',entry['text'].replace('```','` ` `'),'```','',
                          '### Original record JSON','',
                          '```json',json.dumps(entry,ensure_ascii=False,indent=2).replace('```','` ` `'),'```',''])
        data=("\n".join(lines)+"\n").encode('utf8')
        if len(data)>2_000_000:raise BridgeError('Review document exceeds 2 MB export cap')
        # Multi-file publication through a new directory, never partial published files.
        final=base/prefix
        stage=Path(str(final)+'.partial')
        stage.mkdir()
        try:
            draft=stage/'REVIEW.md';receipt=stage/'RECEIPT.json'
            with draft.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            payload['markdown_sha256']=bytes_sha(data)
            with receipt.open('x',encoding='utf-8') as f:
                json.dump(payload,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
            with (stage/'MANIFEST.json').open('x',encoding='utf-8') as f:
                json.dump({'schema':'aixo.review.bundle.v1',
                           'review_sha256':bytes_sha(draft.read_bytes()),
                           'receipt_sha256':bytes_sha(receipt.read_bytes())},f,indent=2)
                f.flush();os.fsync(f.fileno())
            os.replace(stage,final)
        except BaseException:
            import shutil
            shutil.rmtree(stage,ignore_errors=True)
            raise
        return {'directory':str(final),'markdown_path':str(final/'REVIEW.md'),
                'receipt_path':str(final/'RECEIPT.json'),'records':len(records),
                'markdown_sha256':bytes_sha(data),'review_only':True}

    def backup_pair(self, folder):
        check=self.verify()
        if not check['ok']:raise BridgeError('Cannot back up an inconsistent or pending state')
        folder=Path(folder).expanduser().resolve()
        if not folder.is_dir():raise BridgeError('Backup parent must already exist')
        final=folder/('AIXO_Bridge_Backup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:6])
        staging=Path(str(final)+'.partial')
        staging.mkdir()
        try:
            for src,target in ((self.path,staging/'bridge.sqlite3'),(self.wall.path,staging/'wall.sqlite3')):
                with closing(sqlite3.connect(str(src))) as con:
                    with closing(sqlite3.connect(str(target))) as dest:
                        con.backup(dest)
            snapshot=LocalBridge(staging/'bridge.sqlite3',staging/'wall.sqlite3')
            v=snapshot.verify()
            if not v['ok']:raise BridgeError('Copied backup cross-store verification failed: '+str(v['errors']))
            manifest={'schema':'aixo.backup_pair.v1','warning':'two independent SQLite stores, not atomic cross-database snapshot',
                      'wall_sha256':bytes_sha((staging/'wall.sqlite3').read_bytes()),
                      'bridge_sha256':bytes_sha((staging/'bridge.sqlite3').read_bytes()),'as_of':now()}
            (staging/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
            os.replace(staging,final)
            return {'directory':str(final),'verification':v,'manifest':manifest}
        except BaseException:
            import shutil
            shutil.rmtree(staging,ignore_errors=True)
            raise
