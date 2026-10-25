"""Publish only non-identifying check results using the user's GitHub credentials."""

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY = 'iAlexX-16/icpplus-monitor'
BASE_URL = 'https://icp.administracionelectronica.gob.es/icpplus/index.html'


def public_status(status):
    return {
        'last_run': status.get('last_run'),
        'profiles': {
            key: {
                'status': value['status'], 'last_check': value.get('last_check'), 'url': BASE_URL,
                **{field: value[field] for field in ('target_check_at', 'prepared_at', 'check_requested_at',
                   'availability_requested_at', 'dispatch_lateness_ms', 'error_kind', 'error_stage') if field in value},
            }
            for key, value in status.get('profiles', {}).items()
        },
    }


def github_token():
    if os.environ.get('GITHUB_TOKEN'):
        return os.environ['GITHUB_TOKEN']
    environment = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'}
    try:
        result = subprocess.run(
            ['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\nusername=iAlexX-16\n\n',
            capture_output=True, text=True, env=environment, timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ''
    credentials = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    return credentials.get('password', '')


def main():
    token = github_token()
    if not token:
        print('GitHub is not authenticated on this computer; status remains available locally.')
        return 2
    status = json.loads((Path(__file__).resolve().parent / 'data/status.json').read_text(encoding='utf-8'))
    content = base64.b64encode(json.dumps(public_status(status), ensure_ascii=False, indent=2).encode()).decode()
    url = f'https://api.github.com/repos/{REPOSITORY}/contents/data/status.json'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
               'User-Agent': 'icpplus-local-monitor', 'Content-Type': 'application/json'}
    try:
        for attempt in range(2):
            with urlopen(Request(url, headers=headers), timeout=25) as response:
                sha = json.load(response)['sha']
            payload = {'message': 'Update status from local monitor', 'sha': sha, 'content': content, 'branch': 'main'}
            try:
                with urlopen(Request(url, data=json.dumps(payload).encode(), headers=headers, method='PUT'), timeout=25):
                    pass
                print('Anonymous local check status published to GitHub.')
                return 0
            except HTTPError as error:
                if error.code == 409 and attempt == 0:
                    continue
                raise
    except HTTPError as error:
        print(f'GitHub status publication failed (HTTP {error.code}).')
    except (URLError, ValueError, KeyError):
        print('GitHub status publication failed; check authentication and connectivity.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
