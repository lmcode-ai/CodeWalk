# Adding a dataset to the composition generator

The canonical executable API is `codewalk/composition/Backend`. The older `plan` modules
and `DomainPlugin` tutorial remain compatibility examples. New backends should use the
four-method interface below and let the shared pipeline own sampling and publication.

## 1. Source adapter or new backend?

A dataset supplies atoms. A backend defines interaction, rendering and admission semantics.
A second Python complexity dataset usually needs a source adapter emitting `bigo` atoms,
not another sampler. A new language, observation model or semantic oracle needs a backend.
Changing returned-value equivalence to include caller-visible mutation is an oracle change:
version it and collect new admission evidence rather than silently reusing old labels.

## 2. Extract normalized atomic JSONL

Each UTF-8 JSONL line follows [atom.schema.json](../schemas/atom.schema.json):

```json
{
  "schema_version": 1,
  "domain": "bigo",
  "id": "original-function-id",
  "source_id": "original-source-family",
  "provenance": {
    "uri": "https://example.org/upstream",
    "revision": "immutable-upstream-revision",
    "license": "MIT"
  },
  "payload": {}
}
```

Populate payload according to [domain contracts](generation-atom-contracts.md). A source
adapter is an ordinary dataset-specific script. There is no mandatory HF dependency or
automatic mining service. Published composite records are not automatically atomic inputs.

Adapter requirements:

1. Preserve original IDs, revisions, licenses and source families. Do not assign unrelated
   source IDs to functions from the same repository/program when source-disjoint splits matter.
2. Split source families before composition for unseen-source evaluation. Distinct task IDs
   do not prevent component overlap. Keep split manifests and their hashes.
3. Use language-aware parsing for extraction/renaming. Preserve helpers, imports, state,
   exceptions and numeric semantics. Reject unsupported syntax rather than rewriting by guess.
4. Supply actual tests, reference annotations and cost evidence. A boolean approval flag
   cannot replace missing admission evidence or an unavailable historical test suite.
5. Keep references private. The adapter's source, extraction config and immutable upstream
   revision should accompany a release, but golds must not enter the model workspace.
   Preserve required copyright notices and license texts in distributed source/data;
   an SPDX label in private provenance alone does not satisfy upstream redistribution terms.

## 3. Implement one uniform backend

Subclass [Backend](../codewalk/composition/base.py):

```python
class MyBackend(Backend):
    name = "my_domain"
    directed = True

    def validate(self, atom):
        super().validate(atom)
        # Reject invalid payloads before sampling.

    def compatible(self, left, right):
        # The actual interaction relation, not an admission decision.
        ...

    def render(self, atoms, root):
        # Write executable work/reference files under root.
        # Return BuiltTask(root, public_projection, private_judge_data).
        ...

    def admit(self, built, runner):
        # Execute atomic and whole-reference checks via runner.run().
        # Raise Reject or InfrastructureError on failure.
        ...
```

Do not duplicate sampling, task IDs, retries, provenance or publication logic. The pipeline
owns those responsibilities; backends own domain semantics. The complete runnable extension
is [affine_backend.py](../examples/affine_backend.py):

```bash
python -m examples.affine_backend --output outputs/affine-demo
```

It generates integer-affine programs, derives a private reference, executes atomic/composite
checks and rejects identity-baseline tasks. Testing two points is exact only because its
canonical syntax is affine and closed under composition; it is not a general equivalence oracle.

## 4. Define graph semantics and supported bindings

Use `directed=True` for output-to-input chains: the sampler extends only the last node.
Use False for symmetric connected groups: it expands all selected nodes' neighbors.

Compatibility must describe real types, representations and allowed bindings. Admission
still checks downstream preconditions, size growth and label preservation. Document extra
inputs/adapters and reject unsupported cases. Type compatibility alone proves none of these.

Atoms within a task are distinct. `max_per_source` caps source reuse within a task, not
across the whole corpus. The fixed-seed sampler is reproducible but not uniform over all
possible connected subgraphs. Include the sampling policy in the dataset card.

## 5. Separate public problems and private references

Render returns:

```python
BuiltTask(root,
    public={"files": {"driver.py": source}, "question": instruction},
    private={"label": reference_label, "reference": reference})
```

Public `files` maps safe relative paths to UTF-8 source text. Optional `binary_files_base64`
holds binary repository assets. Private reference files and compilation work stay below
`root/work/`; atomic records, execution logs, judge data and admission evidence stay under
the run's `private/` tree. Never include target labels, gold patches or reference proofs in
the public projection. The pipeline writes only admitted tasks to public `tasks/`.

