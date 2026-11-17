# Executable generator atom contracts

These payloads use the common [atom envelope](../schemas/atom.schema.json).
Complete working records are created by [generation_demo.py](../examples/generation_demo.py).
The `generate` command consumes these atoms; the older `plan` command uses a different,
candidate-only input format. Source extraction remains dataset-specific.

## Python complexity (`bigo`)

```json
{
  "entry": "run",
  "source": "def run(values):\n    return [x for x in values]\n",
  "input_type": "list[int]", "output_type": "list[int]",
  "input_size": "length", "output_size": "length",
  "cost": {"n_power": 1, "log_power": 0},
  "size_transfer": {"power": 1, "coefficient": 1},
  "cost_evidence": "Upstream annotation or derivation with source revision.",
  "cases": [{"input": [1, 2], "expected": [1, 2]}]
}
```

The source contains one top-level unary entry function; module-local helpers are preserved.
Stages use separate modules without global renaming. Dependencies must already be installed.
Type names are adapter-certified; adjacent types and size measures must match.

Size is `length`, nonnegative integer `value`, or `constant` (one). Output size is annotated
as `coefficient * input_size ** power + offset`, with positive integer coefficient and
nonnegative integer power and offset (default zero). `SquareMatrix[int]` also checks square
shape and uses side length as n. Tuple references use normalized JSON transport with a
separate top-level runtime type check. Executed atomic and composite cases check that relation on supplied inputs.

Cost annotations are Theta(n^p log(n)^q), p/q nonnegative integers. Substitute intermediate
size powers into each cost, then take the dominant term of their sequential sum. Supported
generated labels are constant/logn/linear/nlogn/quadratic/cubic. Unsupported growth is rejected.
`np` remains an imported classification label, not an output of this polynomial/log generator.
Upstream cost and universal size claims are trusted annotations; finite cases do not prove
asymptotic behavior or infer complexity from arbitrary Python source.

## Java clone equivalence (`codeclone`)

```json
{
  "entry": "run", "input_types": ["int"], "output_type": "int",
  "a_members": "public static int run(int x) { return x + 1; }",
  "b_members": "public static int run(int x) { return x + 1; }",
  "label": "equivalent", "imports": ["java.util.*"],
  "suites": {"type_driven": [[0], [2]], "cross_substitution": [[1], [-1]]},
  "suite_evidence": {
    "type_driven": "Generator revision, seed and suite hash.",
    "cross_substitution": "Original suite identity and substitution provenance."
  }
}
```

Member source is wrapped in a public class `Atom`, with a public static entry. Preserve
helpers/fields and use `Atom` for self-references. Stages and sides use separate packages.
Imports are qualified names without statements or semicolons. The adapter must normalize
upstream instance methods and dependencies correctly; the renderer does not guess semantics.

Supported types: boolean/byte/short/int/long/float/double/char/String and their one-dimensional
arrays. Inputs are JSON scalars/arrays; char is one UTF-16 character. Null is supported for
String only. Void, generics, custom reference types and multidimensional arrays are unsupported.

Default `clone_mode=aggregation` uses separate component arguments and Object[] results with
exception-class tags, following the retained public version's style. Optional `chain` supports
exact-type output-to-input chains, including multi-argument methods. The first downstream
parameter matching the previous return type is bound; other arguments remain public driver
inputs. At most one negative atom is allowed. Both supplied
atomic suites confirm the label; at least two named suites with evidence are required.
These need not be statistically independent. Recovered regression and generated boundary
cases share witnesses. Original EvoSuite source is recovered, but the full historical runner
and CodeWalk admission suites are not replayed. Suite provenance is an adapter responsibility.

Aggregation composite tests vary each component's supplied cases against baseline arguments.
Chain tests vary each stage's free public arguments and execute the whole chain. Each side receives fresh
values. Observations include returns, array contents and exception class tags, not mutations
of unreturned caller arguments. EQ is suite-relative. Negative composites need a real witness;
injected atomic labels alone cannot admit a chain that masks the difference.

## Pytest repository repair (`bugfixing`)

Required payload:

