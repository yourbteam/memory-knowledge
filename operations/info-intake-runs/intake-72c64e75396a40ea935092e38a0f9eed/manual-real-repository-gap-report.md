# Comprehensive Real-Repository Alignment Report

## Report identity

- Intake: `intake-72c64e75396a40ea935092e38a0f9eed`
- Assessment date: 2026-08-24
- Run state: `first_layer_complete_with_preserved_gaps`
- Ruling population checked: **124 of 124 current relationship rulings**
- Composition: **108 readable rulings assessed against the repositories; 16 intake gaps preserved and explicitly accounted for**
- Assessment method: static trace from annotated-page ruling to the active React page assembly, direct API request, API V3 projection, and authoritative V3 calculation code

## Executive verdict

The implementation is **not aligned end to end** with the annotated page bundle.

The API has a credible V3-based foundation: it gathers the V3 metrics for the requested scope and date range and projects the spreadsheet-equivalent fields into named API metrics. Many single-number mappings therefore exist and are correct. The largest defects are introduced after that point in the React assembly layer:

1. Both dashboards use one chart-selected date range to populate widgets that separately claim to be **Today**, **YTD**, and **current pay period**. Correct fields are therefore displayed for the wrong time period.
2. The portal expects a `netRevenueTrend` response that the API does not produce. All time-series requirements depending on it are empty or non-functional.
3. Several formulas drift from the annotated/V3 definition, including internal dashboard total revenue, redemption liability, operator dashboard averages, package/non-package counts, and internal payout-report row splits.
4. Report history, automatic period filing, report generation, opening, PDF download, persisted refunds, Stripe refunds, support data, system issues, and inactive-location monitoring are not implemented.
5. Sixteen run rulings are not product requirements at all: the intake correctly preserved them as source-reading gaps or rejected visual connections. They remain unassessed by design and are listed individually below.

This is a **static code verdict**, not a live-value verdict. No authenticated page/API run or production-data comparison was performed, and no relevant automated test suite was found in the portal or API repository. A value marked aligned below means its implemented formula/path matches the ruling; it does not prove the currently deployed page is serving correct live values.

## Repository baseline and real data path

| Repository | Revision assessed | Role |
|---|---|---|
| `taggable-operator-portal` | `main` / `c5a57ad4ec11dc1e4eb7d4eefa295e1653424a93` | Active React pages and client-side assembly |
| `taggable-api` | `main` / `e03a2dda682fe0cf9ec4888a7b4ed91d8174e11a` | Portal endpoint, V3 gathering, projection, and calculation |
| `taggable-admin-spa` | `main` / `e954a3a22e32e0b3be767ffafa2c79c891c77ba5` | Checked; not the active implementation of these pages |
| `taggable-server` | `feature/historical-archive-db-docs` / `8fea86f67db1608c705adc52b2f1e13b8ba1d5da` | Checked for a separate portal middleware assembly; none found |

The active path is:

`React page -> portal request builder -> /api/admin/portal/{dashboard|payouts} -> V3TourMetricsService.GatherAsync -> PortalV3MetricProjector -> V3 Derive/V3PayoutMath`

There is no separate calculation middleware in the checked repositories. The React portal calls the API endpoint directly. The relevant evidence is:

- Portal request and endpoint construction: `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-analytics.ts:27`
- API base path: `/Users/kamenkamenov/taggable-operator-portal/src/services/api_path.ts:1`
- Portal response pagination and admission: `/Users/kamenkamenov/taggable-operator-portal/src/hooks/usePortalAnalytics.ts:55`
- API scope/range gathering and projection: `/Users/kamenkamenov/taggable-api/src/Taggable.Api/Application/PortalAnalytics/PortalReportingQuery.cs:98`
- Spreadsheet-column-equivalent metric mapping: `/Users/kamenkamenov/taggable-api/src/Taggable.Api/Application/PortalAnalytics/PortalV3MetricProjector.cs:20`
- Authoritative V3 derivation: `/Users/kamenkamenov/taggable-api/src/Taggable.Api/Application/AdminReports/ReportV3OptimizedHandlers.cs:35`
- Authoritative payout arithmetic: `/Users/kamenkamenov/taggable-api/src/Taggable.Api/Application/AdminReports/V3PayoutMath.cs:28`
- V3 spreadsheet headers: `/Users/kamenkamenov/taggable-api/src/Taggable.Api/Application/AdminReports/V3ReportExcelWriter.cs:34`

