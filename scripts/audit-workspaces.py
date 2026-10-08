"""Read-only repository/worktree inventory. Does not merge, remove, reset or fetch."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPOS = ['RTSAI-Mod', 'RTSAI-WebGame', 'OpenRA-AI', 'RTSAI-Web', 'RTSAI-Art', 'RTSAI-Film', 'OpenRA', 'OpenRA-RL']

def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    return result.stdout.strip() if result.returncode == 0 else None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    repos = []
    for name in REPOS:
        repo = ROOT/name
        worktrees = []
        for block in (git(repo, 'worktree', 'list', '--porcelain') or '').split('\n\n'):
            fields = dict(line.split(' ', 1) if ' ' in line else (line, True) for line in block.splitlines())
            if 'worktree' not in fields:
                continue
            location = Path(fields['worktree'])
            sha = fields.get('HEAD', '')
            unique = git(repo, 'rev-list', '--count', 'main..'+sha)
            status = git(location, 'status', '--porcelain=v1', '--untracked-files=all')
            worktrees.append({'path': str(location), 'head': sha, 'branch': fields.get('branch', 'detached'), 'commitsOutsideMain': int(unique or 0), 'changes': (status or '').splitlines(), 'readable': status is not None})
        branches = []
        for branch in (git(repo, 'for-each-ref', '--format=%(refname:short)', 'refs/heads') or '').splitlines():
            if branch.startswith('codex/consolidation-safety-'):
                continue
            count = int(git(repo, 'rev-list', '--count', 'main..'+branch) or 0)
            if count:
                branches.append({'name': branch, 'head': git(repo, 'rev-parse', branch), 'commitsOutsideMain': count, 'patchesOutsideMain': (git(repo, 'cherry', 'main', branch) or '').splitlines()})
        repos.append({'name': name, 'path': str(repo), 'main': git(repo, 'rev-parse', 'main'), 'currentBranch': git(repo, 'branch', '--show-current'), 'status': (git(repo, 'status', '--porcelain=v1') or '').splitlines(), 'remotes': (git(repo, 'remote', '-v') or '').splitlines(), 'worktrees': worktrees, 'unmergedBranches': branches})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'capturedAt': datetime.now(timezone.utc).isoformat(), 'scope': 'Local refs; remote state is not asserted by this inventory', 'repositories': repos}, indent=2)+'\n', encoding='utf-8')
    for repo in repos:
        print(repo['name'], repo['main'][:8], 'worktrees='+str(len(repo['worktrees'])), 'unmerged='+str(len(repo['unmergedBranches'])), 'changes='+str(len(repo['status'])))

if __name__ == '__main__':
    main()
