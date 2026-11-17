"""
convert.py -- turn a stdin/stdout solution into a plain function, and glue functions into one program.

A dataset solution looks like

    n = int(input())
    ...
    print(answer)

and becomes

    s1_n = None
    def stage1(_x):
        global s1_n
        s1_n = int(str(_x))       # the input() call now reads the argument
        ...
        return answer             # the print() call now returns its value

Every name the solution defines is prefixed with s1_, s2_, ... so two stages in one program cannot clash.
A chain of stages is then  composed(x) = stageK(...stage2(stage1(x))).

Only solutions that fit this shape are used.  A solution is rejected (raises Unconvertible) if, e.g.,
it reads anything besides one integer, prints more than once on some path, prints inside a loop,
uses classes, eval/exec, file I/O or fast-I/O tricks.
"""
import ast
import builtins
import copy
import importlib
import textwrap


class Unconvertible(Exception):
    """The solution does not fit the one-integer-in / one-print-out shape."""


# Text that marks a solution we do not try to convert.
FORBIDDEN_TEXT = ["os.read", "sys.stdin =", "sys.stdin=", "sys.stdout =", "sys.stdout=", "stdout.write",
                  "open(", "FastIO", "IOWrapper", "__import__", "eval(", "exec(",
                  "globals(", "locals(", "vars(", "getattr(", "setattr(", "delattr(", "__dict__"]

# Nodes that start their own scope: names assigned inside them are not module-level names.
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef,
          ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


# ================================================================== recognising input and print calls
def is_read_call(node):
    """input()  or  sys.stdin.readline()"""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Name) and f.id == "input" and len(node.args) <= 1 and not node.keywords:
        return True
    return (isinstance(f, ast.Attribute) and f.attr == "readline" and not node.args
            and isinstance(f.value, ast.Attribute) and f.value.attr == "stdin")


def is_int_read(node):
    """int(input())  or  int(input().strip())"""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "int"
            and len(node.args) == 1 and not node.keywords):
        return False
    arg = node.args[0]
    if is_read_call(arg):
        return True
    return (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "strip"
            and not arg.args and is_read_call(arg.func.value))


def reads_input(nodes):
    """Does any of these nodes still read standard input in some way?"""
    for root in nodes:
        for n in ast.walk(root):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in ("input", "raw_input"):
                    return True
                if isinstance(f, ast.Attribute) and f.attr in ("readline", "readlines", "read"):
                    return True
            if isinstance(n, ast.Attribute) and n.attr == "stdin":
                return True
    return False


def is_input_alias(stmt):
    """input = sys.stdin.readline   (or a def input(): ... readline ...) -- dropped, the read is replaced anyway."""
    if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "input"):
        return "readline" in ast.unparse(stmt.value)
    if isinstance(stmt, ast.FunctionDef) and stmt.name == "input":
        return "readline" in ast.unparse(stmt)
    return False


def is_print(node):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"


def contains_print(node):
    return any(is_print(n) for n in ast.walk(node))


def is_exit(stmt):
    """exit() / quit() / sys.exit()"""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        f = stmt.value.func
        if isinstance(f, ast.Name) and f.id in ("exit", "quit"):
            return True
        if isinstance(f, ast.Attribute) and f.attr == "exit" and isinstance(f.value, ast.Name) and f.value.id == "sys":
            return True
    return False


def check_one_print_per_path(stmts):
    """Each print becomes a return, so a second print on the same path would be lost.
    Raises Unconvertible if that can happen.  Returns True if some path through `stmts` prints."""
    printed = False
    for stmt in stmts:
        if is_exit(stmt):
            return False                                  # this path stops here
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)) \
                and contains_print(stmt):
            raise Unconvertible("print inside a loop / try / with")
        if isinstance(stmt, ast.If):
            prints_here = check_one_print_per_path(stmt.body) | check_one_print_per_path(stmt.orelse)
        else:
            prints_here = isinstance(stmt, ast.Expr) and is_print(stmt.value)
        if prints_here:
            if printed:
                raise Unconvertible("several prints on one path")
            printed = True
    return printed


# ================================================================== tree rewriters
class ReadToArgument(ast.NodeTransformer):
    """int(input()) -> int(str(_x)).  Only reads at the top level (not inside loops or functions) count."""

    def __init__(self):
        self.count = 0
        self.depth = 0

    def visit_Call(self, node):
        if self.depth == 0 and is_int_read(node):
            self.count += 1
            x_as_text = ast.Call(ast.Name("str", ast.Load()), [ast.Name("_x", ast.Load())], [])
            arg = node.args[0]
            if is_read_call(arg):
                node.args[0] = x_as_text                  # int(input())         -> int(str(_x))
            else:
                arg.func.value = x_as_text                # int(input().strip()) -> int(str(_x).strip())
            return node
        return self.generic_visit(node)

    def _inside(self, node):
        self.depth += 1
        node = self.generic_visit(node)
        self.depth -= 1
        return node

    visit_For = visit_While = visit_ListComp = visit_SetComp = visit_DictComp = \
        visit_GeneratorExp = visit_Lambda = _inside

    def visit_FunctionDef(self, node):
        return node                                       # reads inside helper functions are not replaced