## Verdict vocabulary

- **Aligned**: implemented formula, source, scope, and visible behavior match the readable ruling in the static path.
- **Partial**: a material part matches, but another required part is absent or wrong.
- **Not aligned**: an implemented behavior uses the wrong formula, scope, endpoint, or target.
- **Not implemented**: the UI may be present, but the required data path or action is absent/inert.
- **Observed**: the ruling only records visible page structure; the structure exists but is not itself a calculation requirement.
- **Intake gap**: the run deliberately rejected or could not read the proposed source relationship. It must not be converted into a product requirement without better source evidence.

| Verdict | Rulings |
|---|---:|
| Aligned | 32 |
| Partial | 30 |
| Not aligned | 16 |
| Not implemented | 28 |
| Observed | 2 |
| Intake gap | 16 |
| **Total** | **124** |

## Cross-page defects

### X-01 — Dashboard time scopes are collapsed into one request

Both dashboard views build one date range from the currently selected chart range and use the returned rows for every widget. The default internal and operator range is two months. As a result, cards labelled Today, YTD, and Pay Period can all display two-month aggregates. This affects otherwise-correct BY, AF, AE, AC, W, X, AH, and AT mappings.

Evidence: `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:549`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:570`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:575`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:145`.

### X-02 — Time-series source is declared by the portal but absent from the API

The portal types and model builders expect `netRevenueTrend`. The API response contract and handler return only metric rows and selectors; no trend is produced. The portal deliberately falls back to an empty series. This blocks payout-over-time, revenue-breakout, weekly net-payout, monthly capture/conversion, and internal company-performance behavior.

Evidence: `/Users/kamenkamenov/taggable-operator-portal/src/types/portal-analytics.ts:73`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:193`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:282`, `/Users/kamenkamenov/taggable-api/src/Taggable.Api/Application/PortalAnalytics/PortalReportingQuery.cs:190`.

### X-03 — Historical report persistence does not exist on the page path

The payout repository rows are synthesized from the current API response. Each operator gets one generated `V3-{companyId}` row. Open, PDF, export, and generate actions call the local `notWiredUp` notification. No period-close filing path is present.

Evidence: `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:341`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:355`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:249`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:685`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:702`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:742`.

### X-04 — Refunds are temporary browser state, not a source-backed value

Refunds can be typed into the payout pages and are subtracted on operator KPI cards. They are not loaded from Stripe, do not include a refunded-transaction count, are not persisted, disappear on reload, and do not consistently flow into internal-table net totals.

