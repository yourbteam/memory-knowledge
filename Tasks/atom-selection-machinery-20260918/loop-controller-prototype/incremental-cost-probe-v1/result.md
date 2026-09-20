# Incremental update cost comparison

The eight extra lens calls did not justify a mandatory ten-call update on this case. Both answers gave the same practical current-position conclusion; neither is a clean winner on all frozen evidence criteria.

| Path | Calls per answer | Provider time | Input tokens | Output tokens |
|---|---:|---:|---:|---:|
| Update + final check | 2 | 55.5 seconds | 117,095 | 2,563 |
| Update + eight lenses + final check | 10 | 575.5 seconds | 592,687 | 29,713 |

The experiment made 11 actual calls: the initial update was shared. All used GPT-5.5 high. No retries, revisions, live answer changes or promotion.

The shorter answer retained the important new findings and uncertainty. Its 22 quotations matched supplied text, but it dropped direct historical evidence references while retaining the historical claims. The full path restored these and added useful source detail; however, its first lens joined five separate values into one purported quote. All later lenses and its final check retained that defect.

Both final checks said keep. The calling assistant evaluated raw answers against all eight frozen criteria and audited exact quotations; this was not independent blind judging. Seven criteria were satisfied by both; evidence-reference quality was partial for both for different reasons.

Recommendation: do not spend the 70-call batch now. Preserve existing evidence references during the smaller incremental update and recheck this same case before replacing the installed path. One case does not establish general reliability or downstream selection equivalence.