class PrintToReturn(ast.NodeTransformer):
    """print(v) -> return v.  Only plain one-argument prints in the main flow are allowed."""

    def __init__(self):
        self.count = 0
        self.in_function = 0

    def visit_FunctionDef(self, node):
        self.in_function += 1
        self.generic_visit(node)
        self.in_function -= 1
        return node

    def visit_Expr(self, node):
        call = node.value
        if is_print(call):
            if self.in_function:
                raise Unconvertible("print inside a helper function")
            if len(call.args) != 1 or call.keywords or isinstance(call.args[0], ast.Starred):
                raise Unconvertible("print with several arguments / keywords / star")
            self.count += 1
            return ast.Return(value=call.args[0])
        return self.generic_visit(node)

    def visit_Call(self, node):
        self.generic_visit(node)
        if is_print(node):
            raise Unconvertible("print used inside an expression")
        return node


class MainIsTrue(ast.NodeTransformer):
    """if __name__ == "__main__":  ->  if True:"""

    def visit_Compare(self, node):
        self.generic_visit(node)
        if (isinstance(node.left, ast.Name) and node.left.id == "__name__" and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Eq) and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == "__main__"):
            return ast.Constant(True)
        return node


class DropGlobal(ast.NodeTransformer):
    """Remove `global` statements from the main flow; the stage function declares its own."""

    def visit_Global(self, node):
        return None


class Rename(ast.NodeTransformer):
    """Rename names according to `mapping` (variables, arguments, function names, global/except names)."""

    def __init__(self, mapping):
        self.mapping = mapping

    def visit_Name(self, node):
        node.id = self.mapping.get(node.id, node.id)
        return node

    def visit_arg(self, node):
        node.arg = self.mapping.get(node.arg, node.arg)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.name = self.mapping.get(node.name, node.name)
        return node

    def visit_Global(self, node):
        node.names = [self.mapping.get(n, n) for n in node.names]
        return node

    visit_Nonlocal = visit_Global

    def visit_ExceptHandler(self, node):
        self.generic_visit(node)
        if node.name:
            node.name = self.mapping.get(node.name, node.name)
        return node


# ================================================================== names
def assigned_names(stmts):
    """Names assigned at module level by these statements (not inside functions or comprehensions)."""
    names = set()

    def visit(node):
        if isinstance(node, SCOPES):
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        for child in ast.iter_child_nodes(node):
            visit(child)

    for stmt in stmts:
        visit(stmt)
    return names


def defined_names(stmts):
    """Names created by top-level imports and function definitions."""
    names = set()
    for stmt in stmts:
        if isinstance(stmt, ast.FunctionDef):
            names.add(stmt.name)
        elif isinstance(stmt, ast.Import):
            names.update((a.asname or a.name).split(".")[0] for a in stmt.names)
        elif isinstance(stmt, ast.ImportFrom):
            names.update(a.asname or a.name for a in stmt.names)
    return names


def expand_star_import(stmt):
    """from math import *  ->  from math import pi, sqrt, ...  (so every name can be renamed)."""
    if not isinstance(stmt, ast.ImportFrom):
        return stmt
    if stmt.module == "__future__":
        raise Unconvertible("__future__ import")
    if not any(a.name == "*" for a in stmt.names):
        return stmt
    if stmt.level:
        raise Unconvertible("relative star import")
    try:
        module = importlib.import_module(stmt.module)
    except Exception:
        raise Unconvertible(f"cannot expand star import of {stmt.module}")
    names = getattr(module, "__all__", None) or [n for n in dir(module) if not n.startswith("_")]
    return ast.ImportFrom(module=stmt.module, names=[ast.alias(name=n) for n in names], level=0)


