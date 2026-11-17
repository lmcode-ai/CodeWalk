# Composition architecture

The executable implementation is `codewalk/composition/`, invoked by `generate`.
See [atomic contracts](generation-atom-contracts.md) and the
[backend extension guide](adding-a-dataset.md). The `codewalk/domains/` modules described
below remain the older candidate-only `plan` interface.

Each domain provides seven responsibilities:

1. **Extract** source artifacts into atoms with stable IDs, source revisions, original
   references, tests/specifications, and licensing metadata.
2. **Relate** atoms that can coexist or exchange data, without modifying their semantics.
3. **Sample** an ordered chain or connected group of N distinct atoms.
4. **Compose** one task and retain a separate trusted reference.
5. **Admit** only after the domain's actual liveness/label and joint-reference checks.
6. **Project** an answer-free model input. Gold patches, labels and reference proofs stay
   in the trusted construction/grading process.
7. **Evaluate** generated answers under the same semantic oracle, recording model failure
   separately from unavailable environments or grader crashes.

## Graph semantics

Repair uses a symmetric graph: two bugs in the same repository are adjacent if their gold
patches touch a common file. Grow a group from the union of neighbors of all selected nodes.
This produces a connected subgraph, not necessarily a clique or a path.

The three chain domains use directed edges. Extend **only the last selected node**.
Taking a neighbor of any earlier node can produce a branching graph, not a chain. The local
paper's generic frontier description and its chain description are not equivalent; the
new planner makes that distinction explicit. It is not a byte-for-byte reproduction of the
missing sampler.

`graph.sample_groups` builds an O(pool_size²) compatibility graph, then samples with a fixed
seed. Distinct ordered chains remain distinct; undirected groups deduplicate by sorted IDs.
A bounded search raises if it cannot produce the requested count. Uniform choice from each
frontier does not imply uniform sampling over every connected subgraph. Source reuse limits
must be explicit; the paper's N=10 Verus construction allows a source program at most twice.

## Composition is more than concatenation

- Repair: propose a shared snapshot and test it; dates alone do not prove that bugs coexist.
- Verus: actual intermediate values must satisfy the fixed predicates and downstream contracts.
- Complexity: propagate output sizes before combining costs; identical types do not imply
  identical size growth.
- Clone chains: downstream stages may erase a difference introduced by a negative pair;
  execute the whole composite rather than deriving NEQ solely from an atomic label.

The planning modules describe these obligations. The executable backends render and check
them under the supported atomic contracts, keeping admission logs and private references.

## Reproducibility record

An admitted task should retain atom/source IDs, ordered edges/bindings, source and generator
commit hashes, seed, compiler/verifier/image digests, public-input hash, reference hash,
admission evidence and final label/specification. Keep references outside the model workspace.
Split source families before composition when claiming unseen-source generalization;
disjoint task IDs alone do not prevent shared component leakage.
