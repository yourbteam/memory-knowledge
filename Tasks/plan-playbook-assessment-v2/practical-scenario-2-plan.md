# Scenario 2: Regime-Aware Gatherer Time Stops

## Objective

Make the Position Summary time-stop status in both morning and exit-review gatherers use the same trustworthy market-regime contract as the rest of the system. Risk-Off extends thresholds; a degraded regime feed cannot silently masquerade as Neutral.

## Allowed Surface

- `tools/shared_utils.py` — `MODIFY`
- `tools/morning_gatherer.py` — `MODIFY`
- `tools/exit_review_gatherer.py` — `MODIFY`
- `tests/test_gatherer_regime_time_stops.py` — `CREATE`
- `tools/harness/datastore.py` — `MODIFY` (approved independent-review correction)
- `tests/harness/test_harness_datastore.py` — `MODIFY` (approved correction coverage)

Exclude changes to `shared_regime.py`, time-stop thresholds, unrelated report sections, live-network tests, commits, and pushes.

## Grounded Preflight

- `shared_utils.compute_time_stop(days_held, is_pre_strategy, regime="Neutral")` is the authoritative threshold function. Neutral/Risk-On use approaching day 45 and exceeded after day 60; Risk-Off adds 14 days. Pre-strategy is always `EXCEEDED`; missing days are `Unknown`.
- `harness.datastore.regime_feed()` is the authoritative fail-closed adapter over `shared_regime.fetch_regime_detail()`. It returns `FeedResult(ok=False, hold_reason="regime_degraded")` when the provider's degraded fingerprint has `vix is None`; consumers must not trust its fake Neutral value.
- `morning_gatherer.main()` currently computes Position Summary rows inline and calls `compute_time_stop(days_held, is_pre)` without regime at the existing TODO.
- `exit_review_gatherer.build_position_summary_table()` has the same omission and TODO; `main()` calls this builder once.
- Neither gatherer currently imports or calls `regime_feed`; no gatherer-specific test file exists.
- Repository-native focused command: `.venv/bin/python -m pytest -q tests/test_gatherer_regime_time_stops.py tests/test_strategy_improvements.py`.
- Repository-native full command from `Makefile`: `make test PYTHON=.venv/bin/python`.
- Scope baseline: the four Scenario 2 paths are clean. From the repository root, `git diff --binary HEAD -- . ':(exclude)tools/shared_utils.py' ':(exclude)tools/morning_gatherer.py' ':(exclude)tools/exit_review_gatherer.py' ':(exclude)tests/test_gatherer_regime_time_stops.py' | shasum -a 256` produced unrelated tracked-content hash `868909481039be3fca25b95c4eb878b949acc6f48645f046e171a0a1ee3d45dd`. `git ls-files --others --exclude-standard -- . ':(exclude)tests/test_gatherer_regime_time_stops.py' | LC_ALL=C sort | while IFS= read -r file_path; do shasum -a 256 -- "$file_path"; done | shasum -a 256` produced unrelated non-ignored untracked-content hash `20e7bdad53c78dc4ab6bfd600ea8d597c07229b473bfc51b85255e4b95850992`. `git rev-parse HEAD` produced `c920926ef6cacf316717557f607f013988001fff`. These commands executed successfully in zsh.

## Locked Behavioral Contract

| Feed/state | Days/pre-state | Required status | Required observable |
| --- | --- | --- | --- |
| trusted `Risk-Off` | 58 days, not pre-strategy | `WITHIN` | both gatherer Position Summary rows contain `WITHIN` |
| trusted `Neutral` | 58 days, not pre-strategy | `APPROACHING` | both rows contain `APPROACHING` |
| trusted `Risk-On` | 61 days, not pre-strategy | `EXCEEDED` | both rows contain `EXCEEDED` |
| degraded feed | finite days, not pre-strategy | `UNKNOWN (regime unavailable)` | both rows expose uncertainty; each report records one regime-feed error |
| degraded feed | pre-strategy | `EXCEEDED` | invariant pre-strategy result remains actionable |
| degraded feed | unknown/invalid entry date | `Unknown` | invariant unknown-date result remains unchanged |

Each gatherer fetches exactly one regime result when at least one active ticker requires a Position Summary time stop, then reuses it for every active ticker. An exit-review run with no active positions follows its existing early return and performs zero regime fetches. A morning run with no active positions also performs zero regime fetches. No per-ticker regime fetch is allowed.

## Implementation

1. In `shared_utils.py`, add `compute_regime_guarded_time_stop(days_held, is_pre_strategy, regime_result)`. Keep invariant outcomes independent of feed health: pre-strategy delegates to `compute_time_stop` and returns `EXCEEDED`; `days_held is None` delegates and returns `Unknown`. For ordinary finite holding periods, require `regime_result.ok is True` and `regime_result.data["regime"]` in `Risk-On|Neutral|Risk-Off`. Otherwise return exact `UNKNOWN (regime unavailable)`. Trusted input delegates to `compute_time_stop(..., regime=regime)`.

2. In `morning_gatherer.py`, import `regime_feed` and the guarded helper. Extract the existing Position Summary loop without changing its columns or formatting into `build_position_summary_rows(active_tickers, positions, prices, capital, regime_result, as_of_date=None)`. Use `compute_days_held(entry_date, as_of_date)` and the guarded helper. In `main()`, capture `run_date = last_trading_day()` exactly once, derive the existing `today_str` from that value, and pass the same `run_date` to the builder so holding periods use the report's existing trading-date semantics. After `all_errors` is created, fetch `regime_result = regime_feed()` exactly once only when `active_tickers` is nonempty; otherwise use `None` without calling the feed. Append exact `*Error: Market regime unavailable; time stops marked UNKNOWN.*` once when a fetched result has `ok` false, and pass the same result into the extracted builder.

