# Weekly Review Setup (Gap #7)

A weekly routine that keeps the memory trustworthy on a schedule: refresh the directive Spark
(#3), run integrity-audit + compaction per active repo, and bump the `DIRECTIVES.md`
"Last reviewed" stamp (committed so the corpus sync mirrors it).

## Enable (macOS launchd)
```bash
cp working-agreement/com.kamen.memory-weekly-review.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kamen.memory-weekly-review.plist
```
Runs Mondays 09:00; logs to `/tmp/mk-weekly-review.log`. Adjust `StartCalendarInterval` as desired.
Linux: schedule `working-agreement/weekly-review.sh` via cron instead.

## Run on demand
```bash
working-agreement/weekly-review.sh
```
Fail-soft: any step failing is logged and skipped; the routine never blocks. Review
`working-agreement/spark-candidates.md` after a run and promote any worthy candidate via "lock it".

## A5: repo set + spark candidates
`weekly-review.sh` exports `MK_SPARK_REPOS` (the 8-repo set: taggable-api, fcsapi, taggable-server,
taggable-database, united-partners, agentic-trading, mcp-agents-workflow, memory-knowledge) so Spark +
consolidation scan all of them; override by exporting `MK_SPARK_REPOS` before the run. The weekly run now
prints a `spark-candidates: <N> -> <path>` line (or `none this run`) so you know to review candidates.
