# Scenario 1 Revised Implementation Plan

## Objective

Make `news_sweep_collector.py` fail visibly whenever `news_sentiment.py` returns an error or non-error news output without real rows in both required sections. Preserve legitimate no-news behavior and optional catalysts.

## Allowed Surface

- `tools/news_sweep_collector.py`
- `tests/test_news_sweep_collector.py` (new)

No other files, report-format changes, network tests, commits, or pushes.

## Grounded Preflight

- `tools/news_sweep_collector.py`: exists, `MODIFY`; contains the three parsers, `is_no_news`, `build_ticker_section`, `build_output`, the per-future classifier, and the final console summary.
- `tests/test_news_sweep_collector.py`: absent at baseline, `CREATE`; no collector-specific fixtures exist.
- `tools/news_sentiment.py`: exists, evidence only; confirms valid output always emits Headlines and Sentiment Summary while Detected Catalysts is conditional.
- Verification commands: from repository root, run focused verification with `.venv/bin/python -m pytest -q tests/test_news_sweep_collector.py`, then the repository-native full regression suite from `Makefile` with `make test PYTHON=.venv/bin/python`; `.venv/bin/python` exists and reported pytest 9.1.1 during preflight.
- Scope baseline: the two approved paths are clean. From the repository root, `git diff --binary HEAD -- . ':(exclude)tools/news_sweep_collector.py' ':(exclude)tests/test_news_sweep_collector.py' | shasum -a 256` produced unrelated tracked-content hash `c920fd8f533e79c9cd333a2b6f7fa44225a97003238599c57ba6509ed6969a76`. `git ls-files --others --exclude-standard -- . ':(exclude)tests/test_news_sweep_collector.py' | LC_ALL=C sort | while IFS= read -r file_path; do shasum -a 256 -- "$file_path"; done | shasum -a 256` produced unrelated untracked-content manifest hash `0fd10ba43ea8a0d299ce3dd14465545ed484feabfba49d5ff8eecb50866de993`. `git rev-parse HEAD` produced `c920926ef6cacf316717557f607f013988001fff`. These commands were executed successfully in zsh; `file_path` is required because zsh reserves `path` for command lookup.

## Implementation

1. In `tools/news_sweep_collector.py`, add a small Markdown-table separator predicate used by the three existing section parsers. A row is a separator when every parsed cell consists only of optional surrounding colons and one or more hyphens. Skip both colon-style (`:---`) and plain (`---`) separator rows. Keep existing table headers excluded. This makes parser truthiness mean at least one real data row; do not add section-name aliases or fallback parsing.

   Lock the minimum real-row predicates at the parser boundary:
   - Sentiment Summary: all seven producer metrics (`Articles Analyzed`, `Positive`, `Neutral`, `Negative`, `Average Score`, `Overall Sentiment`, `Total Unique Headlines`) must appear exactly once with nonempty values. A missing, duplicated, aliased, unknown, or empty metric makes the summary malformed.
   - Headlines: date, source, headline, sentiment, and score are nonempty, and score parses as a finite float. Preserve the existing returned five-string tuple.
   - Detected Catalysts remains optional; when present, its category and count are nonempty and count parses as a non-negative integer before the row is returned.
   Rows failing these minimum predicates are ignored, so a section containing only malformed rows is absent for classification purposes. Do not validate business truth, sentiment vocabulary, date freshness, or headline content beyond these bounded structural semantics.

2. Add a result-classification helper at the collector boundary that returns the exact two-tuple `(status, diagnostic)`. `status` is one of `error`, `no_news`, `malformed`, or `valid`; `diagnostic` is the original error string for `error`, one of the three exact malformed messages below for `malformed`, and `None` otherwise:
   - Any non-`None` tool error is `error`, regardless of whether stdout is empty, contains the no-news marker, or contains apparently valid sections. Preserve the original error text in `failures`.
   - With no error, the existing `is_no_news(stdout)` marker is `no_news` and is not a failure.
   - Otherwise call `parse_top_headlines(stdout, n=3)` and `parse_sentiment_summary(stdout)`. A headline section needs at least one real row; a summary needs the complete exact seven-metric producer set. If either contract fails, return `malformed` with exactly `Malformed news output: missing Headlines rows.`, `Malformed news output: missing Sentiment Summary rows.`, or `Malformed news output: missing Headlines and Sentiment Summary rows.` according to the failed section contracts.
   - Only no-error output with at least one real headline row and the complete exact seven-metric summary is `valid`.
   - Never require `parse_detected_catalysts`; catalysts remain optional.

