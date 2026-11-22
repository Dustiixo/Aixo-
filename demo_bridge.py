"""Isolated end-to-end demonstration. Does NOT touch the live RC1 or bridge stores."""
from __future__ import annotations
import json, tempfile,sys
from pathlib import Path
from local_bridge import LocalBridge

def run():
    root=Path(tempfile.mkdtemp(prefix='AIXO_M02_SAFE_DEMO_')).resolve()
    source=root/'SYNTHETIC_GREMLIN_export.json'
    example={'version':2,'createdAt':'2026-10-26T00:00:00Z','entries':[
      {'id':'synthetic-one','kind':'QUESTION','lane':'KNOWLEDGE','stage':'EXPLORE',
       'text':'Calculate concrete stairs and compare material costs with supplier delivery.',
       'notes':'Synthetic demonstration. Not a real customer quote.', 'createdAt':'2026-10-26T00:00:00Z','deleted':False},
      {'id':'synthetic-two','kind':'IDEA','lane':'KNOWLEDGE','stage':'EXPLORE',
       'text':'Research concrete delivery and supplier materials for a staircase estimate.',
       'notes':'Second synthetic thought; similar lexical subjects produce a suggested collision.',
       'createdAt':'2026-10-26T00:01:00Z','deleted':False}
    ]}
    source.write_text(json.dumps(example,indent=2),encoding='utf8')
    original_bytes=source.read_bytes()
    service=LocalBridge(root/'bridge.sqlite3',root/'wall.sqlite3')
    preview=service.preview(source,'demo-local')
    assert [r['state'] for r in preview['entries']]==['new','new']
    commit=service.commit(source,'demo-local',preview['export_sha256'])
    assert commit['all_committed'] and len(commit['outcomes'])==2
    assert all(r['status']=='imported' for r in commit['outcomes'])
    jobs=service.wall.process_ready(20)
    duplicate=service.commit(source,'demo-local',preview['export_sha256'])
    assert all(r['status']=='duplicate' for r in duplicate['outcomes'])
    mid=commit['outcomes'][0]['marble_id']
    ancestry=service.wall.ancestry(mid)
    audit=service.verify();assert audit['ok'],audit
    review=service.export_review(root,'demo-local')
    backup=service.backup_pair(root)
    # Fresh process simulation: new database connections, same stored results
    reopened=LocalBridge(root/'bridge.sqlite3',root/'wall.sqlite3')
    assert reopened.verify()['ok']
    assert len(reopened.receipts())==2
    assert len(ancestry)==1
    assert source.read_bytes()==original_bytes
    assert Path(review['markdown_path']).is_file()
    assert Path(backup['directory']).is_dir()
    report={'result':'PASS_ISOLATED','stores':'SYNTHETIC_ONLY', 'results_directory':str(root),
            'original_source_unchanged':True,'imports':2,'duplicate_imports_blocked':2,
            'collision_candidates':len(service.wall.candidates()),'jobs':jobs,
            'review_markdown':review['markdown_path'], 'review_receipt':review['receipt_path'],
            'backup_directory':backup['directory'],'reopen_verified':True,
            'warning':'Does not prove host acceptance of GREMLIN Android or Thought Spine live import'}
    (root/'DEMO_RECEIPT.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
    return 0
if __name__=='__main__':
    try:sys.exit(run())
    except Exception as ex:
        print('G0 DEMO FAILED:',str(ex),file=sys.stderr)
        sys.exit(2)