3. In `exit_review_gatherer.py`, import `regime_feed` and the guarded helper. Extend `build_position_summary_table(active_tickers, portfolio, prices, regime_result, as_of_date=None)` and use the guarded helper without changing columns or formatting. In `main()`, capture `run_date = date.today()` exactly once, derive the existing `today_str` from it, and pass the same `run_date` to the builder so holding periods use the report's existing calendar-date semantics. Preserve the no-active early return with zero feed calls. When active tickers exist, fetch exactly once after `all_errors` is created, append the same exact error once on degraded input, and pass the result to the builder.

4. Create `tests/test_gatherer_regime_time_stops.py` with offline `FeedResult` instances and fixed `as_of_date=date(2026, 3, 25)`. Directly test the shared helper's complete matrix: Neutral/Risk-On day 44 `WITHIN`, day 45 and day 60 `APPROACHING`, day 61 `EXCEEDED`; Risk-Off day 58 `WITHIN`, day 59 and day 74 `APPROACHING`, day 75 `EXCEEDED`; degraded finite-day input exact `UNKNOWN (regime unavailable)`; degraded pre-strategy `EXCEEDED`; and degraded missing days `Unknown`. Call both table builders with equivalent one-position data and independently assert the Time Stop column for trusted Risk-Off `WITHIN`, trusted Neutral `APPROACHING`, trusted Risk-On `EXCEEDED`, and degraded exact unknown results. Verify pre-strategy and invalid-date invariants through both builders as well.

   For the real morning `main()` test, monkeypatch `load_portfolio` to two active positions, `AAA` and `BBB`, each with shares, average cost, `entry_date="2026-01-26"`, bullets, note, and target plus empty orders/watchlist; `regime_feed` to a counting degraded fake; `run_tool` to return empty successful output for market/capital tools; `run_ticker_tools` to return empty successful tuples for all requested ticker tools; `get_current_prices` to `{"AAA": 10.0, "BBB": 20.0}`; `get_watchlist_prices` to `{}`; `last_trading_day`, `is_trading_day`, and `as_of_date_label` to fixed values; `sizing_description` to a fixed method dict; and module `OUTPUT` to `tmp_path / "morning-tools-raw.md"`. Invoke `main()`, then prove exactly one feed call, distinct `AAA` and `BBB` Position Summary rows both containing exact `UNKNOWN (regime unavailable)`, and the exact regime error once in the Cross-Check Summary. Add a second morning `main()` test with empty positions/orders/watchlist and a regime fake that raises if called; keep the same remaining offline seams and prove the run completes with zero feed calls.

   For the real exit-review `main()` test, monkeypatch `load_portfolio` to the equivalent two-position `AAA`/`BBB` portfolio; `regime_feed` to a counting degraded fake; `run_portfolio_status` to empty successful output; `get_current_prices` to `{"AAA": 10.0, "BBB": 20.0}`; `run_all_tickers` to return `AAA` and `BBB` result maps with empty successful tuples and no errors; `read_identity_context` and `read_news_context` to fixed text; and module `OUTPUT_PATH` to `tmp_path / "exit-review-raw.md"`. Invoke `main()`, then prove exactly one feed call, distinct `AAA` and `BBB` rows both containing exact unknown status, and the exact regime error once in Tool Errors. Add one no-active exit-review `main()` test whose feed fake would fail if called, proving the preserved zero-fetch early return. No network function may execute.

## Verification

1. Run `.venv/bin/python -m pytest -q tests/test_gatherer_regime_time_stops.py tests/test_strategy_improvements.py`.
2. Run `make test PYTHON=.venv/bin/python`.
3. Run `git diff --check`.
4. Re-run the exact two scope-baseline commands and require hashes `868909481039be3fca25b95c4eb878b949acc6f48645f046e171a0a1ee3d45dd` and `20e7bdad53c78dc4ab6bfd600ea8d597c07229b473bfc51b85255e4b95850992`. Run `git status --short -- tools/shared_utils.py tools/morning_gatherer.py tools/exit_review_gatherer.py tests/test_gatherer_regime_time_stops.py` and require exactly the three `MODIFY` plus one `CREATE` operations. Require `git rev-parse HEAD` to remain `c920926ef6cacf316717557f607f013988001fff`.
5. Independently review feed producer -> guarded helper -> both gatherer mains -> table rows -> error reporting -> focused/full tests. Confirm no default-Neutral use remains at either TODO and no per-ticker feed calls were introduced.

## Approved Independent-Review Correction

The first implementation review found that `regime_feed()` still returned `ok=True` when VIX was present but the regime label was missing or outside `Risk-On|Neutral|Risk-Off`. That allowed both gatherers to display an unexplained unknown state instead of recording the feed degradation. The stable fix is at the authoritative adapter: `tools/harness/datastore.py` now rejects unsupported regime labels with `hold_reason="regime_degraded"`, and `tests/harness/test_harness_datastore.py` covers all three accepted labels plus missing, empty, case-drifted, unknown, and non-canonical labels. This approved correction supersedes the earlier datastore exclusion and expands focused verification to include `tests/harness/test_harness_datastore.py`.

## Practical Cost

Four files, one small shared decision helper, one extraction of existing morning-table code, one exit-builder signature extension, and offline tests. Production adds one shared regime fetch per gatherer run; no per-ticker or test network traffic.
