# Direction check — meaningful lifecycle telemetry

The real candidate-and-runner prototype accepted and ranked two variants whose telemetry omitted
the required start and meaningful-work lifecycle and ended with an unsequenced integrity event.
The generic runner records only a telemetry digest, while the complete Development-Probe runner
does not expose one live feed across its nested stages, cases, and approaches.

The existing append-only telemetry approach remains sound. The stable fix boundary is code-owned
event emission and validation around candidate execution, plus aggregation into the complete-run
feed. Candidate output must remain separate from the parent experiment ledger: the wrapper owns
lifecycle events, validates namespaced operator events, and forwards only accepted records.
