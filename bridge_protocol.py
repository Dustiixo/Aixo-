"""Versioned JSON-line process protocol. One request per local process.
This does NOT open a listening TCP socket or execute arbitrary commands.
"""
from __future__ import annotations
import base64
import json
import sys
from local_bridge import LocalBridge, BridgeError
from wall import WallError

LIMIT=1_000_000

def invoke(request, service=None):
    if not isinstance(request, dict) or set(request)!={'schema','action','args'}:
        raise BridgeError('Expected only schema, action and args')
    if request['schema']!='aixo.local-bridge.request.v1':
        raise BridgeError('Unsupported protocol version')
    a=request['action'];kw=request['args']
    if not isinstance(kw,dict) or not isinstance(a,str):
        raise BridgeError('Invalid operation or arguments')
    operations={
      'health':set(), 'preview':{'path','namespace'},
      'import':{'path','namespace','expected_sha256','allow_revisions','selected_ids'},
      'receipts':{'namespace'},'verify':set(), 'scan':set(),
      'export':{'folder','namespace'},'backup':{'folder'},
      'trace':{'marble_id'}, 'get':{'marble_id'},
    }
    if a not in operations or set(kw)!=operations[a]:
        raise BridgeError('Blocked/unknown action or missing/unexpected arguments')
    if a=='import' and kw.get('approved') is not None:
        raise BridgeError('Unknown approval field')
    s=service or LocalBridge()
    if a=='health':return {'bridge_version':'0.2.0','schema':'aixo.local-bridge.request.v1',
                           'wall_path':str(s.wall.path),'registry_path':str(s.path),'no_network':True}
    if a=='preview':return s.preview(kw['path'],kw['namespace'])
    if a=='import':return s.commit(kw['path'],kw['namespace'],kw['expected_sha256'],
                                    kw['allow_revisions'],kw['selected_ids'])
    if a=='receipts':return {'items':s.receipts(kw['namespace'])}
    if a=='verify':return s.verify()
    if a=='scan':return {'job_outcomes':s.wall.process_ready(30),'wall_stats':s.wall.stats()}
    if a=='export':return s.export_review(kw['folder'],kw['namespace'])
    if a=='backup':return s.backup_pair(kw['folder'])
    if a=='trace':return {'ancestors':s.wall.ancestry(kw['marble_id']),
                          'descendants':s.wall.descendants(kw['marble_id']),
                          'relationships':s.wall.relationships(kw['marble_id'])}
    if a=='get':return s.wall.get(kw['marble_id'])
    raise BridgeError('Unknown action')

def main():
    try:
        raw=sys.stdin.buffer.readline(LIMIT+1)
        if not raw or len(raw)>LIMIT:
            raise BridgeError('Missing or oversized request')
        data=base64.b64decode(raw.strip(),validate=True)
        if len(data)>LIMIT:
            raise BridgeError('Decoded request too large')
        request=json.loads(data.decode('utf8'))
        answer=invoke(request)
        print(json.dumps({'ok':True,'schema':'aixo.local-bridge.response.v1','data':answer},ensure_ascii=True))
        return 0
    except (BridgeError,WallError,ValueError,TypeError,KeyError,OSError,UnicodeError) as ex:
        print(json.dumps({'ok':False,'schema':'aixo.local-bridge.response.v1','error':str(ex)},ensure_ascii=True))
        return 2
if __name__=='__main__':
    sys.exit(main())
