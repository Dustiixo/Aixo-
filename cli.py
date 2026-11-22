"""AIXO Collision Wall CLI -- useful for diagnostics and scriptable headless tests."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from wall import Wall, WallError, default_path

def main(argv=None):
    ap=argparse.ArgumentParser(description='AIXO Collision Wall local event engine')
    ap.add_argument('--db',default=default_path(),help='isolated SQLite file')
    p=ap.add_subparsers(dest='command',required=True)
    p.add_parser('demo');p.add_parser('list');p.add_parser('stats');p.add_parser('verify');p.add_parser('replay')
    p.add_parser('candidates');p.add_parser('jobs');p.add_parser('scan');p.add_parser('backup')
    p.add_parser('fault-once',help='simulate one worker error and persist retry')
    p.add_parser('recover',help='recover expired worker leases')
    add=p.add_parser('add');add.add_argument('title');add.add_argument('body');add.add_argument('--kind',default='thought');add.add_argument('--key')
    sl=p.add_parser('slice');sl.add_argument('id');sl.add_argument('excerpt');sl.add_argument('--title');sl.add_argument('--key')
    mul=p.add_parser('multiply');mul.add_argument('id');mul.add_argument('branches_json',help='JSON list of {title,body}');mul.add_argument('--key')
    mut=p.add_parser('mutate');mut.add_argument('id');mut.add_argument('new_body');mut.add_argument('--title');mut.add_argument('--key')
    trace=p.add_parser('trace');trace.add_argument('id')
    conn=p.add_parser('connect');conn.add_argument('left');conn.add_argument('right');conn.add_argument('--relation',default='COLLIDE')
    dec=p.add_parser('decide');dec.add_argument('candidate_id');dec.add_argument('decision',choices=['accept','dismiss'])
    review=p.add_parser('review');review.add_argument('id');review.add_argument('state',choices=['reviewed','rejected','candidate']);review.add_argument('evidence')
    export=p.add_parser('export');export.add_argument('path')
    restore=p.add_parser('restore-new');restore.add_argument('backup');restore.add_argument('new_path')
    opts=ap.parse_args(argv)
    try:
        if opts.command=='restore-new':
            w=Wall.restore_new(opts.backup,opts.new_path)
            result={'restored':str(w.path),'verify':w.verify()}
        else:
            w=Wall(opts.db)
            cmd=opts.command
            if cmd=='demo':result={'created_ids':w.demo()}
            elif cmd=='list':result=w.list_marbles()
            elif cmd=='stats':result=w.stats()
            elif cmd=='verify':result=w.verify()
            elif cmd=='replay':result={'ok':not w.replay_check(),'errors':w.replay_check()}
            elif cmd=='candidates':result=w.candidates()
            elif cmd=='jobs':result=w.jobs()
            elif cmd=='scan':result={'results':w.process_ready(100),'stats':w.stats()}
            elif cmd=='fault-once':result={'result':w.process_one(simulate_failure=True),'jobs':w.jobs()}
            elif cmd=='recover':result={'reclaimed':w.recover_expired()}
            elif cmd=='add':result={'id':w.add(opts.title,opts.body,opts.kind,key=opts.key)}
            elif cmd=='slice':result={'id':w.slice(opts.id,opts.excerpt,opts.title,key=opts.key)}
            elif cmd=='multiply':result={'ids':w.multiply(opts.id,json.loads(opts.branches_json),key=opts.key)}
            elif cmd=='mutate':result={'id':w.mutate(opts.id,opts.new_body,opts.title,key=opts.key)}
            elif cmd=='trace':result={'ancestors':w.ancestry(opts.id),'descendants':w.descendants(opts.id),'relationships':w.relationships(opts.id)}
            elif cmd=='connect':result={'created':w.connect(opts.left,opts.right,opts.relation)}
            elif cmd=='decide':result={'changed':w.decide_candidate(opts.candidate_id,opts.decision=='accept')}
            elif cmd=='review':w.review(opts.id,opts.state,opts.evidence);result={'ok':True}
            elif cmd=='backup':result={'backup':w.backup()}
            elif cmd=='export':result={'export':w.export_spine(opts.path)}
            else:raise WallError('Unsupported action')
        print(json.dumps(result,indent=2,ensure_ascii=False))
        if opts.command in ('verify','replay') and not result['ok']:return 2
        return 0
    except (WallError,ValueError,OSError,TypeError) as e:
        print('BLOCKED:',str(e),file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