# ================================================================== the conversion
def convert(source, index):
    """Turn one solution into module-level code defining  stage<index>(_x).  Returns that code as text."""
    for text in FORBIDDEN_TEXT:
        if text in source:
            raise Unconvertible(f"uses {text}")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise Unconvertible(f"syntax error: {e}")
    if any(isinstance(n, ast.ClassDef) for n in ast.walk(tree)):
        raise Unconvertible("class definitions are not supported")

    # 1. Split the solution: imports and helper functions stay at module level ("setup"),
    #    everything else becomes the body of the stage function ("body").  Docstrings are dropped.
    setup, body = [], []
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
            setup.append(stmt)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        else:
            body.append(stmt)

    for stmt in setup:
        if isinstance(stmt, ast.Import) and any("." in a.name and not a.asname for a in stmt.names):
            raise Unconvertible("dotted import")
        for n in ast.walk(stmt):
            if isinstance(n, (ast.Import, ast.ImportFrom)) and n is not stmt:
                raise Unconvertible("import inside a function")
    setup = [expand_star_import(stmt) for stmt in setup]
    for stmt in body:
        for n in ast.walk(stmt):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                raise Unconvertible("function defined inside top-level control flow")
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                raise Unconvertible("import inside top-level control flow")
    global_names = {name for stmt in setup + body for g in ast.walk(stmt)
                    if isinstance(g, ast.Global) for name in g.names}

    # 2. The input: exactly one top-level int(input()), which now reads the argument _x.
    setup = [s for s in setup if not is_input_alias(s)]
    body = [s for s in body if not is_input_alias(s)]
    reads = ReadToArgument()
    body = [reads.visit(copy.deepcopy(s)) for s in body]
    if reads.count != 1:
        raise Unconvertible(f"expected exactly one top-level int(input()), found {reads.count}")
    if reads_input(setup + body):
        raise Unconvertible("other input reads remain")

    # 3. The output: each print becomes a return.
    check_one_print_per_path(body)
    prints, main_true, drop_global = PrintToReturn(), MainIsTrue(), DropGlobal()
    body = [drop_global.visit(main_true.visit(prints.visit(copy.deepcopy(s)))) for s in body]
    body = [s for s in body if s is not None]
    setup = [main_true.visit(prints.visit(copy.deepcopy(s))) for s in setup]
    if prints.count == 0:
        raise Unconvertible("no print in the main flow")

    # 4. Drop imported names that are never used (this also trims expanded star imports).
    used = {n.id for s in setup + body for n in ast.walk(s) if isinstance(n, ast.Name)}
    kept = []
    for stmt in setup:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            stmt.names = [a for a in stmt.names if (a.asname or a.name.split(".")[0]) in used]
            if not stmt.names:
                continue
        kept.append(stmt)
    setup = kept

    # 5. Prefix every module-level name with s<index>_ so stages cannot clash.
    body_names = assigned_names(body)
    to_rename = body_names | global_names | defined_names(setup)
    keywords = {k.arg for s in setup + body for k in ast.walk(s) if isinstance(k, ast.keyword) and k.arg}
    if keywords & to_rename:
        raise Unconvertible("a keyword-argument name is also a renamed variable")
    if {"str", "int"} & to_rename:
        raise Unconvertible("the solution redefines `str` or `int`")
    mapping = {name: f"s{index}_{name}" for name in to_rename}
    rename = Rename(mapping)
    setup = [rename.visit(s) for s in setup]
    body = [rename.visit(s) for s in body]
    for stmt in setup:                                    # imports get the new name as an alias
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names:
                alias.asname = mapping[alias.asname or alias.name]

    # 6. Write the code: setup, initial values for the module-level variables, then the stage function.
    lines = [ast.unparse(s) for s in setup]
    for name in sorted((body_names | global_names) - defined_names(setup)):
        if hasattr(builtins, name):                       # e.g. `sum` is still the builtin until reassigned
            lines.append(f"{mapping[name]} = _b.{name}")
        else:
            lines.append(f"{mapping[name]} = None")
    lines.append(f"def stage{index}(_x):")
    if body_names:
        lines.append("    global " + ", ".join(sorted(mapping[n] for n in body_names)))
    lines.append(textwrap.indent("\n".join(ast.unparse(s) for s in body) or "pass", "    "))
    return "\n".join(lines)


def can_convert(source):
    try:
        convert(source, 1)
        return True
    except Unconvertible:
        return False


# ================================================================== whole programs
# Added to every program so it also works as a normal stdin -> stdout solution.
MAIN_BLOCK = '\n\nif __name__ == "__main__":\n    x = int(input())\n    print(composed(x))\n'


def build_program(sources):
    """One program with stage1..stageK and  composed(x) = stageK(...stage1(x)).  Without MAIN_BLOCK."""
    parts = ["import builtins as _b"]                     # gives access to the original builtins as _b.name
    call = "x"
    for i, source in enumerate(sources, 1):
        parts.append(convert(source, i))
        call = f"stage{i}({call})"
    program = "\n\n\n".join(parts) + f"\n\n\ndef composed(x):\n    return {call}\n"
    try:
        compile(program, "<chain>", "exec")
    except SyntaxError as e:
        raise Unconvertible(f"generated program does not compile: {e}")
    return program