3. Replace the per-future branch in `main()` with that helper's classification:
   - `error`: append `(ticker, original_error)` and print `FAILED`.
   - `no_news`: print `no news` and do not append a failure.
   - `malformed`: append `(ticker, bounded malformed diagnostic)` and print `FAILED`.
   - `valid`: print `OK`.
   Continue passing the same `failures` collection to `build_output`, so its existing summary count and failure list expose the new failures without changing report structure.

4. Preserve the same error precedence in both report consumers:
   - In `build_ticker_section`, any non-`None` error renders the existing exact `*Tool error — see Failures section.*` result before inspecting stdout, including partial stdout and the no-news marker.
   - In `build_output`, count `No News Data` only when the tuple has no error and stdout contains the no-news marker. Errored no-news-marker output remains a failure and contributes zero to the no-news count.
   - In `main()`'s final console summary, apply the same no-error predicate before incrementing `No news data`; the report and console must show the same count.

5. Create `tests/test_news_sweep_collector.py`. Drive the real `main()` path with a local helper that monkeypatches `load_portfolio` to return `{"positions": {"AAA": {"shares": 1}}, "pending_orders": {}, "watchlist": []}`, monkeypatches `OUTPUT` to `tmp_path / "news-sweep-raw.md"`, and replaces `run_tool` with a dispatcher: `portfolio_status.py` returns `("", None)`, while `news_sentiment.py` asserts `args == ["AAA"]` and returns the case-specific `(stdout, error)` tuple. Capture stdout with `capsys`, invoke `main()`, and read the temporary output for report assertions; do not claim pre-existing collector fixtures. Cover:
   - valid summary and headline rows without catalysts -> `OK`, zero failures;
   - legitimate no-news -> `no news`, zero failures, report `No News Data | 1`, console `No news data: 1`, and the ticker section's existing `*No news data available.*` text;
   - error with empty stdout -> `FAILED`, original error in report;
   - error with otherwise valid partial stdout -> `FAILED`, never `OK` or `no news`, and the ticker section renders exact `*Tool error — see Failures section.*` text;
   - error with stdout containing the legitimate no-news marker -> `FAILED`, original error in report, never `no news`, report `No News Data` remains zero, console `No news data: 0`, and the ticker section renders the existing tool-error message;
   - headlines present but summary missing/unparseable -> exact `Malformed news output: missing Sentiment Summary rows.` failure;
   - summary present but headlines missing/unparseable -> exact `Malformed news output: missing Headlines rows.` failure;
   - both required sections missing/unparseable -> exact `Malformed news output: missing Headlines and Sentiment Summary rows.` failure;
   - parameterized direct parser assertions prove `---`, `:---`, `---:`, and `:---:` separator rows produce no data from `parse_sentiment_summary`, `parse_top_headlines`, and `parse_detected_catalysts` independently;
   - direct parser assertions reject unknown summary metrics, empty required headline fields, non-numeric or non-finite headline scores, and negative/non-integer catalyst counts;
   - pair a valid headline section with a separator-only summary, and a valid summary with a separator-only headline section, proving either malformed required section prevents `OK`;
   - malformed failures appear in the existing Failures count and list.

   Every tool-error and malformed-output case driven through `main()` also asserts the final console summary contains exact `Failures: 1`; valid and legitimate no-news cases assert `Failures: 0`. This proves the report failure total, per-ticker status, and final console aggregate remain consistent.

## Verification

1. Run `.venv/bin/python -m pytest -q tests/test_news_sweep_collector.py` from `/Users/kamenkamenov/agentic-trading`.
2. Run `make test PYTHON=.venv/bin/python` from `/Users/kamenkamenov/agentic-trading` as the repository-native full regression suite.
3. Run `git diff --check`.
4. Independently review every concrete classifier branch: empty-stdout error, valid-partial-stdout error, no-news-marker error, legitimate no-news, missing summary rows, missing headline rows, separator-only rows, fully valid output, optional catalysts, and propagation through the existing failure count/list.
5. Re-run the exact two content-hash commands from the scope baseline and require exact hashes `c920fd8f533e79c9cd333a2b6f7fa44225a97003238599c57ba6509ed6969a76` and `0fd10ba43ea8a0d299ce3dd14465545ed484feabfba49d5ff8eecb50866de993`. This proves no tracked or untracked content outside the two approved paths changed, including paths already dirty at baseline. Run `git status --short -- tools/news_sweep_collector.py tests/test_news_sweep_collector.py` and require exactly those two Scenario 1 entries with operations matching `MODIFY` and `CREATE`. Re-run `git rev-parse HEAD` and require `c920926ef6cacf316717557f607f013988001fff`, proving this implementation created no commit. Do not run any push command.

## Expected Cost

Two files, one bounded classifier, one separator predicate, and approximately seven focused tests. No live data or network execution.
