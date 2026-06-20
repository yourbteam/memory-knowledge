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
