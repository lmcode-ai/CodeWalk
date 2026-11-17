# Complexity analysis (Big-O)

Executable generation is now available through `generate bigo`: separate Python modules,
a real data-flow driver, executed reference cases, and explicit monomial/log cost substitution.
It requires normalized annotated atoms. See [contracts](../generation-atom-contracts.md)
for supported growth and the distinction between trusted annotations and executed checks.

The local paper uses CodeComplex-derived Python snippets and 80 tasks at each of N=1,2,3,10.
No public CodeWalk complexity repository was found on 2026-11-05. Its registry entry is
intentionally unset; no dataset URL, code, or original label derivation is fabricated.

## Construction recipe

1. Group source snippets by problem ID, choosing the intended source variant per problem.
2. Extract a designated entry function, its parameter/return types, supporting definitions,
   annotated complexity and provenance. Preserve I/O, globals and helper semantics.
3. Add a directed edge for a type-compatible output/input binding. Normalize adapters
   explicitly; language type compatibility is not a proof of a safe semantic adapter.
4. Namespace functions and supporting definitions; create a driver that passes each output
   into the next function. Additional inputs remain explicit driver inputs.
5. Record intermediate-size transfer functions and derive the end-to-end cost. If stage i
   receives size m_i(n), compose its annotated cost T_i(m_i(n)), include adapter/driver costs,
   and combine sequential costs. For example, an n²-sized output followed by quadratic work
   can yield n⁴; it is not merely the maximum atomic label.
6. Check the derivation and supported output class. Reject unsupported growth, unknown
   transfers, or a result outside the released vocabulary instead of rounding to a convenient
   class. Preserve evidence for the paper's domain-specific admission checks.

Types and atomic labels alone are insufficient to reconstruct the missing size derivations.
The old planning implementation requires `size_transfer` metadata but does not assign a
reference label. The executable backend derives labels within its explicitly supported
algebra and rejects unsupported growth.

## Evaluation

One model call, no tools; 4096 output tokens and 300 seconds according to the local appendix.
The prompt selects exactly one label from `constant`, `logn`, `linear`, `nlogn`, `quadratic`,
`cubic`, `np`. Here `np` is the historical dataset label; do not interpret the name as a proof
of NP-completeness. Timeouts/budget exhaustion and unparseable model answers are failures.

The new release parser accepts an exact standalone label after whitespace stripping. The
original parser is unavailable, so this behavior is versioned as a new strict parser rather
than claimed identical to historical scoring. Model/provider identifiers, temperature and
other unspecified API parameters must be supplied and recorded for an actual run.

## Source recovery update (2026-11-06)

The [source reconstruction report](../source-reconstruction.md) records the newer real-source recovery,
679 admitted tasks and its limitations. Earlier counts and availability statements in this
document describe the initial public release or earlier fixture verification, not this new bank.

## Active paper-sized profile

The [paper-sized reconstruction guide](../paper-sized-reconstruction.md) supersedes the earlier subset as
the active release target. It specifies all 1,706 paper slots, actual clone data-flow chains,
expanded complexity atoms, complete L1 Verus recovery and exact restoration of published
repair definitions. Fresh admission and imported historical definitions remain distinct.
