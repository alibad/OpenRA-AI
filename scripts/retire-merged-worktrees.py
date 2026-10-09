"""Retire merged checkouts only with a verified snapshot; remove Windows directory links without following them."""
import argparse,hashlib,json,os,subprocess,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BACKUP=Path(r'D:\rtsai-consolidation\cleanup-20261009')
KEEP={'RTSAI-Mod-wt-art-preview','RTSAI-Mod-wt-web-public','OpenRA-AI-wt-ra2-red-sea'}
HISTORICAL={'OpenRA-AI-wt-art-audit','OpenRA-AI-wt-harness','OpenRA-AI-wt-nl-orders','OpenRA-wt-art-audit','OpenRA-wt-art-audit-baseline','OpenRA-wt-upstream'}
def git(p,*args,check=True):
 r=subprocess.run(['git','-C',str(p),*args],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace')
 if check and r.returncode:raise RuntimeError(r.stderr.strip())
 return r.stdout.strip() if r.returncode==0 else None
def digest(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def regular_files(p):
 links=[]
 for base,dirs,names in os.walk(p,followlinks=False):
  for n in list(dirs):
   q=Path(base)/n
   if getattr(q.lstat(),'st_file_attributes',0)&0x400 or q.is_symlink():links.append(q);dirs.remove(n)
   elif n=='node_modules':dirs.remove(n)
  for n in names:
   q=Path(base)/n
   if q.is_symlink():links.append(q)
   else:yield q
 regular_files.links=links

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');a=parser.parse_args()
 inventory=json.loads((ROOT/'artifacts/consolidation-20261009/workspace-state-before-cleanup.json').read_text());records=json.loads((BACKUP/'index.json').read_text());by_path={r['path']:r for r in records}
 for repo in inventory['repositories']:
  primary=Path(repo['path']).resolve()
  for wt in repo['worktrees']:
   p=Path(wt['path'])
   if p==primary or p.name in KEEP or (p.name not in HISTORICAL and (wt['commitsOutsideMain'] or wt['changes'])):continue
   if p.parent.resolve()!=ROOT.resolve() or not p.name.startswith(primary.name+'-wt-'):raise RuntimeError('Unsafe checkout path')
   if not p.exists():continue
   print('Checking '+p.name,flush=True)
   if not a.execute:continue
   record=by_path.get(str(p));snapshot=BACKUP/(p.name+'.snapshot.json')
   if not record and snapshot.exists():record=json.loads(snapshot.read_text())
   archive=Path(record['archive']) if record else BACKUP/(p.name+'.zip')
   if archive.parent.resolve()!=BACKUP.resolve():raise RuntimeError('Unsafe archive path')
   with zipfile.ZipFile(archive)as z:
    if z.testzip():raise RuntimeError('Archive CRC failed')
    if record and digest(archive)!=record['sha256']:raise RuntimeError('Archive hash mismatch')
    files=list(regular_files(p));links=regular_files.links
    for q in files:
     rel=q.relative_to(p).as_posix()
     if rel not in z.namelist():raise RuntimeError('File absent from backup: '+str(q))
     info=z.getinfo(rel);crc=0;size=0
     with q.open('rb')as f:
      for b in iter(lambda:f.read(1048576),b''):crc=zlib.crc32(b,crc);size+=len(b)
     if info.file_size!=size or info.CRC!=(crc&0xffffffff):raise RuntimeError('File changed after backup: '+str(q))
    if not record:record={'path':str(p),'head':wt['head'],'archive':str(archive),'sha256':digest(archive),'files':len(z.infolist()),'bytes':sum(i.file_size for i in z.infolist()),'status':'archived'}
   if p.name not in HISTORICAL and git(primary,'rev-list','--count',record['head'],'--not','main')!='0':raise RuntimeError('Unique commits')
   if p.name in HISTORICAL:
    if record.get('disposition')!='historical source archive; unresolved resources are not runtime-integrated':raise RuntimeError('Historical snapshot disposition missing')
    archive_ref='refs/tags/workspace-archive-20261009-'+p.name
    previous=git(primary,'rev-parse','--verify',archive_ref,check=False)
    if previous and previous!=record['head']:raise RuntimeError('Archive ref conflict')
    git(primary,'update-ref',archive_ref,record['head']);record['historyRef']=archive_ref
   current_root=git(p,'rev-parse','--show-toplevel',check=False)
   if current_root and Path(current_root).resolve()==p.resolve():
    status=git(p,'status','--porcelain','--untracked-files=all',check=False)
    if p.name in HISTORICAL:
     if status.splitlines()!=record.get('sourceStatus',[]):raise RuntimeError('Historical source changed after snapshot')
    elif status:raise RuntimeError('Uncommitted source edits')
   elif record.get('status')!='kept' or 'failed to delete' not in record.get('reason',''):
    raise RuntimeError('Not a recognized partially retired checkout')
   # Preserve initialized nested engine repositories independently of worktree metadata.
   engine=p/'engine/openra'
   if engine.exists() and not (getattr(engine.lstat(),'st_file_attributes',0)&0x400):
    bundle=BACKUP/(p.name+'-engine.bundle')
    if git(engine,'rev-parse','--git-dir',check=False):
     if not bundle.exists():git(engine,'bundle','create',str(bundle),'--all')
     git(engine,'bundle','verify',str(bundle));record['engineBundle']={'path':str(bundle),'sha256':digest(bundle)}
   record['directoryLinks']=[{'path':str(q.relative_to(p)),'target':str(q.resolve())}for q in links];record['regenerableDependencies']='node_modules can be restored with npm ci using the archived lockfile'
   if str(p)not in by_path:records.append(record);by_path[str(p)]=record
   (BACKUP/'index.json').write_text(json.dumps(records,indent=2))
   # Native unlink of a directory reparse point removes its entry, never its target contents.
   for link in links:
    if link.parent==p.parent:raise RuntimeError('Unexpected root link')
    if getattr(link.lstat(),'st_file_attributes',0)&0x400:
     if getattr(link.lstat(),'st_file_attributes',0)&0x10:os.rmdir(link)
     else:link.unlink()
    elif link.is_symlink():link.unlink()
    else:raise RuntimeError('Directory link changed')
   git(primary,'worktree','remove','--force','--',str(p),check=False)
   if p.exists():
    # All reparse points have been removed; the exact resolved sibling target was checked above.
    ps=Path(__file__).with_name('remove-verified-remnant.ps1')
    subprocess.run(['pwsh','-NoProfile','-File',str(ps),'-Target',str(p),'-WorkspaceRoot',str(ROOT)],check=True)
    git(primary,'worktree','prune')
   record['status']='retired';record.pop('reason',None);(BACKUP/'index.json').write_text(json.dumps(records,indent=2))
   # Halt if another primary checkout was affected.
   for name in ['RTSAI-Mod','RTSAI-WebGame','OpenRA-AI','RTSAI-Web','RTSAI-Art','RTSAI-Film','OpenRA','OpenRA-RL']:
    if git(ROOT/name,'diff','--name-only','--diff-filter=D'):raise RuntimeError('Primary deletion detected')
   print('Retired '+p.name+' with '+str(len(links))+' links safely detached',flush=True)
 print('Verified retired snapshots: '+str(sum(r['status']=='retired'for r in records)),flush=True)
if __name__=='__main__':main()