Evidence: `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:236`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:278`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:588`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:665`.

## Page 1 — Operator Payout Reports

Source ruling: `source-000003-v6.json` — 15 readable rulings, 0 intake gaps.

| Ruling | Verdict | Required meaning | Real-repository result |
|---|---|---|---|
| 000001 | **Partial** | Current half-month net payout = AF plus refunds represented negatively | AF/current-period preset is correct; manually entered refunds are subtracted, but they are ephemeral and not source-backed. |
| 000002 | **Aligned** | Package count F+K; non-package count C+I | Payout model explicitly sums full-price and abandoned-cart package/non-package transaction fields. |
| 000003 | **Aligned** | Content revenue X; paid transactions W | `contentRevenue` uses `totalOperatorPayoutPaidTransactions`; paid count uses `totalPaidTransactions`. |
| 000004 | **Aligned** | Code fees AD; codes used AC | Model maps redemption fees and total redemption codes to the card. |
| 000005 | **Partial** | Stripe refund amount and count; manual/dash until connected; unknown must not look like zero | Blank manual amount input exists and unknown is not forced to `$0`; Stripe integration, count, and persistence are absent. |
| 000006 | **Aligned** | Photo revenue uses X | Current report content/photo revenue uses the projected X equivalent. |
| 000007 | **Aligned** | Duplicate X-to-photo mapping | Same implemented mapping as 000006. |
| 000008 | **Aligned** | Codes-used row value uses AC | Synthesized row uses `totalRedemptionCodes`. |
| 000009 | **Aligned** | Code-fee row value uses AD | Synthesized row uses `redemptionCodeFees`, displayed negative. |
| 000010 | **Partial** | Jul 16–31 report supplies W/X/AC/AD/AF+refund values | The visible row fields are assembled from the right V3 metrics, but it is a current-response synthetic row, not a saved Jul report. |
| 000011 | **Partial** | Duplicate report-row field map | Same result as 000010. |
| 000012 | **Aligned** | First-row photo revenue uses X | Synthetic row uses X equivalent. The sample `$101,503.80` was not value-tested. |
| 000013 | **Aligned** | Duplicate first-row X mapping | Same implemented mapping as 000012. |
| 000014 | **Aligned** | Duplicate first-row X mapping | Same implemented mapping as 000012. |
| 000015 | **Partial** | Selected operator has searchable report history by date/report number | Search filters the rows it receives, but only one synthetic live-scope row exists; historical filing/open/PDF behavior is absent. |

Primary evidence: `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-analytics.ts:14`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:301`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:327`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:355`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:263`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:683`.

## Page 2 — Internal Payout Reports Repository

Source ruling: `source-000009-v1.json` — 10 readable rulings, 3 intake gaps.

| Ruling | Verdict | Required meaning | Real-repository result |
|---|---|---|---|
| 000001 | **Partial** | Net payout AF; projected close = elapsed-day average extrapolated over pay period | Net AF is correct. `projectedClose` is explicitly unavailable. |
| 000002 | **Aligned** | Live/as-of date is visible | The model uses request end date and labels the scope live. Exact sample date was not value-tested. |
| 000003 | **Partial** | “We owe” = positive AF and count only operators with positive AF | Amount correctly sums positive AF; count uses `>= 0`, so zero-balance operators are incorrectly counted. |
| 000004 | **Aligned** | “They owe” = negative AF and count negative operators | Negative AF split and `< 0` count are implemented. |
| 000005 | **Not aligned** | Content BU; service BX; total BY; add-on $0 | Total BY is correct, but current report content uses BS and service uses BT+BX. Add-ons are unavailable rather than a defined `$0`. |
| 000006 | **Not implemented** | Repository contains persisted Jul 16–31 all-operator report | Current API rows are synthesized into a live-scope report; no saved historical repository source is read. |
| 000007 | **Intake gap** | Cropped callout relationship | Source text is cut off; no product ruling may be inferred. |
| 000008 | **Intake gap** | “Open live period-to-date report” target | The source did not visibly connect that control to the proposed orange card. |
| 000009 | **Not aligned** | Report row: net AF, we-owe positive AF, they-owe negative AF, revenue BY | Net and BY are correct; row `weOwe` uses X and `theyOwe` uses AD instead of AF sign splits. |
| 000010 | **Intake gap** | Proposed annotation-to-third-row connection | The arrow terminates at the first Jul row, not the third row. |
| 000011 | **Not aligned** | Duplicate report-row formula | Same wrong row split as 000009. |
| 000012 | **Not aligned** | Duplicate report-row formula | Same wrong row split as 000009. |
| 000013 | **Not implemented** | Auto-file at period close; row opens detail; PDF downloads operator statement | All three actions lack a persistence/action path; open and PDF explicitly report “not wired up.” |

Primary evidence: `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:340`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:341`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:426`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:438`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:451`.

