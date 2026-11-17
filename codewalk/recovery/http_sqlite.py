"""Read-only range-backed SQLite access for recovering selected FEMPD rows.

Never downloads or executes instructions from the database. Requires APSW and requests.
Range responses are validated, bounded and cached; the full multi-GB DB is not fetched.
"""
import hashlib
import json
from pathlib import Path
import re
import threading
import apsw
import requests


class RangeStore:
    def __init__(self,url,cache,block_size=65536):
        self.url=url;self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
        self.block_size=block_size;self.local=threading.local();self.lock=threading.Lock()
        self.bytes_fetched=0;self.size=None;self.etag=None
        self.block(0)

    def session(self):
        if not hasattr(self.local,'session'): self.local.session=requests.Session()
        return self.local.session

    def block(self,index):
        target=self.cache/f'{index:08d}.bin'
        if target.exists():
            meta=json.loads((self.cache/'metadata.json').read_text())
            if meta['url']!=self.url or meta['block_size']!=self.block_size:
                raise ValueError('Cache belongs to another source or block-size profile')
            self.size=meta['size'];self.etag=meta.get('etag')
            content=target.read_bytes()
            expected=min(self.block_size,self.size-index*self.block_size)
            if len(content)!=expected:raise ValueError('Truncated cached SQLite range')
            return content
        start=index*self.block_size
        end=start+self.block_size-1
        # A cache-key query parameter avoids CDN confusion between distinct byte ranges.
        url=self.url+('&' if '?' in self.url else '?')+f'cw_range={start}-{end}&cw_recovery_version=2'
        result=self.session().get(url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'},timeout=60,stream=True)
        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',result.headers.get('Content-Range',''))
        if result.status_code!=206 or not match or int(match[1])!=start:
            status=result.status_code;header=result.headers.get('Content-Range','')
            result.close();raise ValueError(f'Server did not honor bounded SQLite Range request: status={status}, range={header}, requested={start}-{end}')
        size=int(match[3]);expected=min(self.block_size,size-start)
        content=result.raw.read(expected+1,decode_content=True);result.close()
        if len(content)!=expected or int(match[2])!=start+expected-1:
            raise ValueError(f'Invalid SQLite range length: requested={start}-{end}, header={match[0]}, bytes={len(content)}, expected={expected}')
        etag=result.headers.get('ETag')
        if self.size is not None and self.size!=size or self.etag and etag and self.etag!=etag:
            raise ValueError('Remote SQLite artifact changed during recovery')
        self.size=size;self.etag=etag
        with self.lock:
            self.bytes_fetched+=len(content)
            temporary=target.with_suffix('.tmp')
            temporary.write_bytes(content);temporary.replace(target)
            meta=self.cache/'metadata.json'
            temporary=meta.with_suffix('.tmp')
            temporary.write_text(json.dumps({'url':self.url,'size':size,'etag':etag,'block_size':self.block_size}));temporary.replace(meta)
        return content

    def read(self,amount,offset):
        chunks=[]
        while amount and offset<self.size:
            index,position=divmod(offset,self.block_size)
            part=self.block(index)[position:position+amount]
            chunks.append(part);offset+=len(part);amount-=len(part)
        return b''.join(chunks)+b'\0'*amount


class RemoteFile:
    def __init__(self,store):self.store=store
    def xRead(self,amount,offset):return self.store.read(amount,offset)
    def xFileSize(self):return self.store.size
    def xClose(self):pass
    def xLock(self,level):pass
    def xUnlock(self,level):pass
    def xCheckReservedLock(self):return False
    def xFileControl(self,op,pointer):return False
    def xSectorSize(self):return 4096
    def xDeviceCharacteristics(self):return apsw.SQLITE_IOCAP_IMMUTABLE


class HTTPVFS(apsw.VFS):
    def __init__(self,name,store):
        self.store=store
        super().__init__(name,'')
    def xOpen(self,name,flags):return RemoteFile(self.store)


def connect(store,name='codewalk_http_sqlite'):
    vfs=HTTPVFS(name,store)
    db=apsw.Connection('file:remote?immutable=1',flags=apsw.SQLITE_OPEN_READONLY|apsw.SQLITE_OPEN_URI,vfs=name)
    return db,vfs
