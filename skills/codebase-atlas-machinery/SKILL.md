---
name: codebase-atlas-machinery
description: Capture and retrieve a deterministic tracked-file inventory with source-linked facts and reviewed flow overlays. Use when a codebase map must be pinned to actual checkout bytes and rejected when stale.
---

# Codebase Atlas

Use the standard-library CLI at `scripts/atlas.py` from this skill directory. Keep the database outside the target repository.

Index a repository with `index --repo PATH --db DB`. Query a saved inventory with `query --db DB --snapshot SNAPSHOT [--graph]`. A flow JSON contains the exact `snapshot_id` and `extractor_identity`; attach it with `flow-add --db DB --snapshot SNAPSHOT --input FLOW.json`. A separate review JSON contains the assigned `overlay_id` and exact `overlay_content_hash`, plus the review decision and basis; attach it with `flow-review --db DB --snapshot SNAPSHOT --overlay OVERLAY_ID --input REVIEW.json`. Retrieve both with `flow-query --db DB --snapshot SNAPSHOT --overlay OVERLAY_ID`.

For an unclassified plain question, derive lexical terms from its wording and run `discover --db DB --repo PATH --terms TERM... --max-tokens N` before opening source files. Discover requires exactly one saved snapshot with the current extractor and an exact match to the live checkout's canonical root, HEAD/ref, structured status, and tracked-file identities. It refuses stale, old-extractor, missing, or multiple matches. It ranks source-anchored route/action candidates by exact lexical-token overlap and a deterministic tie order; it does not choose the semantic path, add synonyms, or resolve handler calls. Inspect the returned action and controller anchors, including `included_candidates` and `omitted_candidates`, then verify actor and payload details in current source. If a bounded result omits candidates, refine the lexical terms and rerun; never treat top-ranked routes as exhaustive or as semantic selection. The limit is an ASCII stdout-byte proxy, not a model-token count; complete candidates are never truncated.

The Luna mapping worker may prepare bounded, source-anchored flow conclusions from the saved graph. Before creating an accepted review receipt, obtain a separate GPT-6.1 Sol High review of the assignment and the exact flow claims; bind the receipt to the reviewed overlay content hash. Code checks snapshot and overlay integrity but does not substitute for that semantic review.

Use `focus --db DB --repo PATH --snapshot SNAPSHOT --overlay OVERLAY_ID --max-tokens N` only after `flow-query` reports an accepted receipt. Focus rechecks canonical repository root, HEAD/ref, structured Git status, and each tracked path's presence, type, mode, size, and SHA-256. It does not rebuild the source graph. A stale or failed check returns no claims and a nonzero status; reindexing and reviewing a changed overlay requires a new explicit receipt.

The bundled `data/taggable-api.atlas.sqlite` contains reviewed customer-photo browsing and selfie-upload maps. Their snapshot IDs and overlay IDs are recorded in the corresponding `examples/*-flow.json` and `examples/*-review.json` files. On the captured checkout, browsing fits all five conclusions in a 10,000-byte focus limit; selfie upload needs a 15,000-byte limit for all five. Check `omitted_claims` before treating any bounded response as the complete flow.

The focus limit is a conservative ASCII stdout-byte proxy that includes the final newline. It is not a model-token count and excludes prompt overhead. Claims are selected as complete units in overlay order; citations retain their complete spans and point to a deduplicated path/hash table. Complete stale diagnostics are subject to the same cap; if one cannot fit, stdout is empty and stderr reports the required byte count. The command never truncates claims, citations, or stale evidence.

Review receipts are local immutable audit records, not cryptographic signatures or provider authentication. Atlas verifies their binding to the exact snapshot, overlay hash, and extractor identity; it does not validate the truth of reviewed claims. Receiver-name invocation candidates are non-traversable syntax observations and do not establish parameter binding. Type-name candidates are not resolved graph edges. Never treat missing, rejected, stale, or mismatched review evidence as accepted.
