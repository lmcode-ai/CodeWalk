"""AST-based FEMPD method normalization and conservative EvoSuite input extraction."""
import ast
import copy
import itertools
import json
import random
import re
import threading
from tree_sitter import Language,Parser
import tree_sitter_java
from ..composition.java_clone import java_type,literal

_LOCAL=threading.local()


def parser():
    if not hasattr(_LOCAL,'parser'):_LOCAL.parser=Parser(Language(tree_sitter_java.language()))
    return _LOCAL.parser


def walk(node):
    yield node
    for child in node.named_children:yield from walk(child)


def normalize(method):
    prefix='class Target {\n'
    data=(prefix+method['source']+'\n}').encode()
    tree=parser().parse(data)
    if tree.root_node.has_error:raise ValueError('Source Java parse failure')
    nodes=[n for n in walk(tree.root_node) if n.type=='method_declaration']
    candidates=[n for n in nodes if n.child_by_field_name('name').text.decode()==method['name']]
    if len(candidates)!=1:raise ValueError('Ambiguous method entry')
    fn=candidates[0]
    if fn.child_by_field_name('body') is None:raise ValueError('Missing method body')
    params=fn.child_by_field_name('parameters').named_children
    if any(p.type!='formal_parameter' for p in params):raise ValueError('Varargs/receiver parameters unsupported')
    types=[p.child_by_field_name('type').text.decode().replace(' ','')+('[]' if any(c.type=='dimensions' for c in p.named_children) else '') for p in params]
    names=[p.child_by_field_name('name').text.decode() for p in params]
    output=fn.child_by_field_name('type').text.decode().replace(' ','')
    for t in types+[output]:java_type(t)
    edits=[]
    modifiers=next((n for n in fn.named_children if n.type=='modifiers'),None)
    preserved=[]
    if modifiers:
        preserved=[x for x in modifiers.text.decode().split() if x in ('final','synchronized','strictfp')]
        edits.append((modifiers.start_byte,modifiers.end_byte,b''))
    edits.append((fn.start_byte,fn.start_byte,('public static '+' '.join(preserved)+' ').encode()))
    entry=fn.child_by_field_name('name');edits.append((entry.start_byte,entry.end_byte,b'run'))
    for n in walk(fn.child_by_field_name('body')):
        if n.type=='method_invocation' and n.child_by_field_name('name').text.decode()==method['name']:
            obj=n.child_by_field_name('object')
            if obj is None or obj.text in (b'this',b'Target'):
                name=n.child_by_field_name('name');edits.append((name.start_byte,name.end_byte,b'run'))
                if obj is not None:edits.append((obj.start_byte,obj.end_byte,b'Atom'))
    for start,end,value in sorted(edits,reverse=True):data=data[:start]+value+data[end:]
    # Strip only the known wrapper, preserving original method body tokens.
    member=data[len(prefix.encode()):-2].decode()
    return {'member':member,'input_types':types,'output_type':output,'parameter_names':names}