## Page 3 — Operator Payout Dashboard

Source ruling: `source-000010-v1.json` — 16 readable rulings, 2 intake gaps.

| Ruling | Verdict | Required meaning | Real-repository result |
|---|---|---|---|
| 000001 | **Aligned** | Company selector is admin-only; operators are scoped to their company | UI labels the selector admin-only and API applies authorization plus company filters. |
| 000002 | **Partial** | Net payout = content revenue − code fees − refunds | V3 AF already equals X−AD and the manual refund is subtracted. Refund is not persisted/source-backed. |
| 000003 | **Not implemented** | Payouts-over-time chart plots summary values across selected range | Chart series are empty because API supplies no `netRevenueTrend`. |
| 000004 | **Aligned** | Content card uses payout-equivalent values for selected range | Range request and X/W/package/non-package KPI assembly are present. |
| 000005 | **Intake gap** | Proposed Net-payout-to-code-fees visual connection | No arrow connects those cards; formula text alone was insufficient. |
| 000006 | **Not implemented** | D7 chart tooltip contains net/sent/owed/refunds | Empty trend means no real D7 point or tooltip values. |
| 000007 | **Partial** | Refunds can be entered manually | Manual entry exists, but only in component state and with no transaction count. |
| 000008 | **Aligned** | Content add-ons show NA until live | KPI displays `NA`. |
| 000009 | **Aligned** | Duplicate add-on placeholder ruling | Same result as 000008. |
| 000010 | **Not implemented** | Package/non-package chart by time, toggles, totals, counts, combined tooltip | Toggle UI exists and formulas are prepared, but no time-series data reaches it. |
| 000011 | **Aligned** | Add-on table values or “Coming soon” | Content/merch add-on columns display “Coming soon.” |
| 000012 | **Aligned** | Location-table codes use AC | Uses total redemption codes. |
| 000013 | **Aligned** | Location-table net payout uses AF | Uses net operator payout. |
| 000014 | **Aligned** | Location-table amount owed uses AD | Uses redemption code fees, displayed negative. |
| 000015 | **Aligned** | Duplicate AF-to-net mapping | Same result as 000013. |
| 000016 | **Aligned** | Location-table content revenue X and count W | Uses total operator paid revenue and total paid transactions. |
| 000017 | **Not implemented** | Generate report freezes selected range into saved statement | Button calls `notWiredUp`; no save path exists. |
| 000018 | **Intake gap** | Callout-to-Merch-column connection | Arrow reaches Content Add-ons only, not Merch Add-ons. |

Additional gap: the custom calendar changes a label and then requests the standard `period` preset; it does not send the selected custom dates. Evidence: `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:212` and `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:839`.

Primary evidence: `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:287`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:297`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:301`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:324`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:742`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:746`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:787`.

## Page 4 — Operator Dashboard

Source ruling: `source-000011-v1.json` — 29 readable rulings, 6 intake gaps.

All formula verdicts on this page incorporate X-01: unless stated otherwise, a correct base metric is still only **Partial** because the page feeds it the chart-selected range rather than the day/YTD/pay-period range named by the widget.

