"""Fetch pinned public material referenced by the surviving benchmark artifacts."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'CodeWalk-source-recovery/0.2'})
    with urllib.request.urlopen(request,timeout=60) as response: return response.read()


def main():
    out=ROOT/'outputs/source-recovery/upstream'
    out.mkdir(parents=True,exist_ok=True)
    receipts=[]
    def store(repo,revision,relative):
        url=f'https://raw.githubusercontent.com/{repo}/{revision}/{relative}'
        content=fetch(url)
        path=out/repo.split('/')[-1]/relative
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        return {'repo':repo,'revision':revision,'path':relative,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
    manifest=json.loads((ROOT/'data/verus/manifest.json').read_text())
    pins=json.loads((ROOT/'codewalk/recovery/upstreams.json').read_text(encoding='utf-8'))
    wanted={p for task in manifest['tasks'] for p in task.get('source_programs',[])}
    for key in ('codecomplex','verus'):
        repo=pins[key]['repo'];commit=pins[key]['revision']
        tree=json.loads(fetch(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1'))['tree']
        if repo.endswith('CodeComplex'):
            selected=[r['path'] for r in tree if r['path'] in ('data/python_data.jsonl','data/README.md','README.md','LICENSE','LICENSE.md')]
        else:
            selected=[r['path'] for r in tree if r['type']=='blob' and
                      ('/verified/' in r['path'] and Path(r['path']).name in wanted or r['path']=='LICENSE')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(store,repo,commit,p) for p in selected]
            for future in concurrent.futures.as_completed(futures): receipts.append(future.result())
        print(json.dumps({'repo':repo,'revision':commit,'downloaded_files':len(selected)}),flush=True)
    (out/'receipts.json').write_text(json.dumps(receipts,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
