# Sequence Discovery Log: report-v3-optimized-mirror

Status: discovery
CreatedAtUtc: 2026-07-06T15:07:59Z
RegisteredSequenceMatch: none

## Intended Outcome

Optimized parallel mirror of the 84-column V3 report export (export-new-report-v3), validated column-by-column against the golden XLS for June 2026, current XLS handler untouched

## Why This Looks Repeatable

same optimization pattern as the dashboard; the golden-capture + column-diff validation will recur for future report changes

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| XLS output + remove global interceptor | export-new-report-v3-optimized-xls (V3ReportExcelWriter); cell-for-cell diff vs golden XLS | Generated XLS is cell-for-cell IDENTICAL to the current report (0/12516 mismatches, same 152x84 dims, same 52244 bytes). Global ForceCommandTimeoutInterceptor + Program.cs CommandTimeout removed (optimized handler self-sets per-command 600s); JSON endpoint still 200 in ~8.6s. | Optimized XLS endpoint ~10s vs current >230s timeout. Ready to switch the button's data source when desired. |
| Engagement group + indexes -> full exact mirror | add-report-perf-indexes.sql via WebJob apply-schema; POST export-new-report-v3-optimized; validate2.py positional | 79/79 data columns match golden exactly across all 149 operators (positional, 0 name mismatches). Optimized endpoint ~37s vs current >230s timeout. col14/col29 were validation artifacts (duplicate operator names; XLS paren convention) — resolved by positional+magnitude comparison. | Indexes applied: Users(LastTourId,CreatedAt) INCLUDE(FaceId), ProductImage(TourTimeSlotsId,Created), UserProductImage(UserId,IsMe). Current XLS handler untouched. |
| Build optimized parallel endpoint + live-validate vs golden (June 2026) | POST /api/admin/export-new-report-v3-optimized (JSON) vs report_golden.json (parsed from current XLS) | Endpoint returns 149 operators in ~21-35s (vs current >230s timeout). 62/79 data columns exact-match golden. Remaining: engagement group (cols 32-36,41-48,51,67-69) not yet ported; col29 is XLS paren/sign convention (value matches); col14 revshare edge on 1/149 operators. | Order-level metrics (financial/payout/redemption/service-fee/kiosk-web/discount) all validated. Current export-new-report-v3 XLS handler untouched. |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