- `repository`: existing local Git checkout path; no implicit network cloning.
- `base_commit`: full commit hash; `fix_time`: ISO-8601 with a time zone, or an
  explicitly recorded `base_time` fallback if the actual fix timestamp is unavailable.
- `gold_patch`, `test_patch`: Git unified diff text, including new-file metadata when needed.
- `modified_files`: exactly the source paths touched by the gold patch.
- `test_ids`: explicit unique pytest node IDs, e.g. `tests/test_math.py::test_add`.

Atoms share a repository and connect through common gold-modified paths. The earliest fix
time proposes the base. Git archive exports it without history; an isolated Git context
applies every test patch. Public files are captured before tests or gold execution. Binary
files are base64-encoded in JSON and materialized as bytes. Symlink entries are rejected.

Each atom's target tests run in a fresh copy of the common prepared state. Every requested
test must fail normally. Collection/setup errors, skips and wrong counts block the run.
All gold patches must apply together and the union of target tests must pass in another
fresh copy. Gold patches cannot edit target test files. This is targeted FAIL_TO_PASS,
not a PASS_TO_PASS guarantee. Environment dependencies must already exist.

The v1 backend supports pytest repositories. Other repository test frameworks need a
validated result adapter/backend, not a shell command treating any nonzero exit as a live bug.
It does not automatically resolve every historical benchmark image or working directory.

## Structured Verus (`verus`)

```json
{
  "input_type": "u64", "output_type": "u64", "requires": [],
  "ensures": "result == x / 2",
  "segments": [{"exec": "x / 2"}]
}
```

One argument `x`, one return `result`; supported types are bool and signed/unsigned Rust
Copy integer scalars. This is structured generation, not arbitrary Rust AST rewriting.
Vector, borrowing, multiple-input and helper-heavy historical atoms need an extended backend.

A segment has exactly one of `exec`, `proof`, or `annotation`. Executable segments are shared
by task/reference. Proof segments become reference-only `proof { ... }`; annotation segments
are reference-only loop invariants/decreases clauses. Split executable segments around loop
headers to place annotations. The source adapter must classify syntax correctly. This is
not an untrusted candidate grader; proof-bypass tokens are rejected conservatively.

Ensures become fixed stage predicates. The driver feeds real outputs forward and returns
a tuple of intermediate values so its fixed contract can describe their actual predicates.
This is a new construction format, not a byte-for-byte historical driver. Preconditions
remain intact; Verus must justify every downstream precondition.

Admission verifies every atomic reference and the joint reference with zero errors, then
requires positive verification errors for the unfinished task. Missing verification counts,
including parse/type/toolchain failures, block rather than admit. The actual Verus version
and outputs are recorded. See [official installation instructions](https://github.com/verus-lang/verus/blob/main/INSTALL.md).

## Recovered source extensions

Repair may supply `interaction_files`, a source-file subset for graph coupling, while
retaining the complete gold patch. Target-test/configuration edits and unsafe paths are rejected.

With `verus_mode: source_recovered`, real upstream task/reference modules replace scalar
segments. The adapter supplies function metadata, executable projection and fixed step/driver
wrappers. Validation compares executable helpers, spec helpers, contracts and wrappers against
reference source. Recovered vectors, borrows and multiple arguments are supported; unrestricted
Rust rewriting is not. Downstream preconditions remain intact. Reference verification must
succeed. The specific early missing-loop-decreases proof diagnostic is accepted only after
a separate `--no-verify` type check succeeds; unrelated parse/type failures never establish
a valid unfinished task. See [source reconstruction](source-reconstruction.md).

## Shared size contracts and standalone sources

A recovered multi-argument Python function may use `input_size: shared` and a public
record `{n, args}`. Its `input_contract.argument_layout` lists `array`, `string` or
`integer` for each argument. Sequence lengths must equal n; integer arguments lie
between zero and n. The harness checks this contract before every atomic and composite
execution. The public question includes the size-contract details. Such records are
explicit root inputs; unproved shared-record output annotations are rejected.

Recovered Verus atoms with `standalone_only: true` may retain original non-chainable
argument/return types. They still require matched executable/spec helpers and fixed drivers,
reference proof success and unfinished-task proof failure. They cannot enter deeper chains.
See the [paper-sized reconstruction guide](paper-sized-reconstruction.md).