| Ruling | Verdict | Required meaning | Real-repository result |
|---|---|---|---|
| 000001 | **Partial** | Today net revenue uses AF | AF equivalent is used, but for the selected chart range rather than today. |
| 000002 | **Partial** | Paid count W and W/AE percentage | W and AE equivalents are used, but for the wrong period. |
| 000003 | **Partial** | Transactions today uses AE | AE equivalent is used, but for the wrong period. |
| 000004 | **Partial** | Codes AC and AC/AE percentage | AC and AE equivalents are used, but for the wrong period. |
| 000005 | **Not aligned** | Package count F+K and share over AE | Model uses F only; abandoned-cart package K is omitted. Period is also wrong. |
| 000006 | **Not aligned** | Non-package count C+I and share over AE | Model uses C only; abandoned-cart single I is omitted. Period is also wrong. |
| 000007 | **Not implemented** | Refresh refetches Live Today and All Locations Today | Button only resets local guest-count state; it does not call the analytics retry/refetch path. |
| 000008 | **Not aligned** | Current conversion AT; prior-seven-day average AT | Current value averages AT across current request rows; “7-day avg” uses BR/session-to-transaction and has no prior-seven-day request. |
| 000009 | **Aligned** | Live section is scoped to selected location | Client groups API rows by location and selects that group for every Live card. |
| 000010 | **Partial** | Current capture AE/guest; prior-seven-day average of same | Current displayed capture uses AE/manual guest. The average uses AU from the selected request, not prior-seven-day AE/guest. |
| 000011 | **Partial** | Duplicate AC/AE ruling | Same result as 000004. |
| 000012 | **Intake gap** | Preserved AE all-locations identity | Proposed source unit actually said AF, so the relationship was rejected. |
| 000013 | **Partial** | All-locations-today net = sum AF | Sum AF is used, but for the chart-selected range. |
| 000014 | **Partial** | Donut center is leading daily-revenue location/share | Leading-location/share math exists, but its inputs cover the wrong period. |
| 000015 | **Partial** | Legend AF, AF share, and AE count by location | Field/grouping math is correct; period is wrong. |
| 000016 | **Not aligned** | Average transaction = sum X / sum W | Page calculates AF / AE. |
| 000017 | **Intake gap** | Proposed relationship between average and transaction count | Neighboring metrics have no connector. |
| 000018 | **Intake gap** | Proposed `$20.16` average-revenue/visitor endpoint | `$20.16` belongs to average revenue/transaction; visitor value is a separate `$3.67` field. |
| 000019 | **Not aligned** | YTD capture = sum AE / sum guest count | Model averages AU (`uniqueVisitorToFaceRecognitionRate`) over rows and does not force YTD scope. |
| 000020 | **Not implemented** | Monthly capture and conversion points | `performance.history` is always empty. |
| 000021 | **Not aligned** | YTD average revenue/visitor = sum X / guest count | Model uses AF / unique visitors, and scope is not guaranteed YTD. |
| 000022 | **Partial** | YTD conversion = average AT | Model averages AT, but over the selected chart range rather than guaranteed YTD. |
| 000023 | **Partial** | Earned-to-date = AF for current pay period | AF is used, but current chart-selected range supplies the rows. |
| 000024 | **Not implemented** | Projected close extrapolates elapsed-period AF | Value is explicitly unavailable. |
| 000025 | **Not implemented** | Previous pay-period AF total | Value is explicitly unavailable. |
| 000026 | **Not aligned** | Next payout is next 1st or 16th | Model uses request end date and generic “scheduled settlement.” |
| 000027 | **Intake gap** | Clipped time-range selector | Right edge is unreadable; no faithful relationship was admitted. |
| 000028 | **Partial** | Selected-period total paid = sum AF across locations | Aggregate total uses AF for selected range, but its required time-series chart is empty. |
| 000029 | **Intake gap** | Action Items contents | Screenshot is cropped below the heading; entries cannot be assessed from this ruling. |
| 000030 | **Not implemented** | Revenue chart has date and money axes | With no trend source there is no meaningful real series/scale to validate. |
| 000031 | **Not implemented** | Weekly total AF tooltip with per-location AF breakout | Missing trend prevents weekly points and tooltip. |
| 000032 | **Not implemented** | Date ticks position the net-revenue series | Missing trend prevents a real dated series. |
| 000033 | **Not implemented** | Hover guide and tooltip show total/per-location values | Missing trend prevents the behavior. |
| 000034 | **Intake gap** | Partially cropped chart-panel endpoint | Panel is too obscured/cropped to bind the proposed relationship. |
| 000035 | **Partial** | All-locations-today transactions = sum AE | AE sum is used, but for the selected chart range. |

Primary evidence: `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:145`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:163`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:169`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:193`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:250`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:503`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:520`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:541`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:549`.

