"""AIXO RC1 Windows-safe JSON bridge. One isolated local request per process.
No network, subprocess, shell, project-wide access, or arbitrary Python invocation.
Only explicit whitelisted methods on the standalone Wall store.
"""
from __future__ import annotations
import base64
import json
import sys
from wall import Wall, WallError, default_path


def run(request):
    if not isinstance(request, dict) or set(request) - {'action', 'args'}:
        raise WallError('Invalid request fields')
    action = request.get('action')
    args = request.get('args', {})
    if not isinstance(args, dict):
        raise WallError('Arguments must be an object')
    if not isinstance(action, str):
        raise WallError('Action must be a string')
    if action == 'restore-new':
        if set(args) != {'backup', 'target'}:
            raise WallError('Restore needs backup and target')
        result = Wall.restore_new(args['backup'], args['target'])
        return {'path': str(result.path), 'verification': result.verify()}
    wall = Wall(default_path())
    actions = {
        'stats': (lambda: wall.stats(), set()),
        'verify': (lambda: wall.verify(), set()),
        'replay': (lambda: {'errors': wall.replay_check()}, set()),
        'list': (lambda: wall.list_marbles(limit=300), set()),
        'candidates': (lambda: wall.candidates(), set()),
        'events': (lambda: wall.events(limit=60), set()),
        'jobs': (lambda: wall.jobs(), set()),
        'demo': (lambda: {'created_ids': wall.demo()}, set()),
        'scan': (lambda: {'processed': wall.process_ready(30), 'stats': wall.stats()}, set()),
        'backup': (lambda: {'path': wall.backup()}, set()),
        'recover': (lambda: {'reclaimed': wall.recover_expired()}, set()),
        'get': (lambda: wall.get(args['id']), {'id'}),
        'trace': (lambda: {'ancestors': wall.ancestry(args['id']), 'descendants': wall.descendants(args['id']), 'relationships': wall.relationships(args['id'])}, {'id'}),
        'add': (lambda: {'id': wall.add(args['title'], args['body'], 'thought', 'user')}, {'title', 'body'}),
        'slice': (lambda: {'id': wall.slice(args['id'], args['excerpt'])}, {'id', 'excerpt'}),
        'mutate': (lambda: {'id': wall.mutate(args['id'], args['new_body'])}, {'id', 'new_body'}),
        'multiply': (lambda: {'ids': wall.multiply(args['id'], args['branches'])}, {'id', 'branches'}),
        'connect': (lambda: {'created': wall.connect(args['left'], args['right'], args['relation'])}, {'left', 'right', 'relation'}),
        'decide': (lambda: {'changed': wall.decide_candidate(args['id'], args['accept'])}, {'id', 'accept'}),
        'review': (lambda: (wall.review(args['id'], args['state'], args['evidence']), {'ok': True})[1], {'id', 'state', 'evidence'}),
        'export': (lambda: {'path': wall.export_spine(args['path'])}, {'path'}),
    }
    if action not in actions:
        raise WallError('Unknown or blocked action')
    operation, fields = actions[action]
    if set(args) != fields:
        raise WallError('Unexpected or missing action arguments')
    return operation()


def main():
    try:
        wire = sys.stdin.buffer.readline(2000000)
        if not wire or len(wire) >= 2000000:
            raise WallError('Request missing or too large')
        request = json.loads(base64.b64decode(wire.strip(), validate=True).decode('utf-8'))
        result = run(request)
        print(json.dumps({'ok': True, 'data': result}, ensure_ascii=True))
        return 0
    except (WallError, ValueError, OSError, KeyError, TypeError, UnicodeError) as err:
        print(json.dumps({'ok': False, 'error': str(err)}, ensure_ascii=True))
        return 2

if __name__ == '__main__':
    sys.exit(main())
