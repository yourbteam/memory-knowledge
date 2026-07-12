# Sequence Discovery Logs

This folder stores discovery logs for repeatable operational sequences that do not yet have a registered sequence folder.

Create logs with:

```bash
python3 scripts/sequence_discovery_log.py start --sequence-name "<short name>" --outcome "<intended outcome>" --why-repeatable "<why this will likely recur>"
```

Activate the discovery sequence before running operational commands:

```bash
python3 scripts/work_memory.py classify --task-id "<task-id>" --operation-kind other --repeatable yes --meaningful-steps 3
python3 scripts/work_memory.py select --task-id "<task-id>" --discovery-log "<log-path>"
python3 scripts/sequence_guard.py activate --task-id "<task-id>" --discovery-log "<log-path>"
```

Append validated steps with:

```bash
python3 scripts/sequence_discovery_log.py append-step --file <log-path> --step "<step>" --command "<command or action>" --result "<result>" --note "<correction or note>"
```

Guard repeated commands before running them again:

```bash
python3 scripts/sequence_guard.py guard --task-id "<task-id>" --step "<step>" --command "<command or action>" --source discovery_log --source-ref "<log-path>"
```

Promote a discovery log only after the commands, inputs, failure handling, and verification evidence are stable enough to create `operations/sequences/<sequence-id>/sequence.md`.

Do not record secrets, token values, challenge codes, or private auth payloads in discovery logs.
