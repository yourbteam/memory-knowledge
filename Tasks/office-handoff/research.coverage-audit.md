# research.md — Requirements Coverage Audit (Gate 2 of 3)

Breadth: is the requirement set complete and every requirement addressed or scoped out?

## Cycle 1 Assessment

### Requirement Inventory
| req_id | requirement | type | source |
| --- | --- | --- | --- |
| R1 | Standalone folder with ALL needed files | explicit | user |
| R2 | Separate installation-instructions document | explicit | user |
| R3 | Office machine — Claude (separately) | explicit | user |
| R4 | Office machine — Codex (separately) | explicit | user |
| R5 | Local Codex on this machine | explicit | user |
| R6 | All wired and in sync | explicit | user |
| R7 | "take advantage of the upgrades" — usage + verification, not just install | explicit | user |
| R8 | Path/username/node portability | implied | D2/D8 |
| R9 | Secrets hygiene | non-functional | guard rails |
| R10 | Fail-open / non-breaking | non-functional | existing design |
| R11 | Snapshot provenance + drift management | implied | D4 |
| R12 | Per-target verification (acceptance) | implied (R7) | playbook |

### Coverage Matrix
| req | status | addressed where |
| --- | --- | --- |
| R1 | addressed | §4 payload/ copies of every artifact |
| R2 | addressed | §4 INSTALL.md (single consolidated doc) |
| R3 | addressed | §2a + §4 flow (1) |
| R4 | addressed | §2b + §4 flow (2) |
| R5 | addressed | §2c gap + D6 + §4 flow (3) |
| R6 | addressed | §3 sync model (git + Azure + projections) |
| R7 | **partial → CGAP-001** | §3 explains sync but §4 does not require INSTALL to cover *usage/benefit + verification* per upgrade |
| R8 | addressed | D2, D8 |
| R9 | addressed | D7 |
| R10 | addressed | §1 fail-open tiers |
| R11 | addressed | D4 + MANIFEST |
| R12 | **partial → CGAP-001** | verification not yet a required deliverable element |

### Blocker Gap Ledger
| gap_id | sev | req | lens | evidence | why uncovered | planned fix | closure | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CGAP-001 | blocker | R7,R12 | omission/partial | §4 lists INSTALL.md but not its required contents: per-upgrade "what it does / how to benefit" + a per-target verification block | "take advantage of" + acceptance unaddressed | Amend §4 to require INSTALL to include, per target: install steps, a usage/benefit note per upgrade, and a verification block with concrete checks | §4 amended | closed |

## Cycle 1 Plan
Amend §4 to enumerate required INSTALL.md contents (steps + usage + verification per target).

## Cycle 1 Edits
§4: added the INSTALL.md required-contents list.

## Cycle 2 Assessment (fresh, no edits)
All 12 requirements now addressed: R7/R12 closed by the §4 contents requirement. Acceptance criteria
present (each requirement has a verifiable home). Post-edit new-gap pass: enumerating verification
introduces no conflict with D-decisions. No orphan mechanisms; no silently dropped requirement.

### Final Coverage Proof
| req | covered? | acceptance |
| --- | --- | --- |
| R1–R12 | yes | §4 (payload + INSTALL contents), §2c/D6 (local), §3 (sync), D7 (secrets) |

## Final Convergence Check
Fresh no-edit pass, zero blocker coverage gaps. **Converged (breadth).** Depth gate next.
