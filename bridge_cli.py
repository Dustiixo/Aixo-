"""Headless operator CLI. Explicit preview and SHA-bound import, never autosync."""
import argparse,json,sys
from local_bridge import LocalBridge, BridgeError

def main(argv=None):
    p=argparse.ArgumentParser(description='AIXO Local Bridge M0.2 (offline)')
    p.add_argument('--registry');p.add_argument('--wall')
    subs=p.add_subparsers(dest='cmd',required=True)
    pv=subs.add_parser('preview');pv.add_argument('file');pv.add_argument('--namespace',default='gremlin-local')
    imp=subs.add_parser('import');imp.add_argument('file');imp.add_argument('--namespace',default='gremlin-local');imp.add_argument('--sha',required=True);imp.add_argument('--allow-revisions',action='store_true');imp.add_argument('--ids',nargs='*')
    subs.add_parser('verify');subs.add_parser('receipts');subs.add_parser('scan');subs.add_parser('health')
    exp=subs.add_parser('export');exp.add_argument('folder');exp.add_argument('--namespace',default='gremlin-local')
    bk=subs.add_parser('backup');bk.add_argument('folder')
    opts=p.parse_args(argv)
    try:
        b=LocalBridge(opts.registry,opts.wall)
        if opts.cmd=='preview':r=b.preview(opts.file,opts.namespace)
        elif opts.cmd=='import':r=b.commit(opts.file,opts.namespace,opts.sha,opts.allow_revisions,opts.ids)
        elif opts.cmd=='verify':r=b.verify()
        elif opts.cmd=='receipts':r=b.receipts()
        elif opts.cmd=='scan':r=b.wall.process_ready(30)
        elif opts.cmd=='health':r={'bridge':str(b.path),'wall':str(b.wall.path)}
        elif opts.cmd=='export':r=b.export_review(opts.folder,opts.namespace)
        elif opts.cmd=='backup':r=b.backup_pair(opts.folder)
        else:raise BridgeError('Invalid command')
        print(json.dumps(r,indent=2,ensure_ascii=False))
        if opts.cmd=='verify' and not r['ok']:return 2
        if opts.cmd=='import' and not r['all_committed']:return 2
        return 0
    except (BridgeError,OSError,ValueError) as ex:
        print('G0 BLOCKED:',str(ex),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
