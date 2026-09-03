# Direction check — experiment terminalization

The generic runner appends `experiment_started` before variant execution and evaluation. It catches only `EvaluatorTimeout`; every other `ExperimentError` raised after that point reaches `main`, which prints stderr and exits without writing `summary.json` or a terminal experiment event. The stable boundary is the runner-owned lifecycle after the start event, not individual evaluator adapters.

The existing independent-evaluator design remains sound. Terminal summary creation must become a guaranteed runner invariant while preflight refusals before `experiment_started` remain output-free.