## Page 5 — Internal Payout Dashboard

Source ruling: `source-000012-v1.json` — 19 readable rulings, 2 intake gaps.

| Ruling | Verdict | Required meaning | Real-repository result |
|---|---|---|---|
| 000001 | **Aligned** | Taggable revenue = BY across all operators | KPI uses total Taggable revenue. |
| 000002 | **Not implemented** | Daily selected-period chart with toggleable series | Toggle controls exist, but trend arrays are empty because API provides no trend. |
| 000003 | **Aligned** | Net paid to operators = AF across all operators | KPI uses net operator payout. |
| 000004 | **Intake gap** | Date-selector relationship | Callout covers part of selector and no endpoint is visible. |
| 000005 | **Aligned** | Paid-to-operators content = X across all operators | KPI uses total operator payout paid transactions. |
| 000006 | **Not implemented** | D7 tooltip values | No real D7 point exists without a trend source. |
| 000007 | **Not implemented** | Purple D7 “owed to us” marker | No real marker exists without a trend source. |
| 000008 | **Aligned** | Invoiced codes = AD across all operators | KPI uses redemption code fees. |
| 000009 | **Aligned** | Right KPI cards are Content BU and Service BX | Current KPI construction uses the projected BU and BX equivalents. |
| 000010 | **Intake gap** | Clipped right-side KPI | Card title/subtitle is not fully readable. |
| 000011 | **Not implemented** | Daily BU/BX breakout and combined total popup | Series are defined but empty because API provides no trend. |
| 000012 | **Not implemented** | Blue D7 marker exists | No data point is produced. |
| 000013 | **Not implemented** | Duplicate selected-period chart behavior | Same missing trend as 000002. |
| 000014 | **Observed** | “By operator” table and selected-period context are visible | Structure is present. |
| 000015 | **Not implemented** | Orange revenue-series line exists | No trend data reaches the chart. |
| 000016 | **Aligned** | Per-operator total revenue = BY | Table groups rows by company and sums total Taggable revenue. |
| 000017 | **Aligned** | “We send them” = positive AF | Sign split sums positive net operator payout. |
| 000018 | **Aligned** | “They owe us” = negative AF | Sign split sums negative net operator payout and displays magnitude. |
| 000019 | **Aligned** | Net = all AF | Table total uses net operator payout. |
| 000020 | **Partial** | Add manually populated refunds column | Editable refund column exists, but values are ephemeral and do not alter table net totals. |
| 000021 | **Not implemented** | Generate report freezes selected range into saved internal report | Button explicitly reports that generation/saving is not wired. |

