# Sequence Discovery Logs

This folder stores discovery logs for repeatable operational sequences that do not yet have a registered sequence folder.

Create logs with:

```bash
uv run python scripts/sequence_discovery_log.py start --sequence-name "<short name>" --outcome "<intended outcome>" --why-repeatable "<why this will likely recur>"
```

Activate the discovery sequence before running operational commands:

```bash
uv run python scripts/sequence_guard.py activate --sequence-id "<short name>" --discovery-log "<log-path>"
```

Append validated steps with:

```bash
uv run python scripts/sequence_discovery_log.py append-step --file <log-path> --step "<step>" --command "<command or action>" --result "<result>" --note "<correction or note>"
```

Guard repeated commands before running them again:

```bash
uv run python scripts/sequence_guard.py guard --step "<step>" --command "<command or action>" --source discovery_log --source-ref "<log-path>"
```

Promote a discovery log only after the commands, inputs, failure handling, and verification evidence are stable enough to create `operations/sequences/<sequence-id>/sequence.md`.

Do not record secrets, token values, challenge codes, or private auth payloads in discovery logs.