Task IDs are routing metadata, not prompt content. The manifest records component provenance
and should not be copied into a model prompt. Publish only the intended public artifacts.

## 6. Execute real admission

Return both gates with evidence only after real checks succeed:

```json
{"atom_gate": true, "reference_gate": true, "tests": "actual domain evidence"}
```

This dictionary is a backend contract, not a proof mechanism. A new backend that sets flags
without executing a justified oracle is incorrect. Pin its tools and retain raw evidence.

- `Reject`: invalid group, source compilation failure, wrong reference, masked negative,
  unsupported cost growth or already-solved unfinished task. Another group may be sampled.
- `InfrastructureError`: unavailable tool/image, timeout, broken test collection/setup or
  missing verifier evidence. Stop as blocked; do not report admission or model success.
- `ValueError`: malformed inputs/configuration. Correct them before generation.

Use `Runner.run(argv, cwd, name=...)`, with argument lists and no shell. Record versions,
exit codes and outputs. For test-based EQ, explicitly state its finite-suite scope. For
complexity, identify trusted source annotations separately from checked size substitution.

## 7. Register once and run

Add the backend class to [registry.py](../codewalk/composition/registry.py). `generate` CLI
choices follow that registry. The affine example demonstrates runtime registration; a
distributed domain should be registered centrally. The separate artifact download registry
describes published datasets, so add an HF URL only after that dataset actually exists.

```bash
python -m codewalk generate my_domain --atoms normalized-atoms.jsonl \
  --level 3 --count 100 --seed 42 --max-candidates 10000 \
  --max-per-source 2 --config generation-config.json --output outputs/my-run
```

Optional config `label_quotas` maps private label names to nonnegative counts summing to
`--count`. Quotas may require a larger candidate budget. Never relabel tasks to fill them.

Output must be new or empty. `dataset.jsonl` is written only when the requested count passes
admission. Incomplete runs produce `dataset.partial.jsonl`, `complete=false`, and nonzero
CLI exit status. Never rename a partial export to claim completion.

The manifest records seed, atom/config/implementation and backend-source hashes, selected source IDs,
public-task and admission hashes, rejection reasons and Python/platform. Tool outputs are
private execution evidence. Full reproducibility also requires identical toolchain and
dependency versions; matching a seed alone is insufficient.

## 8. Execution environment

Native mode runs code on the host and is intended for trusted atoms/fixtures. External
source code should use Docker mode with a prebuilt immutable image:

```json
{
  "execution": "docker",
  "image": "your-registry/codewalk-tools@sha256:YOUR_64_HEX_DIGEST",
  "timeout_seconds": 120
}
```

Replace the placeholder with the actual digest. The image must contain all required tools
and repository dependencies. Network is disabled; capabilities are dropped; CPU, memory and
process limits apply; only the candidate work directory is mounted. Archive/patch preparation
uses host-side Git. Dependency installation is not automatic. Docker mode is implemented but
must be validated against your pinned image before claiming support for that environment.

`$PYTHON` resolves to the current interpreter natively and `python` in Docker. Native `java`,
`javac` and `verus` paths may be overridden. `verus_command` supports an argument-list prefix.
`tool_env` permits toolchain home/PATH overrides only; arbitrary provider keys are not forwarded.

## 9. Tests and publication

Before release, add tests for:

- malformed atoms, duplicate IDs, incompatible edges and source reuse limits;
- actual compilation/execution and both admission gates;
- domain-specific failures: masking, size growth, patch conflicts, unsatisfied preconditions;
- missing tools/timeouts producing blocked runs;
- rejected tasks absent from public output and references absent from public inputs;
- requested-count/quota exhaustion, no overwrite, reproducibility and implementation hashes.

Run tests on actual upstream atoms as well as synthetic fixtures. Document supported syntax,
types, unsupported cases, observation model, oracle limitations, dependencies, source splits
and licenses. The included fixtures exercise the generator; they do not certify a new dataset.

## Real-source adapters and explicit candidate groups

Use the [source recovery workflow](source-reconstruction.md) as an end-to-end adapter example.
Keep raw upstream source, pinned revision, extracted atoms and admission evidence separate.
The optional `generate --groups` JSONL provides `atom_ids` for preferred groups, such as
original component groupings. The shared pipeline still validates IDs, source limits, graph
compatibility, rendering and both admission gates. Explicit plans cannot bypass admission.
Long directed chains may use bounded lookahead; report exhausted search as a limitation
instead of weakening contracts or inventing missing atoms.