Primary evidence: `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:289`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:297`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:319`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:335`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:523`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/payouts/index.tsx:588`.

## Page 6 — Internal Dashboard

Source ruling: `source-000013-v1.json` — 19 readable rulings, 3 intake gaps.

All Today/current-pay-period verdicts also incorporate X-01: the implementation supplies the selected company-performance range, not an independently correct day or pay-period range.

| Ruling | Verdict | Required meaning | Real-repository result |
|---|---|---|---|
| 000001 | **Partial** | Today NPR BY and transaction count AE | BY and AE equivalents are used, but for the selected chart range. |
| 000002 | **Not aligned** | Company-performance time series: NPR BY and total collected N+T | “Series” is up to 20 company/location rows labelled by company, not dates. NPR uses BY; total uses N+R, not N+T. |
| 000003 | **Not aligned** | Average conversion = average BR across operators | Code computes aggregate successful transactions / total sessions, which is not average BR. |
| 000004 | **Not implemented** | Online locations = positive AU; idle locations = non-positive AU | Card counts companies, labels them operators, sets online=total companies, and leaves idle unavailable. |
| 000005 | **Not aligned** | Duplicate time-series BY and N+T ruling | Same company-row pseudo-series and N+R formula as 000002. |
| 000006 | **Partial** | Unique users today = AH after AH becomes unique faces | Uses projected AH/unique visitors, but card still says “Total users” and period is wrong. The upstream semantic change to unique faces was not live-value verified. |
| 000007 | **Partial** | Current pay-period section shows BU, BX, and BY | BY total is used, but the visible sub-breakdown repeats BY as Photo and does not show BU/BX separately; period is also wrong. |
| 000008 | **Partial** | Net payout owed = AF across operators for current pay period | AF is used, but scope is the selected performance range. |
| 000009 | **Not aligned** | Total revenue collected = N+T | Model uses N+R (`totalFullPriceRevenue + operatorDiscountRevenue`), omitting T/abandoned-cart discount revenue and substituting R. |
| 000010 | **Not aligned** | Redemption liability = sum of negative AF | Model uses AD/redemption code fees instead of negative AF. |
| 000011 | **Observed** | Customers group appears within Support section | Structural container exists, but it receives no support data. |
| 000012 | **Intake gap** | Obscured Operators metric group | Annotation covers target; no readable relationship was admitted. |
| 000013 | **Not implemented** | Operators support requires ticketing/plugin integration | API model returns no groups; page displays unavailable message. |
| 000014 | **Not implemented** | Open-support action opens support | Button routes to a generic “not implemented” notice. |
| 000015 | **Not implemented** | Customers open count is displayed from data | `openCount` and groups are unavailable/empty. |
| 000016 | **Partial** | Per-operator NPR = BY across operator locations | Grouping and BY sum are correct, but current-pay-period scope is not independently requested. |
| 000017 | **Intake gap** | Proposed issue-callout-to-Open-button connection | Arrow lands beside the Payment webhook row, not the Open button. |
| 000018 | **Not implemented** | System issues Open action provides issue detail | Issues are always empty; Open routes to generic unimplemented Support target. |
| 000019 | **Partial** | Operator net = AF across operator locations | Grouping and AF sum are correct, but current-pay-period scope is not independently requested. |
| 000020 | **Not implemented** | Inactive locations = zero AU for 72 hours | Model has no inactivity threshold or rows; UI still says inactive operators and unavailable. |
| 000021 | **Intake gap** | Cropped ranking-callout origin | Callout opening extends beyond source crop. |
| 000022 | **Partial** | Duplicate per-operator BY ruling | Same result as 000016. |

An additional related formula defect affects the visible Customer Gross/Total Revenue measures: `grossRevenue` and top-operator `gross` also use N+R, not N+T.

Primary evidence: `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:133`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:145`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:154`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:202`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:218`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:225`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:229`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:232`, `/Users/kamenkamenov/taggable-operator-portal/src/services/portal-page-models.ts:235`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:447`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:448`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:450`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:451`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:459`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:465`, `/Users/kamenkamenov/taggable-operator-portal/src/pages/dashboard/index.tsx:472`.

## Practical defect list by priority

### Critical — values can look valid while representing the wrong period or formula

1. Split dashboard data acquisition into explicit day, previous-seven-day, YTD, current-pay-period, previous-pay-period, and selected-chart-period scopes. Do not reuse one response for all labels.
2. Implement a real dated trend contract in the API or remove the untrue portal expectation. All chart requirements depend on it.
3. Correct internal dashboard total revenue from N+R to N+T everywhere it is used, including company performance, pay-period total, and top-operator gross.
4. Correct redemption liability from AD to the negative-AF sum required by the annotation.
5. Correct operator-dashboard package/non-package counts to F+K and C+I.
6. Correct operator-dashboard average transaction to X/W, average visitor to X/guest, and capture to AE/guest with the exact required scopes.
7. Correct internal payout-report row “we owe” and “they owe” to positive/negative AF, and exclude zero balances from the positive-operator count.
8. Correct internal payout-report content/service split to BU/BX.

### High — required user workflows are presently inert

