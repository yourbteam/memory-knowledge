# Minimal commit and push

<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->
## Operator entry point

For a new commit/push task, launch the dedicated controller with no arguments:

```bash
python3 scripts/commit_push_main_launch.py
```

It owns classification, exact `commit-push-main` selection, activation, run start, and handoff to
the numbered semantic interview. For a commit/push task that is already selected and activated,
continue through the shared zero-argument handoff:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
<!-- END SEMANTIC INTAKE ENTRYPOINT -->

Stable sequence id: `commit-push-main`.

## Operator entry point

Run the dedicated controller with no arguments:

```bash
python3 scripts/commit_push_main_launch.py
```

Launch a requested commit-and-push operation with host permission to write the repository's Git
common directory and reach its configured remote. Dry runs do not need that permission. The host
grant never replaces the controller's exact prepared-operation display and numbered authorization.

The controller displays numbered choices for the operation, repository, and changed paths. It
collects one focused verification command, mechanically routes every pytest form through the
selected repository's executable `scripts/run_pytest.sh` wrapper, shows the normalized prepared
operation, and requires a separate numbered authorization before any commit or push. An unmanaged
host Python can therefore never become the pytest runtime.

## Outcome

Publish exactly the selected paths while leaving every unrelated working-tree change untouched.
The sequence succeeds only after a fresh remote checkout reports the exact local commit.

## Boundaries

1. **Exact manifest** — selected repository-relative files form the complete staging scope;
   duplicate, missing, unchanged, absolute, and escaping entries are rejected. Tracked deletions
   are valid.
2. **Relevant verification** — the exact operator-supplied argument array runs from the selected
   worktree after the manifest has passed mechanical staging checks. Every non-zero exit blocks
   before commit.
3. **Exact commit** — the staged paths and resulting commit must equal the manifest. Unrelated
   tracked and untracked work remains local.
4. **Push** — Git pushes that one commit to the selected remote and branch. A non-zero push is a
   failure. GitHub CLI authentication is not a prerequisite and `gh auth status` must not gate this sequence.
   Only the actual `git push` result from the deterministic publish or resume operation is authoritative for
   Git remote authentication.
5. **Remote confirmation** — a fresh, shallow, no-checkout clone must report the same commit SHA.

## Failure handling

- Dry run uses a temporary Git index and object database, runs the same staging and verification
  boundaries without leaking that temporary Git environment into the verification command, and
  leaves the real object database, index, HEAD, and remote unchanged.
- Before commit, a failure unstages only the manifest and preserves all working-tree content.
- After commit, a push or confirmation failure preserves the single local commit at HEAD and
  reports that fact. It never creates another commit automatically and never force-pushes.
- The sequence does not classify, select, activate, ingest, write a lifecycle ledger, regenerate
  proof artifacts, or make Git success depend on any of those systems.
- A real publish must be launched with Git-common-directory write and remote-network permission;
  an `index.lock` denial from a read-only host is an invocation-contract failure, not a reason to
  reconstruct the Git steps manually.

## Verification

```bash
scripts/run_pytest.sh -q \
  tests/test_publish_boundary_probes.py \
  tests/test_minimal_git_publish.py \
  tests/test_minimal_commit_push_main_launch.py
```

The standalone probes prove every boundary both ways. The production tests exercise dry-run
isolation, exact commits, non-zero verification, tracked deletion, failed-push containment, remote
confirmation refusal, numbered authorization, and a complete no-argument interview that publishes
to a disposable bare remote.

Pass signal: the final JSON says `ok: true`, `commit` equals `remote_commit`, the committed path set
equals the selected manifest, and unrelated changes remain unstaged.
