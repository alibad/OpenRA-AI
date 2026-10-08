"""Preserve the exact changed blobs of historical overlapping branches without activating old code."""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'resources/history/branch-variants-20261009.zip'
INDEX = OUT.with_suffix('.json')
BRANCHES = ['codex/air-warfare','codex/china-faction','codex/iran-faction-archive-20260812','codex/local-ai-installer','codex/mandab-campaign','codex/turkey-faction']

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def main():
    if OUT.exists():
        index = json.loads(INDEX.read_text(encoding='utf-8'))
        with zipfile.ZipFile(OUT) as archive:
            for branch in index['branches']:
                for file in branch['files']:
                    if 'member' in file:
                        assert hashlib.sha256(archive.read(file['member'])).hexdigest() == file['sha256']
        print('Verified existing branch archive:', sum(len(b['files']) for b in index['branches']), 'entries')
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    index = {'policy': 'Exact historical source variants; not runtime activation. Current canonical code remains authoritative. Git history and the safety bundles retain complete commits.', 'branches': []}
    seen = set()
    with zipfile.ZipFile(OUT, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for name in BRANCHES:
            head = git('rev-parse', name).decode().strip()
            base = git('merge-base', 'main', name).decode().strip()
            paths = git('diff', '--name-only', '-z', base, name).decode().split('\0')
            branch = {'name': name, 'head': head, 'base': base, 'files': []}
            for path in filter(None, paths):
                row = git('ls-tree', name, '--', path).decode().strip()
                if not row:
                    branch['files'].append({'path': path, 'change': 'historical deletion'})
                    continue
                descriptor = row.split('\t',1)[0].split()
                if descriptor[1] != 'blob':
                    branch['files'].append({'path': path, 'type': descriptor[1], 'gitObject': descriptor[2]})
                    continue
                data = git('cat-file', 'blob', descriptor[2])
                digest = hashlib.sha256(data).hexdigest()
                member = 'objects/'+digest
                if digest not in seen:
                    archive.writestr(member, data); seen.add(digest)
                branch['files'].append({'path': path, 'gitObject': descriptor[2], 'sha256': digest, 'bytes': len(data), 'member': member})
            index['branches'].append(branch)
    index['archiveSha256'] = hashlib.sha256(OUT.read_bytes()).hexdigest()
    INDEX.write_text(json.dumps(index, indent=2)+'\n', encoding='utf-8')
    print('Preserved', len(BRANCHES), 'branches,', sum(len(b['files']) for b in index['branches']), 'entries,', OUT.stat().st_size, 'bytes')

if __name__ == '__main__':
    main()