9. Add durable payout-report persistence, automatic period-close filing, report detail, PDF generation/download, and real Generate report behavior.
10. Add a persisted refunds source and transaction count, then integrate Stripe when available; ensure every relevant net total uses the same refund record.
11. Make Refresh issue a real manual analytics request/refetch for Live Today and All Locations Today.
12. Make custom date selection send the chosen start/end dates rather than the standard current-period preset.
13. Add projected close, previous-period total, and next-payout schedule calculations.

### Product/data integrations still absent

14. Add support/ticket metrics and real navigation.
15. Add system-issue data and issue-detail navigation.
16. Add inactive-location data based on the agreed 72-hour/no-upload rule and rename the card from operators to locations.
17. Confirm and enforce the AH semantic change from sessions/visitors to unique faces/users before relying on the card as the requested measure.

## The 16 preserved intake gaps

These are complete coverage items, not implementation failures. They require clearer source evidence before they can become requirements.

| Page/source | Ruling | Preserved reason |
|---|---|---|
| Internal Payout Reports / 000009 | 000007 | Callout text is cut off at source boundary. |
| Internal Payout Reports / 000009 | 000008 | “Open live period-to-date report” has no visible target connection. |
| Internal Payout Reports / 000009 | 000010 | Arrow reaches first Jul row, not proposed third row. |
| Operator Payout Dashboard / 000010 | 000005 | No arrow connects Net payout card to code-fees card. |
| Operator Payout Dashboard / 000010 | 000018 | Arrow reaches Content Add-ons, not Merch Add-ons. |
| Operator Dashboard / 000011 | 000012 | Required AE identity was proposed from an AF source unit. |
| Operator Dashboard / 000011 | 000017 | Neighboring average/count metrics have no connector. |
| Operator Dashboard / 000011 | 000018 | Proposed `$20.16` visitor endpoint contradicts visible `$3.67` visitor field. |
| Operator Dashboard / 000011 | 000027 | Time-range selector is clipped. |
| Operator Dashboard / 000011 | 000029 | Action Items contents are below the crop. |
| Operator Dashboard / 000011 | 000034 | Chart panel is mostly cropped/obscured. |
| Internal Payout Dashboard / 000012 | 000004 | Date selector is covered and has no visible destination. |
| Internal Payout Dashboard / 000012 | 000010 | Required KPI is clipped at crop edge. |
| Internal Dashboard / 000013 | 000012 | Operators metric group is covered by annotation. |
| Internal Dashboard / 000013 | 000017 | Arrow lands beside issue row, not Open button. |
| Internal Dashboard / 000013 | 000021 | Callout origin is cropped. |

## Coverage closure

| Source projection | Total rulings | Readable assessed | Intake gaps accounted | Unchecked |
|---|---:|---:|---:|---:|
| `source-000003-v6.json` | 15 | 15 | 0 | 0 |
| `source-000009-v1.json` | 13 | 10 | 3 | 0 |
| `source-000010-v1.json` | 18 | 16 | 2 | 0 |
| `source-000011-v1.json` | 35 | 29 | 6 | 0 |
| `source-000012-v1.json` | 21 | 19 | 2 | 0 |
| `source-000013-v1.json` | 22 | 19 | 3 | 0 |
| **Total** | **124** | **108** | **16** | **0** |

Every relationship identifier from every current final screenshot projection appears exactly once in the page tables above. The intake-gap table repeats the 16 gap identifiers as a convenience; it does not add new rulings.

## What remains unproven

- No live authenticated browser/API request was executed.
- No comparison was made between displayed production numbers and a V3 export for the same actual company/location/date range.
- Deployment identity was not verified; this report assesses the named local repository revisions.
- No separate middleware calculation layer was found in the repositories checked. If one exists elsewhere, it was not part of the available source set.
- No relevant automated tests were found that prove these page formulas or behaviors.

The next valid validation would use one frozen company/location/date-range case, capture the API response and matching V3 report rows, and compare every displayed field after the static formula defects above are corrected. Until then, this report is comprehensive for code-path alignment but must not be represented as proof of live numeric accuracy.
