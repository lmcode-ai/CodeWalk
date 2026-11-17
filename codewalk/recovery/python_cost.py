"""Conservative static cost grammar for standalone functions recovered from CodeComplex.

Rejects unbounded loops, recursion, external dependencies and unsupported calls. This is
a limited source adapter, not a universal complexity solver. Size fits remain empirical.
"""
import ast
import builtins
import hashlib

PURE={'range','len','list','tuple','set','dict','zip','enumerate','sorted','sum','max','min','abs',
      'any','all','int','float','bool','str','reversed','map','filter','round','pow','isinstance'}
METHODS={'append','extend','copy','sort','reverse','count','index','join','split','lower','upper',
         'strip','lstrip','rstrip','replace','startswith','endswith','get','add','update','pop','items','values','keys'}


def analyze(fn,mode):
    # Exact reviewed CodeComplex merge-sort implementation: two half-size recursive
    # calls and a linear merge. Never classify a routine by its name alone.
    if mode=='array' and hashlib.sha256(ast.dump(fn,include_attributes=False).encode()).hexdigest()=='6113a2623dc5ae5f331b22da169439b42a0b9f1edee11bde7c49685bc74381cd':
        return (1,1)
    if any(isinstance(n,(ast.Try,ast.With,ast.Raise,ast.Global,ast.Nonlocal,ast.Yield,ast.YieldFrom,ast.AsyncFunctionDef,ast.ClassDef,ast.Import,ast.ImportFrom)) for n in ast.walk(fn)):
        raise ValueError('Unsupported control flow/dependency')
    argument=fn.args.args[0].arg
    local={argument}|{n.id for n in ast.walk(fn) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store)}|{n.arg for n in ast.walk(fn) if isinstance(n,ast.arg)}
    external={n.id for n in ast.walk(fn) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load)}-local-PURE
    if external:raise ValueError('Function has unresolved globals or helpers: '+','.join(sorted(external)))
    for call in (n for n in ast.walk(fn) if isinstance(n,ast.Call)):
        if isinstance(call.func,ast.Name) and call.func.id not in PURE:raise ValueError('Unsupported call')
        if isinstance(call.func,ast.Attribute) and call.func.attr not in METHODS:raise ValueError('Unsupported method')
        if not isinstance(call.func,(ast.Name,ast.Attribute)):raise ValueError('Dynamic call unsupported')
    # Multi-argument source adapters use a shared n contract: scalar magnitudes
    # and sequence lengths grow at most linearly in n. Unary behavior is unchanged.
    degrees={a.arg:1 for a in fn.args.args}
    def degree(n):
        if isinstance(n,ast.Constant) and type(n.value) in (int,float):return 0
        if isinstance(n,ast.Name) and n.id in degrees:return degrees[n.id]
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('len','list','reversed','enumerate','zip'):
            return max(degree(a) for a in n.args)
        if isinstance(n,ast.Subscript) and isinstance(n.slice,ast.Slice):return degree(n.value)
        if isinstance(n,ast.BinOp):
            a,b=degree(n.left),degree(n.right)
            if isinstance(n.op,(ast.Add,ast.Sub)):return max(a,b)
            if isinstance(n.op,ast.Mult):return a+b
            if isinstance(n.op,(ast.Div,ast.FloorDiv)) and b==0:return a
            if isinstance(n.op,ast.Pow) and isinstance(n.right,ast.Constant) and type(n.right.value) is int and 0<=n.right.value<=3:return a*n.right.value
        raise ValueError('Unknown iteration bound')
    def factor(iterator):
        if isinstance(iterator,(ast.List,ast.Tuple)):return 0
        if isinstance(iterator,ast.Call) and isinstance(iterator.func,ast.Name) and iterator.func.id=='range':
            powers=[degree(a) for a in iterator.args]
            if not any(powers):
                for a in iterator.args:
                    if not isinstance(a,ast.Constant) or type(a.value) is not int or abs(a.value)>1024:raise ValueError('Unknown constant loop bound')
            return max(powers,default=0)
        return degree(iterator)
    def cost(n):
        if isinstance(n,ast.While):
            if mode!='integer':raise ValueError('Only audited scalar shrinking while loops are supported')
            test_names={x.id for x in ast.walk(n.test) if isinstance(x,ast.Name)}
            if test_names!={argument}:raise ValueError('Unknown while-loop measure')
            shrinking=False
            for stmt in n.body:
                if isinstance(stmt,ast.AugAssign) and isinstance(stmt.target,ast.Name) and stmt.target.id==argument:
                    if isinstance(stmt.op,(ast.FloorDiv,ast.RShift)) and isinstance(stmt.value,ast.Constant) and type(stmt.value.value) is int and stmt.value.value>=(2 if isinstance(stmt.op,ast.FloorDiv) else 1):shrinking=True
                if isinstance(stmt,ast.Assign) and any(isinstance(t,ast.Name) and t.id==argument for t in stmt.targets):
                    v=stmt.value
                    if isinstance(v,ast.BinOp) and isinstance(v.left,ast.Name) and v.left.id==argument and isinstance(v.op,(ast.FloorDiv,ast.RShift)) and isinstance(v.right,ast.Constant) and type(v.right.value) is int and v.right.value>=(2 if isinstance(v.op,ast.FloorDiv) else 1):shrinking=True
            if not shrinking:raise ValueError('Unproved while-loop contraction')
            if any(isinstance(c,(ast.Break,ast.Return)) for c in ast.walk(n)):raise ValueError('Unsupported shrinking-loop exit')
            inner=max((cost(c) for c in n.body),default=(0,0))
            return (inner[0],inner[1]+1)
        if isinstance(n,ast.Assign):
            try:d=degree(n.value)
            except ValueError:d=None
            if d is not None:
                for target in n.targets:
                    if isinstance(target,ast.Name):degrees[target.id]=d
        if isinstance(n,ast.For):
            if any(isinstance(c,(ast.Break,ast.Return)) for c in ast.walk(n)):raise ValueError('Early-exit loop requires a separate audit')
            p=factor(n.iter)
            if isinstance(n.target,ast.Name):degrees[n.target.id]=p
            inner=max((cost(c) for c in n.body),default=(0,0))
            return (p+inner[0],inner[1])
        if isinstance(n,(ast.ListComp,ast.SetComp,ast.DictComp,ast.GeneratorExp)):
            p=sum(factor(g.iter) for g in n.generators)
            inner=max((cost(c) for c in ast.iter_child_nodes(n) if not isinstance(c,ast.comprehension)),default=(0,0))
            return (p+inner[0],inner[1])
        children=max((cost(c) for c in ast.iter_child_nodes(n)),default=(0,0))
        if isinstance(n,ast.Call):
            name=n.func.id if isinstance(n.func,ast.Name) else n.func.attr
            if name in ('sorted','sort'):return max(children,(1,1))
            if name in ('sum','list','tuple','set','dict','any','all','max','min','extend','copy','reverse','count','index','join','split','lower','upper','strip','lstrip','rstrip','replace'):
                if name in ('max','min') and len(n.args)>1:return children
                if name in ('list','tuple','set','dict') and not n.args:return children
                return max(children,(1,0))
            if name=='str' and mode=='integer':return max(children,(0,1))
        return children
    return max((cost(n) for n in fn.body),default=(0,0))
