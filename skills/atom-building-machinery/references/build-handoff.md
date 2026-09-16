# Build-only handoff

The caller supplies an approved atom; selection is outside this contract. Approval is recorded
from authorization actually provided by the owner or authorized calling workflow. This record
binds scope; it is not cryptographic proof of human presence and cannot create authorization.

Use a packet with exactly these fields:

- `schema_version`: `"build-1"`.
- `goal`, `state`: the approved fixed goal object and observed state.
- `atom_request`: the exact controller request described in SKILL.md.
- `candidate`: only `outcome`, `contribution`, `proof`; outcome equals atom_request.outcome.
  These describe what to deliver, not comparative priority or alternatives.
- `bindings`: repository-relative `goal` and `state` JSON source paths.
- `evidence`: nonempty unique records with repository-relative `path`, SHA-256 and exact `text`.
  Sources must be regular, unlinked, within the product root and unchanged.
- `approval`: `path` and exact nonempty `quote` from a registered authorization JSON source.
  That source has `approved: true`, `repository_root`, `atom_request_sha256` and a nonempty
  `authorization_reference` locating the actual owner/caller authorization. Hash the request
  as UTF-8 json.dumps(request, sort_keys=True, separators=(',', ':')).
- `progress`: the existing delivery claim: `kind` (product, machinery-reliability or
  autonomy-transfer), `claim`, `responsibility`, `before` (description and source quotes),
  `after` (description and owner), and `proof`. Responsibility is null except for autonomy
  transfer. Autonomy claims additionally retain their existing complete workflow baseline
  and `workflow` contract; removing selection does not weaken contribution verification.

Prepare a receipt locally (no model calls):

```bash
python3 scripts/build_admission.py <packet.json> <new-receipt.json> \
  --goal-context <fixed-goal-context.json> --source-root <repository-root>
python3 scripts/atom_controller.py start <atom-request.json> <new-run> \
  --build-packet <packet.json> --build-receipt <new-receipt.json>
```

Initialize the goal sequence once as described in SKILL.md. Existing active builds cannot be
skipped. Goal context retains the existing schema: schema_version 1, goal, approved_source_sha256.
The prepared driver retains `value_packet` and `value_receipt` as transport field names; point them
to the build-only files. New build packets never require selection_binding or atom-selection-gate.

Delivery checking uses build_completion.py and its own model boundary after existing exact-payload
transfer authorization. No ranking occurs at completion. Historical value receipts use their
historical verification path; preserve them unchanged.
