"""Recover actual source and EvoSuite blobs for surviving benchmark pair IDs."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from codewalk.recovery.http_sqlite import RangeStore,connect


def main():
    out=ROOT/'outputs/source-recovery/fempd';out.mkdir(parents=True,exist_ok=True)
    ids=set()
    for level in (1,2,3):
        for row in json.loads((ROOT/f'data/codeclone/data/level_{level}.json').read_text(encoding='utf-8')):
            ids.update(row['component_pairids'])
    pin=json.loads((ROOT/'codewalk/recovery/upstreams.json').read_text(encoding='utf-8'))['fempd']
    store=RangeStore(pin['url'],ROOT/'outputs/source-recovery/fempd-cache')
    if store.size!=pin['size_bytes'] or store.etag.strip('"')!=pin['etag']:
        raise ValueError('FEMPD size/ETag no longer matches the recovered source artifact')
    db,vfs=connect(store)
    verdicts=dict(db.execute('select pairid,consensus from verifiedpairs'))
    pairs={row[0]:row[1:] for row in db.execute('select id,leftMethodID,rightMethodID from pairs where id in ('+','.join('?' for _ in ids)+')',tuple(sorted(ids)))}
    db.close()
    def retrieve(pair_id):
        target=out/f'{pair_id}.json'
        if target.exists():return json.loads(target.read_text(encoding='utf-8'))
        for attempt in range(3):
            conn,v=connect(store,name=f'fempd-{pair_id}-{threading.get_ident()}')
            try:
                methods=[]
                for method_id in pairs[pair_id]:
                    row=list(conn.execute('select id,name,rtext,Target_ESTest,Target_ESTest_scaffolding,signature,compilable from methods where id=?',(method_id,)))[0]
                    keys=('id','name','source','evosuite','scaffolding','signature','compilable')
                    methods.append({k:value.decode('utf-8') if isinstance(value,bytes) else value for k,value in zip(keys,row)})
                result={'pair_id':pair_id,'upstream_consensus':verdicts.get(pair_id),'methods':methods,
                        'source':'FEMPD original SQLite, selected by published component_pairids'}
                target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
                return result
            except Exception:
                if attempt==2:raise
                time.sleep(attempt+1)
            finally:conn.close()
    errors=[];completed=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(retrieve,i):i for i in sorted(ids)}
        for future in concurrent.futures.as_completed(futures):
            try:future.result();completed+=1
            except Exception as exc:errors.append({'pair_id':futures[future],'error':str(exc)})
            if (completed+len(errors))%25==0:print(json.dumps({'recovered':completed,'errors':len(errors),'network_bytes':store.bytes_fetched}),flush=True)
    summary={'requested_pairs':len(ids),'recovered_pairs':completed,'errors':errors,'network_bytes_this_run':store.bytes_fetched,
             'remote_database_size':store.size,'etag':store.etag,
             'database_url':store.url,'method':'validated cached HTTP ranges; read-only SQLite primary-key queries'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
