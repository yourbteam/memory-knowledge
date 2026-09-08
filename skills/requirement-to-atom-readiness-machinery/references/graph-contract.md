# Typed graph and queue contract v1

This prerequisite publishes shape only. Nodes use exactly six types: requirement, evidence, authority_decision, contradiction, verification and atom_candidate. Each has a closed, type-specific record. Code owns node IDs, edge identities and condition classification; a model cannot grant authority or readiness.

Allowed edge names are supports, refutes, requires, governed-by, conflicts-with, verified-by, maps-to-atom and precedes. Admission must reject unknown endpoints, forbidden endpoint types, duplicates, self-dependencies and cycles in requires or precedes. Canonical graph order is node ID and edge tuple.

The queue orders blocking class, dependency layer, earliest linked requirement ordinal, source ordinal and stable node ID. Classes are integrity, mandatory-evidence, contradiction, semantic, research, planning, verification and owner. Only the first item is public. Unchanged input yields the same graph and next action; no all-green graph may claim readiness before later package verification exists.

## Atom 6 initial graph and next action

`readiness_controller.py start` builds the initial graph from explicit checked manifests. `status`, `verify-replay` and `advance` reconstruct that initial snapshot and expose only its first unresolved action, graph hash and queue count. The complete queue stays in `queue.json`; the graph stays in `graph.json`. Altering either projection is refused. This initial deterministic `advance` performs no model calls, probes, owner decisions or evidence-response mutations; those belong to the remaining interview and phase-routing atoms.

Requirement identities come from the sealed exporter. Legacy bindings preserve old and current exact text and, where unequal, the captured two-seat mapping evidence. Conditions create pending verification or owner-decision nodes; no producer claim can create a verified node. Other typed node records remain available to the subsequent interview and atom-compilation capabilities. Dependencies are explicit, never inferred from input order. Missing, foreign or cyclic links are refused before publication. A graph with no unresolved queue still cannot certify readiness.
