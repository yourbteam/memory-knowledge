# Frozen real case — Atom 17 (2026-09-05)

Round 5 atom D (`s12-card-approver`, united-partners) started through the Atom 16 door with
`activation_cards[].approver` declared introduced; its experiment was recorded; the canonical
`src/up_harness/tactical_roadmap.py` then gained the field (SHA-256 a094ab48167f27ee9fbb28e31ba1c8aed8fcf47779b551aeda7def04ebf8d577).
The installed Claude controller (SHA-256 65e1165868bcdedcdc226807ae685baf31c631f90c97462a89de53316240aa83) then refused to load the run:

- `status <run>` → see d-run.status.{stderr,exit}.txt
- `change-surface <run> <out>` → see d-run.change-surface.{stderr,exit}.txt

`s12-card-approver.controller-run/` is a byte copy of the run at that moment (ledger, baseline,
experiment event); `s12-card-approver.atom-request.json` is the request it was started with.
Repository root recorded in the run: /Users/kamenkamenov/united-partners.
