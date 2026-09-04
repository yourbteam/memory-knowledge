# Atom C retained-surface review

## Scope

Reviewed the four-path change surface derived by Atom Controller from the verified Atom B
baseline to the exact candidate bytes in the isolated promotion repository:

- `skills/atom-building-machinery/SKILL.md`
- `skills/atom-building-machinery/scripts/atom_controller.py`
- `tests/test_atom_building_machinery.py`
- `working-agreement/client-skill-projections.json`

Change-surface SHA-256:
`a8f6a2dfebd859a27429f6616ad67bc9dc741f431ba3f5f52ee82984857ab806`.

## Evidence inspected

- Official Development-Probe run `development-probe/run-final-7`: both approaches ran on all
  five declared real requests; `enforced-surface` won; final assembly
  `14b1c1392a14e72f43f74498d3db68e1468939da2e68194f1a07047d27e76d05` passed all five cases.
- The final self-hosted controller run declares `contract_surface` over its own
  `atom_controller.REQUEST_FIELDS`; its experiment receipt includes the AST key scan and observes
  that exact declared field.
- The real Step 12 order in `experiment/operator-order-final/relocated/operator-evidence/summary.json`
  returned `0, 2, 0` for named assigner, prose proof order, and generic renderer respectively.
- Both owner interviews are request-hash-bound and record `operator_choice: waive`; using the
  other request's receipt is measured as a refusal by the Development-Probe.
- The misspelled `ownership[].owenr` declaration refuses and names the available keys.
- Combined Atom A-C focused suite: 85 passed, including the self-host declaration and managed
  projection/install checks.
- Full unrestricted repository suite: 2,270 passed, 1 skipped. One unrelated
  prevention-materialization test remains red; neither its stored output nor any prevention source
  is in the three-atom diff.

## Findings

No blocking correctness, security, regression, or requirement-coverage finding remains in the
four-path Atom C surface. The implementation fails closed for missing declarations, unresolved
fields, direct model-written waivers, mismatched interview receipts, and undeclared payload reads.

The unrelated stale prevention materialization is not part of this atom and is not altered or
hidden by promotion.

## Conclusion

The reviewed surface is eligible for controller-recorded promotion. Real installation and both
client parity checks remain post-promotion operator-path validation, not evidence already claimed
by this review.