def test_inputs(source,types):
    tree=parser().parse(source.encode());cases=[]
    def evaluate(n,env):
        if n is None:raise ValueError('Missing expression')
        t=n.type;s=n.text.decode()
        if t in ('decimal_integer_literal','hex_integer_literal','octal_integer_literal','binary_integer_literal'):
            value=s.replace('_','').rstrip('Ll');return int(value,0) if value.lower().startswith(('0x','0b')) else int(value,8 if value.startswith('0') and len(value)>1 else 10)
        if t in ('decimal_floating_point_literal','hex_floating_point_literal'):
            value=s.replace('_','').rstrip('fFdD');return float.fromhex(value) if value.lower().startswith('0x') else float(value)
        if t in ('string_literal','character_literal'):return ast.literal_eval(s)
        if s in ('true','false'):return s=='true'
        if t=='null_literal':return None
        if t=='identifier':return env[s]
        if t=='parenthesized_expression':return evaluate(n.named_children[0],env)
        if t=='unary_expression':
            value=evaluate(n.named_children[-1],env);op=n.children[0].text.decode()
            return {'-':lambda:-value,'+':lambda:+value,'!':lambda:not value,'~':lambda:~value}[op]()
        if t=='cast_expression':
            value=evaluate(n.child_by_field_name('value'),env)
            typ=n.child_by_field_name('type').text.decode()
            if typ in ('byte','short','int','long','char'):
                bits={'byte':8,'short':16,'int':32,'long':64,'char':16}[typ]
                value=int(value)%(2**bits)
                if typ=='char':return chr(value)
                return value-2**bits if value>=2**(bits-1) else value
            return value
        if t=='array_initializer':return [evaluate(c,env) for c in n.named_children]
        if t=='array_creation_expression':
            initializer=next((c for c in n.named_children if c.type=='array_initializer'),None)
            if initializer:return evaluate(initializer,env)
            dimension=next(c for c in n.named_children if c.type=='dimensions_expr')
            count=evaluate(dimension.named_children[0],env)
            if not 0<=count<=256:raise ValueError('Array bound too large')
            typ=n.child_by_field_name('type').text.decode()
            return [False if typ=='boolean' else '\0' if typ=='char' else None if typ=='String' else 0]*count
        if t=='array_access':return evaluate(n.child_by_field_name('array'),env)[evaluate(n.child_by_field_name('index'),env)]
        if t=='field_access' and n.child_by_field_name('field').text==b'length':return len(evaluate(n.child_by_field_name('object'),env))
        if t=='method_invocation' and n.child_by_field_name('name').text in (b'__target__',b'run'):
            values=[evaluate(c,env) for c in n.child_by_field_name('arguments').named_children]
            if len(values)!=len(types):raise ValueError('Arity mismatch')
            for value,typ in zip(values,types):literal(value,typ)
            cases.append(copy.deepcopy(values));raise ValueError('Return value intentionally unknown')
        raise ValueError('Unsupported Java expression: '+t)
    def statements(node,env):
        if node.type=='local_variable_declaration':
            for dec in (c for c in node.named_children if c.type=='variable_declarator'):
                try:env[dec.child_by_field_name('name').text.decode()]=evaluate(dec.child_by_field_name('value'),env)
                except (ValueError,KeyError,StopIteration,TypeError,IndexError,OverflowError,SyntaxError):pass
            return
        if node.type=='assignment_expression':
            try:
                left=node.child_by_field_name('left');right=evaluate(node.child_by_field_name('right'),env)
                if left.type=='identifier':env[left.text.decode()]=right
                elif left.type=='array_access':evaluate(left.child_by_field_name('array'),env)[evaluate(left.child_by_field_name('index'),env)]=right
            except (ValueError,KeyError,TypeError,IndexError,OverflowError):pass
            return
        if node.type=='method_invocation':
            try:evaluate(node,env)
            except (ValueError,KeyError,StopIteration,TypeError,IndexError,OverflowError,SyntaxError):pass
            return
        for child in node.named_children:statements(child,env)
    for fn in (n for n in walk(tree.root_node) if n.type=='method_declaration' and n.child_by_field_name('name').text.startswith(b'test')):
        statements(fn.child_by_field_name('body'),{})
    return unique(cases)


def unique(cases):
    return list({json.dumps(v,sort_keys=True,ensure_ascii=True):v for v in cases}.values())


def generated_inputs(types,names,seed,count=64):
    rng=random.Random(seed)
    def values(typ):
        if typ.endswith('[]'):
            base=typ[:-2];small=values(base)
            return [[],[small[0]],[small[-1]],[small[0]]*4,small[:4],small[:8]]
        if typ=='String':return ['', 'a','abc','123','-1','a,b','a b','true','00','AAAA','é']
        if typ=='char':return ['\0','a','A','0',' ','\n',',','é']
        if typ=='boolean':return [False,True]
        return [-3,-1,0,1,2,3,4,7,8,16,31,127] if typ!='byte' else [-3,-1,0,1,2,3,4,7,16,127]
    pools=[values(t) for t in types];cases=[]
    for k in range(count):
        case=[copy.deepcopy(pool[k%len(pool)] if k<12 else rng.choice(pool)) for pool in pools]
        arrays=[v for t,v in zip(types,case) if t.endswith('[]') or t=='String']
        if arrays and k%2==0:
            length=len(arrays[0])
            for i,(typ,name) in enumerate(zip(types,names)):
                if typ in ('int','long','short','byte') and re.search('length|len|count|size',name,re.I):case[i]=length
                elif typ in ('int','long','short','byte') and re.search('offset|start|off|begin|index',name,re.I):case[i]=0
        cases.append(case)
    return unique(cases)
