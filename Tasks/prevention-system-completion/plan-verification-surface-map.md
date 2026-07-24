# Plan verification surface map

Plan revision: `6976a97529c702f64d812ff9cf683f6d870eca0084a807186176107aa5300248`

| id | subsystem or artifact | why in scope | risk | authoritative evidence | implementation risk if missed |
| --- | --- | --- | --- | --- | --- |
| COV-01 | prevention contracts, canonical owner registry, `SEQUENCES.md` projection | one owner and typed dispatch require a closed authority | high | `scripts/work_memory.py:registry_rows`; `operations/sequences/SEQUENCES.md`; research `CUR-ENTRYPOINT`/`CUR-TYPED` matrices | runtime keeps parsing prose or permits multiple/raw owners |
| COV-02 | work-memory event schema, atomic ledger, legacy replay | all correction, journal, learning, and metrics facts must share durable authority | high | `scripts/work_memory.py:EVENT_FIELDS`, transaction and summary paths; current ledger | new events break old runs or create a second truth |
| COV-03 | prevention controller, selector, legacy raw entry points | pre-dispatch mandatory selection must own effects | high | `scripts/sequence_guard.py`; `scripts/sequence_checked_exec.py`; work-memory raw CLI boundaries | direct commands bypass selection or raw inputs mutate state |
| COV-04 | all 25 owner adapters and external black-box evidence | system-wide entrypoint and resume claims depend on every registry row | high | registry owner matrix; available automation paths and terminal signals | composite/external rows remain prose-only or are falsely counted from mocks |
| COV-05 | Codex project hooks and host capability admission | the model must not remember to consult the registry | high | official PreToolUse support; `.codex` project layer; tool-grant evidence | unsupported actions bypass prevention while run is called governed |
| COV-06 | correction prohibition and causal learning lineage | verified fixes must become mandatory and reusable | high | blocker fingerprints; correction/verification events; observer, bootstrap, lifecycle, promotion, reconciliation | repeat failure executes or lineage remains a manual/post-hoc join |
| COV-07 | full-unit budget admission across long owners | long work must not start without complete remaining capacity | high | research admission formula and long-controller matrix | expensive unit strands after partial execution |
| COV-08 | transition/effect journal, reconciliation, branch/worktree/run identity | resume must advance without duplicate external effects or cross-run consumption | high | research and promotion journals; reconciliation checkpoint; workflow-state evidence | crash or branch change duplicates effects or corrupts another run |
| COV-09 | canonical metrics, representative corpus, acceptance report | all six success conditions require event-backed proof | high | work-memory metrics; research timing; fixed acceptance formulas | synthetic/prose evidence creates a false pass or hides overhead |
| COV-10 | migration of skills/runbooks, compatibility containment, full review | new controller must be the normal path and preserve unrelated dirty-tree work | medium | `skills/sequence-runner/SKILL.md`; registry documents; existing tests and git status | operators keep invoking legacy raw commands or implementation overwrites unrelated changes |

Control flow to verify: host action → strict intent → capability admission → selector → budget admission → transition/effect preparation → typed owner → reconciliation/verification → terminal event → metric query.

Persistence flow to verify: branch/worktree/run identity → existing atomic work-memory ledger → prepared/committed transition and effect events → resume reconciliation → generated views/reports.

Approval boundaries to preserve: discovery qualification, reconciliation manifest approval, promotion and registered verification; no phase-ledger, external-repository, user-global config, commit, push, deploy, or secret operation.
