"""Token-aware recovery for the surviving Verus corpus; conservative, not a Rust compiler."""
from dataclasses import dataclass
import re


@dataclass
class Token:
    value:str
    start:int
    end:int


def tokens(source):
    result=[];i=0
    while i<len(source):
        if source[i].isspace():i+=1;continue
        if source.startswith('//',i):
            end=source.find('\n',i);i=len(source) if end<0 else end;continue
        if source.startswith('/*',i):
            depth=1;i+=2
            while depth and i<len(source):
                if source.startswith('/*',i):depth+=1;i+=2
                elif source.startswith('*/',i):depth-=1;i+=2
                else:i+=1
            if depth:raise ValueError('Unclosed Rust comment')
            continue
        match=re.match(r'r(#+)?"',source[i:])
        if match:
            close='"'+(match[1] or '');end=source.find(close,i+len(match[0]))
            if end<0:raise ValueError('Unclosed raw string')
            result.append(Token(source[i:end+len(close)],i,end+len(close)));i=end+len(close);continue
        match=re.match(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])\'|[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[^\s]',source[i:])
        if not match:raise ValueError('Unsupported Rust token')
        value=match[0];result.append(Token(value,i,i+len(value)));i+=len(value)
    return result


def close_at(ts,index):
    pairs={'{':'}','(':')','[':']'};opening=ts[index].value;closing=pairs[opening];depth=1
    for j in range(index+1,len(ts)):
        if ts[j].value==opening:depth+=1
        elif ts[j].value==closing:
            depth-=1
            if not depth:return j
    raise ValueError('Unbalanced Rust delimiters')


def verus_body(source):
    ts=tokens(source)
    for i in range(len(ts)-2):
        if [t.value for t in ts[i:i+3]]==['verus','!','{']:
            end=close_at(ts,i+2);return source[ts[i+2].end:ts[end].start]
    raise ValueError('No Verus block')


def replace_names(source,mapping,logical=()):
    ts=tokens(source);edits=[]
    for i,t in enumerate(ts):
        if t.value in mapping:
            edits.append((t.start,t.end,mapping[t.value]))
            if t.value in logical and i+1<len(ts) and ts[i+1].value=='@':edits.append((ts[i+1].start,ts[i+1].end,''))
    for a,b,value in sorted(edits,reverse=True):source=source[:a]+value+source[b:]
    return source


def functions(body):
    ts=tokens(body);result={};depth=0;i=0
    while i<len(ts):
        t=ts[i]
        if depth==0 and t.value=='fn':
            name=ts[i+1].value;start=i+2
            if ts[start].value=='<':
                generic_depth=1;start+=1
                while generic_depth and start<len(ts):
                    if ts[start].value=='<':generic_depth+=1
                    elif ts[start].value=='>':generic_depth-=1
                    start+=1
            if ts[start].value!='(':raise ValueError('Unsupported recovered function signature')
            params_end=close_at(ts,start)
            j=params_end+1
            while j<len(ts):
                if ts[j].value=='{':
                    end=close_at(ts,j)
                    if end+1<len(ts) and ts[end+1].value in (',','&','|','='):
                        j=end+1;continue
                    break
                if ts[j].value in ('(', '['):j=close_at(ts,j)+1
                else:j+=1
            if j>=len(ts):raise ValueError('Function body unavailable')
            finish=close_at(ts,j)
            line=body.rfind('\n',0,t.start)+1
            result[name]={'name':name,'start':line,'fn_start':t.start,'body_start':ts[j].start,
                'end':ts[finish].end,'parameters':body[ts[start].end:ts[params_end].start],
                'header':body[t.start:ts[j].start],'body':body[ts[j].end:ts[finish].start],
                'prefix':body[line:t.start]}
            i=finish+1;continue
        if t.value=='{':depth+=1
        elif t.value=='}':depth-=1
        i+=1
    return result


def publicize(body):
    edits=[]
    for fn in functions(body).values():
        prefix=fn['prefix']
        if 'spec' in prefix:
            replacement='pub '+('closed' if 'closed' in prefix else 'open')+' spec '
        elif 'proof' in prefix:replacement='pub proof '
        else:replacement='pub '
        edits.append((fn['start'],fn['fn_start'],replacement))
    for a,b,v in sorted(edits,reverse=True):body=body[:a]+v+body[b:]
    return body


def executable_projection(body):
    ts=tokens(body);out=[];i=0
    while i<len(ts):
        value=ts[i].value
        if value=='proof' and i+1<len(ts) and ts[i+1].value=='{':i=close_at(ts,i+1)+1;continue
        if value in ('assert','assert_by','reveal','hide') and i+1<len(ts) and ts[i+1].value=='(':
            i=close_at(ts,i+1)+1
            if i<len(ts) and ts[i].value=='by':
                i+=1
                if ts[i].value=='{':i=close_at(ts,i)+1
            if i<len(ts) and ts[i].value==';':i+=1
            continue
        if value=='let' and i+1<len(ts) and ts[i+1].value in ('ghost','tracked'):
            while ts[i].value!=';':i+=1
            i+=1;continue
        if value in ('invariant','invariant_except_break','decreases'):
            i+=1
            while i<len(ts):
                if ts[i].value in ('(', '['):i=close_at(ts,i)+1;continue
                if ts[i].value=='{':
                    end=close_at(ts,i)
                    if end+1<len(ts) and ts[end+1].value==',':i=end+1;continue
                    break
                i+=1
            continue
        out.append(value);i+=1
    return out


def split_parameters(source):
    parts=[];depth=0;start=0
    for i,c in enumerate(source):
        if c in '<([':depth+=1
        if c in '>)]':depth-=1
        if c==',' and depth==0:parts.append(source[start:i]);start=i+1
    parts.append(source[start:])
    result=[]
    for part in parts:
        if not part.strip():continue
        name,typ=part.split(':',1);name=name.strip();typ=re.sub(r'\s+','',typ)
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name):raise ValueError('Unsupported parameter binding')
        result.append((name,typ))
    return result


def contract(fn):
    params=split_parameters(fn['parameters'])
    match=re.search(r'->\s*\(\s*([A-Za-z_]\w*)\s*:\s*([^)]*)\)',fn['header'])
    if not match:raise ValueError('Named scalar/vector return required')
    output=re.sub(r'\s+','',match[2])
    if output.startswith('&') or ',' in output:raise ValueError('Borrowed/tuple output unsupported in recovered chain')
    header=fn['header'][match.end():]
    ens=header.find('ensures')
    if ens<0:raise ValueError('Missing fixed driver contract')
    post=header[ens+len('ensures'):].strip().rstrip(',').strip()
    if not re.fullmatch(r'step1\s*\(.*\)',post,re.S):raise ValueError('Recovered L1 postcondition must be one step1 predicate')
    pre=header[:ens].strip()
    requires=pre[len('requires'):].strip().rstrip(',') if pre.startswith('requires') else ''
    return {'parameters':params,'output_type':output,'return_name':match[1],'ensures':post,'requires':requires}
