"""Execute an admitted disposable experiment; no product promotion or goal completion.

Reuses candidate generation and lineage verification. OS confinement owns runtime
isolation; a separate model assesses raw captured evidence against the saved cases.
"""
import json
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

from build_preparation import read, ref, save, sha, verify
from candidate_execution import once, verify_generation, emit, files

RUNTIME_DIRECTORIES = ['experiment/results']
RUNTIME_FILES = ['experiment/report.md']
SOURCE_INTEGRITY_RUNTIME_PATH = 'experiment/controller-source-integrity-receipt.json'
MAX_REVIEW_ARTIFACT_BYTES = 500000
MAX_REVIEW_REPORT_BYTES = 100000
MAX_REVIEW_JSON_FIELD_BYTES = 16000


def json_field_metadata(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    result = {
        'transport': 'verified_json_field_metadata',
        'sha256': hashlib.sha256(raw).hexdigest(),
        'serialized_bytes': len(raw),
        'raw_evidence_preserved': True,
        'content_included': False,
    }
    if isinstance(value, (dict, list)):
        result['item_count'] = len(value)
    return result


def bounded_json_projection(path):
    try:
        value = json.loads(path.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if path.name.endswith('.process.json') and isinstance(value, dict):
        return {
            key: json_field_metadata(item) if key in ('stdout', 'stderr') else item
            for key, item in value.items()
        }, 'process_projection'
    if path.name.endswith('.trace.json') and isinstance(value, dict):
        result = {}
        for key, item in value.items():
            raw = json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode()
            result[key] = item if len(raw) <= MAX_REVIEW_JSON_FIELD_BYTES else json_field_metadata(item)
        return result, 'bounded_json_projection'
    return None, None


def source_manifest(source_units):
    result = []
    for unit in source_units:
        text = unit['text']
        raw = text.encode()
        result.append({'path': unit['path'], 'sha256': hashlib.sha256(raw).hexdigest(),
                       'size_bytes': len(raw), 'content_included': False})
    return result


def protected_source_comparison(candidate, before):
    """Export the exact before/after identities used to protect generated source."""
    candidate = Path(candidate).resolve()

    def relative(reference):
        path = Path(reference['path']).resolve()
        try:
            return str(path.relative_to(candidate))
        except ValueError as exc:
            raise ValueError('Protected source escaped the candidate root: ' + str(path)) from exc

    def runtime_output(path):
        return path in RUNTIME_FILES or any(
            path == directory or path.startswith(directory + '/')
            for directory in RUNTIME_DIRECTORIES)

    before_by_path = {
        relative(reference): reference['sha256']
        for reference in before
        if not runtime_output(relative(reference))
    }
    after_by_path = {
        relative(reference): reference['sha256']
        for reference in files(candidate)
        if not runtime_output(relative(reference))
    }
    rows = []
    changes = []
    for path in sorted(set(before_by_path) | set(after_by_path)):
        before_sha = before_by_path.get(path)
        after_sha = after_by_path.get(path)
        if before_sha is None:
            status = 'added'
        elif after_sha is None:
            status = 'missing'
        elif before_sha != after_sha:
            status = 'changed'
        else:
            status = 'unchanged'
        rows.append({
            'path': path,
            'before_sha256': before_sha,
            'after_sha256': after_sha,
            'status': status,
        })
        if status != 'unchanged':
            changes.append(path)

    def identity(mapping):
        raw = json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()
        return hashlib.sha256(raw).hexdigest()

    return {
        'schema_version': 1,
        'kind': 'protected_source_comparison',
        'status': 'verified_unchanged' if not changes else 'changed',
        'protected_source_count': len(rows),
        'before_manifest_sha256': identity(before_by_path),
        'after_manifest_sha256': identity(after_by_path),
        'changes': changes,
        'files': rows,
    }


def review_evidence(reference):
    """Return reviewable text without discarding oversized raw evidence."""
    path = verify(reference)
    if path.suffix not in ('.php', '.py', '.json', '.md', '.txt'):
        return None
    size = path.stat().st_size
    projected, transport = bounded_json_projection(path) if path.suffix == '.json' else (None, None)
    paired_trace = path.name.endswith('.stdout.txt') and path.with_name(
        path.name.replace('.stdout.txt', '.trace.json')).exists()
    oversized_generated_report = path.name == 'report.md' and size > MAX_REVIEW_REPORT_BYTES
    if projected is not None:
        text = json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    elif size <= MAX_REVIEW_ARTIFACT_BYTES and not paired_trace and not oversized_generated_report:
        text = path.read_text()
        transport = 'full_text'
    else:
        metadata = {
            'transport': 'verified_metadata_only',
            'path': reference['path'],
            'sha256': reference['sha256'],
            'size_bytes': size,
            'raw_evidence_preserved': True,
            'content_included': False,
        }
        if oversized_generated_report:
            metadata['omission_reason'] = (
                'Generated report exceeds the bounded review transport; '
                'primary code and trace evidence is supplied separately.')
        text = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        transport = 'verified_metadata_only'
    return {'path': reference['path'], 'sha256': reference['sha256'],
            'size_bytes': size, 'transport': transport, 'text': text}


def review_evidence_set(references):
    """Represent byte-identical artifacts once while retaining every identity."""
    result = []
    first_by_hash = {}
    for reference in references:
        path = verify(reference)
        digest = reference['sha256']
        if digest in first_by_hash:
            item = {
                'path': reference['path'], 'sha256': digest,
                'size_bytes': path.stat().st_size, 'transport': 'verified_duplicate',
                'text': json.dumps({
                    'transport': 'verified_duplicate',
                    'duplicate_of': first_by_hash[digest],
                    'sha256': digest,
                    'size_bytes': path.stat().st_size,
                    'raw_evidence_preserved': True,
                    'content_included': False,
                }, ensure_ascii=False, sort_keys=True),
            }
        else:
            item = review_evidence(reference)
            if item is not None:
                first_by_hash[digest] = reference['path']
        if item is not None:
            result.append(item)
    return result


def review_execution_projection(result):
    """Keep execution facts in-model without copying the full raw-file manifest."""
    output_files = result['output_files']
    manifest = json.dumps(
        output_files, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    projected = {key: value for key, value in result.items() if key != 'output_files'}
    projected['output_file_manifest'] = {
        'count': len(output_files),
        'sha256': hashlib.sha256(manifest).hexdigest(),
        'raw_manifest_preserved': True,
        'content_included': False,
    }
    return projected


def review_output_references(experiment_root, references):
    """Send executable code and decision traces; retain bulk snapshots outside the prompt."""
    experiment_root = Path(experiment_root).resolve()
    selected = []
    by_name = {}
    trace_paths = []
    for reference in references:
        path = Path(verify(reference)).resolve()
        try:
            relative = path.relative_to(experiment_root)
        except ValueError as exc:
            raise ValueError('Experiment output escaped its evidence root: ' + str(path)) from exc
        detail_trace = False
        if path.name.endswith('.trace.json'):
            try:
                trace = json.loads(path.read_text())
                detail_trace = (
                    isinstance(trace, dict)
                    and isinstance(trace.get('process_record'), str)
                    and isinstance(trace.get('checks'), list)
                    and len(trace['checks']) == 1
                )
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        include = relative.parts[0] != 'results' or (
            path.name in {'results.json', 'traces.jsonl', 'source-manifest.json'} or
            path.name.endswith('.process.json') or
            (path.name.endswith('.trace.json') and not detail_trace))
        by_name.setdefault(path.name, []).append(reference)
        if include:
            selected.append(reference)
        if path.name.endswith('.trace.json') and not detail_trace:
            trace_paths.append(path)

    # A failed compact check may point at one small detailed artifact. Include only
    # those explicitly named details, rather than every successful stage snapshot.
    requested = set()
    def collect(value):
        if isinstance(value, dict):
            if value.get('observed_expected') is False and isinstance(value.get('evidence_file'), str):
                requested.add(value['evidence_file'])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    for path in trace_paths:
        try:
            collect(json.loads(path.read_text()))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    for name in sorted(requested):
        matches = by_name.get(Path(name).name, [])
        if len(matches) != 1:
            raise ValueError('Failed-check evidence is missing or ambiguous: ' + name)
        if matches[0] not in selected:
            selected.append(matches[0])
    return selected


def citation_representation(citation, root):
    """Resolve a quote against the exact review representation and its raw source."""
    source = root_ref(citation['evidence_path'], root)
    source_path = Path(root) / source['path']
    raw_text = source_path.read_text()
    quote = citation.get('quote', '')
    if quote.strip() and quote in raw_text:
        return source, raw_text, 'raw_source'
    projected = review_evidence({'path': str(source_path), 'sha256': source['sha256']})
    if projected is not None and quote.strip() and quote in projected['text']:
        return source, projected['text'], projected['transport']
    raise ValueError('Citation does not resolve in its raw or transported representation')


def materialize_citation_representation(output, source, text, transport):
    """Persist non-raw review text so downstream checks read what the reviewer read."""
    if transport == 'raw_source':
        return source
    identity = json.dumps({
        'source': source, 'transport': transport,
        'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
    }, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    path = Path(output) / 'review-evidence' / (hashlib.sha256(identity).hexdigest() + '.txt')
    raw = text.encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Materialized review evidence changed: ' + str(path))
    else:
        path.write_bytes(raw)
    return ref(path)


def save_versioned_json(path, data):
    """Keep a failed immutable export and write corrected content beside it."""
    path = Path(path)
    raw = (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode()
    if path.exists() and path.read_bytes() != raw:
        path = path.with_name(path.stem + '-' + hashlib.sha256(raw).hexdigest()[:16] + path.suffix)
    save(path, data)
    return path


def review_schema(ids, evidence_paths, obj, array, text):
    """Require every citation to identify one file and one contiguous quote."""
    citation = obj({
        'evidence_path': {'type': 'string', 'enum': evidence_paths},
        'quote': text,
    })
    return obj({'cases': array(obj({
                    'id': {'type': 'string', 'enum': ids},
                    'verdict': {'type': 'string', 'enum': ['supported', 'unsupported', 'cannot_assess']},
                    'reason': text,
                    'citations': array(citation),
                })),
                'conclusion': text,
                'implementation_consequence': text})


def citation_repair_schema(ids, evidence_paths, obj, array, text):
    citation = obj({
        'evidence_path': {'type': 'string', 'enum': evidence_paths},
        'quote': text,
    })
    return obj({'cases': array(obj({
        'id': {'type': 'string', 'enum': ids},
        'citations': array(citation),
    }))})


def validate_review_citations(answer, ids, texts):
    if [case['id'] for case in answer['cases']] != ids:
        raise ValueError('Review omitted or reordered assigned cases')
    for case in answer['cases']:
        citations = case.get('citations')
        if not citations:
            raise ValueError('Review has no citation: ' + case['id'])
        for citation in citations:
            path = citation['evidence_path']
            quote = citation['quote']
            if not quote.strip() or quote not in texts.get(path, ''):
                raise ValueError('Review citation does not resolve: ' + case['id'])


def saved_legacy_review(folder, ids):
    """Identify the one superseded single-citation contract without translating it."""
    folder = Path(folder)
    step_path = folder / 'step.json'
    if not step_path.exists():
        return None
    step = read(step_path)
    if step.get('status') != 'completed':
        return None
    answer = read(folder / step['answer_file'])
    cases = answer.get('cases')
    if not isinstance(cases, list) or [case.get('id') for case in cases] != ids:
        return None
    if not all(set(case) == {'id', 'verdict', 'reason', 'evidence_path', 'quote'} for case in cases):
        return None
    return answer, step['session']


def repair_legacy_review(output, legacy, session, ids, texts, checkpoint, review, obj, array, text):
    """Ask the original reviewer only to restate citations under the corrected contract."""
    evidence_paths = list(texts)
    schema = citation_repair_schema(ids, evidence_paths, obj, array, text)
    prompt = (
        'Restate only the citations for your completed experiment review. Preserve the prior '
        'verdicts, reasons, conclusion and implementation consequence; do not reassess them. '
        'Return every case once in the supplied order. Each citation must name exactly one '
        'allowed evidence_path and quote one non-empty, exact, contiguous fragment from that '
        'file. Use multiple citation objects when a judgment needs multiple files or fragments. '
        'Never join paths or quotes with semicolons. No tools.\n' +
        json.dumps({'case_ids': ids, 'prior_review': legacy,
                    'allowed_evidence_paths': evidence_paths},
                   ensure_ascii=False, separators=(',', ':'))
    )
    repaired, _ = checkpoint.call(
        Path(output) / 'review-citation-repair',
        'experiment-review-citation-repair',
        prompt,
        schema,
        lambda path: review.CodexTransport(path, {
            'provider': 'codex', 'model': 'gpt-6-astra', 'reasoning': 'medium'}),
        session=session,
    )
    if [case['id'] for case in repaired['cases']] != ids:
        raise ValueError('Citation repair omitted or reordered assigned cases')
    citations = {case['id']: case['citations'] for case in repaired['cases']}
    answer = {
        'cases': [{
            'id': case['id'],
            'verdict': case['verdict'],
            'reason': case['reason'],
            'citations': citations[case['id']],
        } for case in legacy['cases']],
        'conclusion': legacy['conclusion'],
        'implementation_consequence': legacy['implementation_consequence'],
    }
    validate_review_citations(answer, ids, texts)
    return answer


def write_contract(allowed_paths):
    """Keep generated source paths distinct from execution-time evidence writes."""
    if not isinstance(allowed_paths, list) or not all(
            isinstance(path, str) and path for path in allowed_paths):
        raise ValueError('Builder request omitted its code-edit paths')
    return {
        'code_edit_paths': list(allowed_paths),
        'runtime_write_directories': list(RUNTIME_DIRECTORIES),
        'runtime_write_files': list(RUNTIME_FILES),
        'temporary_storage': 'launcher-supplied TMPDIR outside the candidate source tree',
    }


def builder_execution_contract(runtime_contract, allowed_paths):
    """Combine adapter-owned launch facts with the actual downstream evidence contract."""
    timeout = (runtime_contract.get('entrypoint') or {}).get('timeout_seconds') \
        if isinstance(runtime_contract, dict) else None
    if (not isinstance(runtime_contract, dict)
            or runtime_contract.get('schema_version') != 1
            or type(timeout) is not int or timeout <= 0):
        raise ValueError('Runtime adapter omitted the bounded execution contract')
    return {
        'schema_version': 2,
        'authority': {
            'assignment': 'Controls the business outcome, cases and observation boundaries.',
            'this_contract': (
                'Controls execution mechanics. When assignment prose conflicts about invocation, '
                'paths, writes, source verification, dependency availability, time or evidence '
                'format, follow this contract and do not block on the stale mechanical statement.'),
        },
        'runtime': runtime_contract,
        'write_contract': write_contract(allowed_paths),
        'source_integrity': model_source_integrity_contract(),
        'evidence': {
            'output_root': RUNTIME_DIRECTORIES[0],
            'report_path': RUNTIME_FILES[0],
            'case_trace': {
                'filename_suffix': '.trace.json',
                'required_top_level_fields': ['status', 'checks'],
                'required_status': 'checked',
                'required_check_fields': ['name', 'observed_expected'],
                'purpose': 'Preserve each case observation for independent review and compact assessment.',
            },
            'process_record': {
                'filename_suffix': '.process.json',
                'required_fields': ['exit_status', 'stderr'],
                'purpose': 'Preserve each child execution outcome independently from its interpretation.',
            },
            'review_transport_limits_bytes': {
                'report': MAX_REVIEW_REPORT_BYTES,
                'artifact': MAX_REVIEW_ARTIFACT_BYTES,
                'json_field': MAX_REVIEW_JSON_FIELD_BYTES,
            },
            'limit_effect': (
                'Content over a listed limit remains hash-preserved but becomes metadata-only for '
                'the reviewer. Keep decisive case checks within the structured trace limits.'),
        },
    }


def execution_contract_from_request(request):
    """Return the code-owned contract, upgrading saved v1 requests deterministically."""
    context = json.loads(request['context'])
    contract = context.get('builder_execution_contract')
    if not isinstance(contract, dict) or contract.get('schema_version') not in (1, 2):
        raise ValueError('Builder request has no supported execution contract')
    result = json.loads(json.dumps(contract))
    source_version = result['schema_version']
    expected_writes = write_contract(request.get('allowed_paths'))
    if source_version == 1:
        result['schema_version'] = 2
        result['write_contract'] = expected_writes
        result['compatibility'] = {
            'source_schema_version': 1,
            'reason': 'Saved request predates the explicit split between code edits and runtime evidence writes.',
        }
        result['evidence']['case_trace']['required_status'] = 'checked'
    elif result.get('write_contract') != expected_writes:
        raise ValueError('Builder request write contract differs from controller paths')
    if result['evidence']['case_trace'].get('required_status') != 'checked':
        raise ValueError('Builder request has a non-canonical trace status')
    return result


def generation_request(data, execution_contract):
    """Keep code edits separate from execution writes under one authoritative contract."""
    data = json.loads(json.dumps(data))
    context = json.loads(data['context'])
    context['builder_execution_contract'] = execution_contract
    data['context'] = json.dumps(context, ensure_ascii=False)
    data['constraints'] = (
        'The allowed_paths list limits files in your returned code edits only. '
        'Generate only the assigned files. At execution time the generated program '
        'IS permitted to create directories and evidence files under experiment/results/, '
        'write experiment/report.md, and use the supplied TMPDIR for temporary files. '
        'At runtime, allowed_paths are read-only. If assignment prose names one of them as a '
        'destination for temporary data, use TMPDIR instead. Do this only when the exact path '
        'is not part of the observation; otherwise stop and state the conflict. '
        'Do not return generated evidence or results-directory entries as code edits. '
        'All other existing files, including generated executable code and frozen cases, are read-only at runtime. '
        'No live services, credentials, external writes, installation or deployment. '
        'Preserve all selected cases and source-grounded limits. '
        'Do not implement missing product behavior to make a probe pass. '
        'The Authoritative execution contract is code-derived from the actual launcher and '
        'downstream reviewer. It supersedes conflicting execution mechanics in assignment prose; '
        'the assignment remains authoritative for business cases and observation boundaries.')
    return data


def source_provenance(handoff, request, correction_sources=None):
    """Bind supplied source bytes to Git without asking the builder to infer ancestry."""
    repository = Path(handoff['repository'])
    commit = handoff['commit']
    def git(*args):
        return subprocess.run(['git', '-C', str(repository), *args], capture_output=True, check=True).stdout
    identity = git('rev-list', '--parents', '-n', '1', commit).decode().strip().split()
    if not identity or identity[0] != commit: raise ValueError('Cannot resolve the prepared source commit')
    correction_sources = correction_sources or {}
    source_rows = []
    for row in request['files']:
        path = row['path'];local = Path(request['baseline']) / path
        if sha(local) != row['sha256']: raise ValueError('Prepared source changed: ' + path)
        if path in correction_sources:
            if row['sha256'] != correction_sources[path]:
                raise ValueError('Correction harness differs from its verified prior generation: ' + path)
            source_rows.append({**row, 'role': 'verified prior generated research harness'})
            continue
        if path.startswith('references/'):
            source_rows.append({**row, 'role': 'archived reference; not installed product'})
            continue
        raw = git('show', commit + ':' + path)
        if raw != local.read_bytes(): raise ValueError('Source snapshot differs from commit: ' + path)
        git_blob = git('rev-parse', commit + ':' + path).decode().strip()
        if len(git_blob) != 40 or any(character not in '0123456789abcdef' for character in git_blob):
            raise ValueError('Invalid Git blob identity for current product source: ' + path)
        source_rows.append({**row, 'role': 'current product', 'commit': commit,
                            'git_blob': git_blob})
    changes = []
    for line in git('diff-tree', '--root', '--no-commit-id', '--name-status', '-r', '--no-renames', commit).decode().splitlines():
        status, path = line.split('\t', 1)
        item = {'status': status, 'path': path}
        if status != 'D': item['sha256'] = hashlib.sha256(git('show', commit + ':' + path)).hexdigest()
        changes.append(item)
    return {'commit': commit, 'parents': identity[1:], 'commit_changes': changes,
            'snapshot_root': request['baseline'], 'source_files': source_rows,
            'verification': 'Controller compared every current-product snapshot file byte-for-byte with git show at this commit. Archived references are separately identified by SHA-256. Runtime should verify snapshot hashes; Git access is unnecessary.'}


def model_source_provenance(provenance):
    """Expose source roles to the builder without delegating integrity checks to it."""
    return {
        'verification': provenance['verification'],
        'integrity_owner': (
            'Source hashes and Git identities are code-validated controller facts. '
            'Their complete values remain in the audit artifact and are not model decisions.'),
        'source_files': [
            {'path': row['path'], 'role': row['role']}
            for row in provenance['source_files']
        ],
    }


def source_integrity_receipt(provenance, provenance_reference):
    """Record controller-owned integrity proof without exposing raw identities to the model."""
    source_files = provenance['source_files']
    return {
        'schema_version': 1,
        'contract': 'controller-source-integrity-v1',
        'status': 'verified',
        'owner': 'prepared-execution-controller',
        'source_provenance': provenance_reference,
        'verification': provenance['verification'],
        'source_file_count': len(source_files),
        'current_product_file_count': sum(
            1 for row in source_files if row['role'] == 'current product'),
        'archived_reference_file_count': sum(
            1 for row in source_files if row['role'] != 'current product'),
    }


def model_source_integrity_contract():
    """Tell generated code how to consume controller proof, never how to reproduce it."""
    return {
        'contract': 'controller-source-integrity-v1',
        'runtime_path': SOURCE_INTEGRITY_RUNTIME_PATH,
        'receipt_fields': {
            'schema_version': 'schema_version',
            'contract': 'contract',
            'status': 'status',
        },
        'required_schema_version': 1,
        'required_status': 'verified',
        'use': (
            'Read this controller-created, read-only receipt and record its verified status in '
            'the experiment evidence. Do not re-hash source, query Git, count hash characters, '
            'or treat source identity as a model judgment.'),
    }


def install_source_integrity_receipt(candidate, receipt_path):
    """Inject the verified controller receipt as a protected runtime input."""
    candidate = Path(candidate).resolve();receipt_path = Path(receipt_path).resolve()
    receipt = read(receipt_path)
    if (set(receipt) != {'schema_version', 'contract', 'status', 'owner',
                         'source_provenance', 'verification', 'source_file_count',
                         'current_product_file_count', 'archived_reference_file_count'}
            or receipt['schema_version'] != 1
            or receipt['contract'] != 'controller-source-integrity-v1'
            or receipt['status'] != 'verified'):
        raise ValueError('Invalid controller source-integrity receipt')
    verify(receipt['source_provenance'])
    target = candidate / SOURCE_INTEGRITY_RUNTIME_PATH
    if target.exists() or target.is_symlink():
        raise ValueError('Candidate collided with the controller source-integrity receipt')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(receipt_path, target)
    return target


def materialize_runtime_source(handoff, request, config, output, runtime_adapters):
    """Supply adapter-known project files from the already-bound product commit."""
    baseline=Path(request['baseline']).resolve();repository=Path(handoff['repository']).resolve()
    commit=handoff['commit'];required=runtime_adapters.required_project_files(config,baseline)
    target_root=Path(output).resolve()/'runtime-source'
    if target_root.exists():raise ValueError('Runtime source already exists; use a fresh attempt')
    target_root.mkdir(parents=True)
    rows=[]
    for path in required:
        result=subprocess.run(['git','-C',str(repository),'show',commit+':'+path],capture_output=True)
        if result.returncode:
            raise ValueError('Bound commit lacks required runtime project file: '+path)
        raw=result.stdout;baseline_path=baseline/path
        if baseline_path.exists() and baseline_path.read_bytes()!=raw:
            raise ValueError('Evidence baseline differs from bound runtime project file: '+path)
        target=target_root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        rows.append({'path':path,'sha256':sha(target),'source_commit':commit,
                     'present_in_evidence_baseline':baseline_path.is_file()})
    manifest={'schema_version':1,'repository':str(repository),'commit':commit,
              'purpose':'adapter-required runtime input only; not model-selected evidence',
              'files':rows}
    manifest_path=Path(output).resolve()/'runtime-source-manifest.json';save(manifest_path,manifest)
    return target_root,ref(manifest_path)


def overlay_correction_generation(data, previous_candidate, previous_result, baseline, snapshot):
    """Build a correction baseline from files the prior model actually changed."""
    baseline = Path(baseline).resolve();previous_candidate = Path(previous_candidate).resolve()
    shutil.copytree(data['baseline'], baseline)
    units = {item['path']: item['text'] for item in data['source_units']}
    changed_paths = previous_result.get('changed_paths')
    if (not isinstance(changed_paths, list) or any(not isinstance(path, str) for path in changed_paths)
            or len(changed_paths) != len(set(changed_paths))
            or any(path not in data['allowed_paths'] for path in changed_paths)):
        raise ValueError('Prior generation changed-path receipt is invalid')
    correction_sources = {}
    for path in changed_paths:
        source = previous_candidate / path
        if not source.is_file():
            raise ValueError('Prior generated harness is missing: ' + path)
        target = baseline / path;target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target);units[path] = source.read_text()
        correction_sources[path] = sha(source)
    data['baseline'] = str(baseline)
    data['files'] = snapshot(baseline)
    data['source_units'] = [{'path': path, 'text': text} for path, text in units.items()]
    return correction_sources


def prepare(state, output, php=None, autoload=None, docker_config=None, runtime_config=None,
            external_schema_config=None):
    root = Path(state['root']);output = Path(output).resolve()
    if state['stage'] != 'build' or (state.get('pending') or {}).get('action') != 'prepare_build':
        raise ValueError('Requires the pending selected experiment')
    bound = state['selection_preparation']
    handoff_path = verify({'path': str(root / bound['path']), 'sha256': bound['sha256']})
    handoff = read(handoff_path);cycle = read(state['cycle'])
    for key, expected in [('selection', cycle['selection']), ('goal', state['goal']), ('answers', state['answers'])]:
        actual = handoff['bindings'][key]
        if actual != ref(root / expected['path']) or actual['sha256'] != expected['sha256']:
            raise ValueError('Prepared experiment belongs to another ' + key)
    request = verify(handoff['creation_request']);assignment = verify(handoff['assignment'])
    verify(handoff['verification_plan'])
    data = read(request)
    correction = correction_for_generation(state, cycle)
    sys.path.insert(0, str(Path(state['skills']) / 'atom-building-machinery/scripts'))
    import runtime_adapters
    if runtime_config and (php or autoload or docker_config):
        raise ValueError('Use --runtime-config alone, or the legacy PHP arguments')
    if correction:
        if runtime_config or php or autoload or docker_config:
            raise ValueError('A research correction reuses its verified runtime; do not replace it')
        runtime = reusable_runtime(correction, root)
        runtime_adapters.open_runtime(runtime)
    else:
        config = read(runtime_config) if runtime_config else runtime_adapters.legacy_config(php,autoload,docker_config)
        runtime_source,runtime_source_manifest=materialize_runtime_source(
            handoff,data,config,output,runtime_adapters)
        runtime = runtime_adapters.prepare(config,runtime_source,data,output/'runtime')
    scripts = Path(state['skills']) / 'atom-building-machinery/scripts'
    correction_sources = {}
    if correction:
        previous_handoff = resolve_root_ref(correction['previous_prepared_execution'], root)
        previous_bindings = read(previous_handoff.parent / 'bindings.json')
        previous_request = verify(previous_bindings['request'])
        previous_candidate = verify_generation(previous_handoff.parent / 'generation', previous_request, scripts)
        previous_result = read(previous_handoff.parent / 'generation' / 'result.json')
        from candidate_builder_contract import snapshot
        baseline = output / 'correction-baseline'
        if baseline.exists(): raise ValueError('Correction baseline already exists; use a fresh attempt')
        correction_sources = overlay_correction_generation(
            data, previous_candidate, previous_result, baseline, snapshot)
    from external_schema_evidence import materialize as materialize_schema_evidence
    from external_schema_evidence import model_context as schema_evidence_context
    external_schema_evidence = materialize_schema_evidence(
        external_schema_config, output / 'external-evidence', save, ref)
    runtime_context = runtime_adapters.model_context(runtime)
    derived = generation_request(
        data, builder_execution_contract(runtime_context, data['allowed_paths']))
    provenance = source_provenance(handoff, data, correction_sources)
    context = json.loads(derived['context'])
    context['source_provenance'] = model_source_provenance(provenance)
    if external_schema_evidence:
        context['external_schema_evidence'] = schema_evidence_context(external_schema_evidence)
        provenance['external_schema_evidence'] = [
            {
                'projection': item['projection'],
                'source': item['data']['source'],
                'tables': item['data']['tables'],
                'scope': item['data']['scope'],
                'row_data_included': item['data']['row_data_included'],
            }
            for item in external_schema_evidence['projections']
        ]
        derived['constraints'] += (
            ' External schema evidence is a dated, hash-bound snapshot. Use its complete table '
            'definitions for schema facts at that snapshot only; do not claim a live database '
            'observation or infer row data.')
    if correction:
        context['approved_research_correction'] = correction
        derived['constraints'] += (
            ' This is a correction of the same selected research job. Address only the '
            'assessment-backed correction, preserve already supported cases, and report the '
            'observed boundary exactly. Do not change the selected work or implement product behavior.')
    derived['constraints'] += (
        ' Source identity, Git ancestry, source hashes and protected-file immutability are '
        'controller-owned checks. At runtime read the supplied controller source-integrity '
        'receipt and record its verified status; do not reproduce those checks in generated code. '
        'If assignment prose delegates those checks to run.py, the controller receipt satisfies '
        'that integrity obligation while the experiment remains responsible for its product observations.')
    derived['context'] = json.dumps(context, ensure_ascii=False)
    provenance_path = output / 'source-provenance.json'
    save(provenance_path, provenance)
    integrity_path = output / 'source-integrity-receipt.json'
    save(integrity_path, source_integrity_receipt(provenance, ref(provenance_path)))
    sys.path.insert(0, str(scripts))
    from candidate_builder_contract import prepare as validate_request
    validate_request(derived)
    save(output / 'creation-request.json', derived)
    result = {'schema_version': 2,
              'preparation': ref(handoff_path), 'original_request': ref(request), 'request': ref(output / 'creation-request.json'), 'assignment': ref(assignment),
              'runtime': runtime, 'builder': ref(scripts / 'candidate_builder.py'),
              'connection': ref(Path(__file__)), 'selection': cycle['selection'],
              'source_integrity_receipt': ref(integrity_path)}
    if external_schema_evidence:
        result['external_schema_evidence'] = {
            'config': external_schema_evidence['config'],
            'manifest': external_schema_evidence['manifest'],
        }
    if not correction:result['runtime_source_manifest']=runtime_source_manifest
    save(output / 'bindings.json', result)
    return result


def resume_bindings(state, output):
    """Reuse immutable preparation only after generation and execution are receipted."""
    output = Path(output).resolve()
    bindings_path = output / 'bindings.json'
    generation_receipt = output / 'receipts' / 'generation.json'
    execution_receipt = output / 'execution' / 'result.json'
    if not bindings_path.exists():
        return None
    if not generation_receipt.is_file() or not execution_receipt.is_file():
        return None
    cycle = read(state['cycle'])
    normal_execution = (
        state['stage'] == 'build'
        and (state.get('pending') or {}).get('action') == 'prepare_build'
    )
    unassessed_export_repair = (
        state['stage'] == 'assessment'
        and cycle.get('research_result') is not None
        and cycle.get('assessment') is None
        and (output / 'handoff.json').is_file()
    )
    if not normal_execution and not unassessed_export_repair:
        raise ValueError('Requires the pending selected experiment')
    root = Path(state['root'])
    bound = read(bindings_path)
    expected_preparation = ref(root / state['selection_preparation']['path'])
    if bound.get('preparation') != expected_preparation:
        raise ValueError('Saved execution belongs to another preparation')
    if bound.get('selection') != cycle['selection']:
        raise ValueError('Saved execution belongs to another selection')
    version = bound.get('schema_version', 1)
    if version not in (1, 2):
        raise ValueError('Unsupported prepared-execution bindings version')
    required = ['preparation', 'original_request', 'request', 'assignment', 'builder']
    if version == 2:
        required.append('source_integrity_receipt')
    for key in required:
        verify(bound[key])
    if bound.get('external_schema_evidence'):
        verify(bound['external_schema_evidence']['config'])
        manifest = read(verify(bound['external_schema_evidence']['manifest']))
        for projection in manifest['projections']:
            verify(projection)
    verify(bound['runtime']['receipt'])
    verify(ref(generation_receipt))
    verify(ref(execution_receipt))
    return bound


def root_ref(path, root):
    """Create the loop's root-relative, content-bound reference."""
    root = Path(root).resolve()
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    if path.is_symlink():
        raise ValueError('Research evidence is not a regular file under the loop root: ' + str(path))
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Research evidence is not a regular file under the loop root: ' + str(path))
    return {'path': str(path.relative_to(root)), 'sha256': sha(path)}


def resolve_root_ref(reference, root):
    root = Path(root).resolve()
    path = root / reference['path']
    if (set(reference) != {'path', 'sha256'} or path.is_symlink()
            or not path.resolve().is_relative_to(root) or not path.is_file()
            or sha(path) != reference['sha256']):
        raise ValueError('Changed or invalid loop reference: ' + str(reference.get('path')))
    return path


def correction_for_generation(state, cycle):
    reference = state.get('research_correction')
    if not reference:
        return None
    path = resolve_root_ref(reference, state['root'])
    correction = read(path)
    if (correction.get('kind') != 'selected_research_correction'
            or correction.get('goal') != cycle['goal']
            or correction.get('selection') != cycle['selection']
            or not correction.get('reason', '').strip()):
        raise ValueError('Research correction does not bind this selected job')
    resolve_root_ref(correction['prior_research_result'], state['root'])
    resolve_root_ref(correction['assessment'], state['root'])
    resolve_root_ref(correction['previous_prepared_execution'], state['root'])
    return correction


def reusable_runtime(correction, root):
    previous_handoff = resolve_root_ref(correction['previous_prepared_execution'], root)
    bindings = read(previous_handoff.parent / 'bindings.json')
    return bindings['runtime']


def completed_handoff(state, output, bound):
    """Verify a completed experiment handoff before reusing it without model calls."""
    output = Path(output).resolve()
    handoff_path = output / 'handoff.json'
    if not handoff_path.exists():
        return None
    handoff = read(handoff_path)
    cycle = read(state['cycle'])
    if handoff.get('selection') != bound['selection'] or handoff['selection'] != cycle['selection']:
        raise ValueError('Prepared execution handoff belongs to another selection')
    expected = {
        'generation': output / 'generation' / 'result.json',
        'execution': output / 'execution' / 'result.json',
    }
    for key, expected_path in expected.items():
        actual_path = verify(handoff[key])
        if actual_path.resolve() != expected_path.resolve():
            raise ValueError('Prepared execution handoff has a changed ' + key)
    cases = handoff.get('review', {}).get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('Prepared execution handoff has no completed review cases')
    root = Path(state['root'])
    for case in cases:
        citations = case.get('citations')
        if not isinstance(citations, list) or not citations:
            raise ValueError('Prepared execution handoff has an uncited review case')
        for citation in citations:
            try:
                citation_representation(citation, root)
            except ValueError:
                raise ValueError('Prepared execution handoff citation no longer resolves: ' + case.get('id', 'unknown'))
    return handoff


def compact_execution_facts(output, handoff, root):
    """Expose code-checkable runtime facts without transporting full raw traces."""
    output = Path(output)
    execution = read(verify(handoff['execution']))
    provenance_path = output / 'source-provenance.json'
    provenance = read(provenance_path)
    bindings = read(output / 'bindings.json')
    request = read(verify(bindings['request']))
    execution_contract = execution_contract_from_request(request)
    outcomes = []
    evidence = []
    selected_outputs = review_output_references(
        output / 'execution' / 'source' / 'experiment', execution['output_files'])
    for reference in selected_outputs:
        path = verify(reference)
        if not (path.name.endswith('.trace.json') or path.name.endswith('.process.json')):
            continue
        admitted = root_ref(path, root)
        evidence.append(admitted)
        data = read(path)
        if path.name.endswith('.trace.json'):
            if data.get('status') != 'checked':
                raise ValueError('Trace has non-canonical status: ' + str(path))
            checks = data.get('checks', [])
            if not isinstance(checks, list) or not all(
                    isinstance(item, dict)
                    and isinstance(item.get('name'), str)
                    and type(item.get('observed_expected')) is bool
                    for item in checks):
                raise ValueError('Trace has invalid checks: ' + str(path))
            outcomes.append({
                'evidence': admitted,
                'kind': 'trace',
                'status': data.get('status'),
                'check_count': len(checks),
                'failed_checks': [item.get('name') for item in checks
                                  if item.get('observed_expected') is not True],
            })
        else:
            outcomes.append({
                'evidence': admitted,
                'kind': 'process',
                'exit_status': data.get('exit_status'),
                'stderr_empty': not bool(data.get('stderr')),
            })
    source_files = provenance.get('source_files', [])
    protection_reference = execution.get('protected_source_comparison')
    protection = read(verify(protection_reference)) if protection_reference else None
    version_reconciliation = {
        'schema_version': 1,
        'kind': 'git_version_reconciliation',
        'status': 'verified',
        'research_commit': provenance.get('commit'),
        'direct_parents': provenance.get('parents', []),
        'commit_changes': provenance.get('commit_changes', []),
        'verification': (
            'Controller resolved the research commit, its direct parent list and its complete '
            'no-renames commit diff from Git.'),
    }
    if (not isinstance(version_reconciliation['research_commit'], str)
            or not isinstance(version_reconciliation['direct_parents'], list)
            or not isinstance(version_reconciliation['commit_changes'], list)):
        raise ValueError('Source provenance cannot produce a version-reconciliation receipt')
    version_path = save_versioned_json(
        output / 'version-reconciliation.json', version_reconciliation)
    write_boundary = {
        'schema_version': 1,
        'kind': 'execution_write_boundary',
        'status': ('verified' if protection and protection.get('status') == 'verified_unchanged'
                   else 'not_verified'),
        'write_contract': execution_contract['write_contract'],
        'protected_source_status': protection.get('status') if protection else None,
        'verification': (
            'The controller excludes only the declared runtime evidence paths from source '
            'protection; every other candidate file is compared before and after execution. '
            'Temporary files use the launcher-supplied TMPDIR outside the candidate source tree.'),
    }
    write_path = save_versioned_json(output / 'write-boundary.json', write_boundary)
    evidence.extend([root_ref(version_path, root), root_ref(write_path, root)])
    facts = {
        'execution_receipt': root_ref(handoff['execution']['path'], root),
        'generation_receipt': root_ref(handoff['generation']['path'], root),
        'bindings': root_ref(output / 'bindings.json', root),
        'source_provenance': root_ref(provenance_path, root),
        'source_commit': provenance.get('commit'),
        'version_reconciliation': version_reconciliation,
        'write_boundary': write_boundary,
        'source_file_count': len(source_files),
        'current_product_files': sum(1 for item in source_files if item.get('role') == 'current product'),
        'archived_reference_files': sum(1 for item in source_files if item.get('role') != 'current product'),
        'returncode': execution.get('returncode'),
        'timed_out': execution.get('timed_out'),
        'protected_changes': execution.get('protected_changes'),
        'protected_source_comparison': (
            root_ref(protection_reference['path'], root) if protection_reference else None),
        'protected_source_status': protection.get('status') if protection else None,
        'protected_source_count': protection.get('protected_source_count') if protection else None,
        'generated_report_changed': execution.get('generated_report_changed'),
        'process_count': sum(1 for item in outcomes if item['kind'] == 'process'),
        'trace_count': sum(1 for item in outcomes if item['kind'] == 'trace'),
        'all_processes_passed': all(item.get('exit_status') == 0 for item in outcomes
                                    if item['kind'] == 'process'),
        'all_trace_checks_passed': all(not item.get('failed_checks') and item.get('status') == 'checked'
                                       for item in outcomes if item['kind'] == 'trace'),
        'outcomes': outcomes,
        'verification': (
            'Code verified every referenced hash, summarized each saved process exit and trace '
            'check, bound supplied current-product source bytes to the recorded Git commit, and '
            'recorded the before-and-after hashes for every protected input.'),
    }
    return facts, evidence


def research_result_from_handoff(state, output, handoff_path, handoff):
    """Mechanically bind reviewed experiment evidence to the current cycle."""
    root = Path(state['root'])
    cycle = read(state['cycle'])
    if handoff.get('selection') != cycle['selection']:
        raise ValueError('Prepared experiment result belongs to another selection')
    review = json.loads(json.dumps(handoff['review']))
    cited_evidence = []
    cited_paths = set()
    for case in review['cases']:
        verified = []
        for citation in case['citations']:
            quote = citation['quote']
            try:
                source, text, transport = citation_representation(citation, root)
            except ValueError:
                raise ValueError('Prepared execution handoff citation no longer resolves: ' + case['id'])
            materialized = materialize_citation_representation(output, source, text, transport)
            reference = root_ref(materialized['path'], root)
            starts = []
            cursor = 0
            while True:
                start = text.find(quote, cursor)
                if start < 0:
                    break
                starts.append(start)
                cursor = start + max(1, len(quote))
            if not quote.strip() or not starts:
                raise ValueError('Prepared execution handoff citation no longer resolves: ' + case['id'])
            verified_citation = {
                'evidence': reference, 'quote': quote,
                'occurrences': [{'start': start, 'end': start + len(quote)} for start in starts],
            }
            if reference != source:
                verified_citation.update(source_evidence=source, transport=transport)
            verified.append(verified_citation)
            if reference['path'] not in cited_paths:
                cited_evidence.append(reference)
                cited_paths.add(reference['path'])
            if source['path'] not in cited_paths:
                cited_evidence.append(source)
                cited_paths.add(source['path'])
        case['citations'] = verified
    execution_facts, execution_evidence = compact_execution_facts(output, handoff, root)
    package = {
        'schema_version': 2,
        'kind': 'selected_research_assessment_package',
        'goal': cycle['goal'],
        'selection': cycle['selection'],
        'status': handoff['status'],
        'product_modified': handoff.get('product_modified', False),
        'goal_complete': handoff.get('goal_complete', False),
        'generation': root_ref(handoff['generation']['path'], root),
        'execution': root_ref(handoff['execution']['path'], root),
        'execution_facts': execution_facts,
        'review': review,
        'raw_evidence': cited_evidence,
    }
    package_path = save_versioned_json(Path(output) / 'assessment-package.json', package)
    paths = [handoff_path, handoff['generation']['path'], handoff['execution']['path']]
    for case in review['cases']:
        for citation in case['citations']:
            paths.append(citation['evidence']['path'])
            if citation.get('source_evidence'):
                paths.append(citation['source_evidence']['path'])
    paths.extend(item['path'] for item in execution_evidence)
    paths.extend([execution_facts['bindings']['path'], execution_facts['source_provenance']['path']])
    if execution_facts.get('protected_source_comparison'):
        paths.append(execution_facts['protected_source_comparison']['path'])
    evidence = []
    seen = set()
    for path in paths:
        reference = root_ref(path, root)
        if reference['path'] not in seen:
            evidence.append(reference)
            seen.add(reference['path'])
    result = {
        'kind': 'selected_research_result',
        'goal': cycle['goal'],
        'selection': cycle['selection'],
        'evidence': evidence,
        'assessment_package': root_ref(package_path, root),
    }
    destination = save_versioned_json(Path(output) / 'research-result.json', result)
    return destination


def verify_assessment_admission(state, output, research_result):
    """Prove the exported package is consumable before advancing the loop."""
    root = Path(state['root'])
    cycle = read(state['cycle'])
    cycle['research_result'] = root_ref(research_result, root)
    cycle['assessment'] = None
    candidate_cycle = save_versioned_json(Path(output) / 'assessment-admission-cycle.json', cycle)
    context_script = Path(state['skills']) / 'atom-assessment-machinery/scripts/context.py'
    spec = importlib.util.spec_from_file_location('_prepared_research_assessment_context', context_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    admission = module.assemble(root, candidate_cycle)
    save_versioned_json(Path(output) / 'assessment-admission.json', admission)
    if admission.get('collection_status') != 'references_verified':
        raise ValueError('Prepared research result cannot enter assessment: ' + json.dumps(
            admission.get('missing_or_inconsistent', []), ensure_ascii=False, separators=(',', ':')))
    return admission


def completed_execution(output, request, skills):
    """Load and verify completed generation/execution without reopening runtime."""
    output = Path(output).resolve()
    receipt = output / 'execution' / 'result.json'
    if not receipt.exists():
        return None
    verify_generation(output / 'generation', request, skills)
    result = read(receipt)
    for r in result['output_files'] + [result['stdout'], result['stderr'], result['command'], result['isolation']]:
        verify(r)
    return result


def execute(state, output, php=None, autoload=None, prepare_only=False, docker_config=None,
            runtime_config=None, external_schema_config=None):
    output = Path(output).resolve()
    bound = resume_bindings(state, output) or prepare(
        state, output, php, autoload, docker_config, runtime_config,
        external_schema_config)
    saved_handoff = completed_handoff(state, output, bound)
    if saved_handoff is not None:
        research_result = research_result_from_handoff(
            state, output, output / 'handoff.json', saved_handoff)
        verify_assessment_admission(state, output, research_result)
        return {'action': saved_handoff['status'], 'handoff': str(output / 'handoff.json'),
                'research_result': str(research_result), 'model_calls': 0}
    if prepare_only:
        return {'action': 'execution_prepared', 'bindings': str(output / 'bindings.json'),
                'model_calls': 2, 'stages': ['generation', 'confined_execution', 'independent_review']}
    request = verify(bound['request']);assignment = read(verify(bound['assignment']))
    skills = Path(state['skills'])
    generation = output / 'generation'
    run = output / 'execution'
    receipt = run / 'result.json'
    result = completed_execution(output, request, skills)
    if result is None:
        import runtime_adapters
        runtime = bound['runtime']
        isolation = runtime_adapters.isolation(runtime, output / 'isolation')
        once(output, 'generation', [sys.executable, '-B', str(verify(bound['builder'])), str(request), str(generation)],
             generation, generation / 'result.json')
        candidate = verify_generation(generation, request, skills)
        if run.exists(): raise ValueError('Interrupted execution exists; inspect before repeating the experiment')
        run.mkdir();scratch = run / 'tmp';scratch.mkdir()
        execution_source = run / 'source'
        shutil.copytree(candidate, execution_source)
        candidate = execution_source
        install_source_integrity_receipt(candidate, verify(bound['source_integrity_receipt']))
        before = files(candidate)
        emit(output, 'isolated_execution_started')
        observed = runtime_adapters.execute(runtime,candidate,run)
        code = observed['returncode'];timed_out = observed['timed_out']
        changes = []
        for row in before:
            p = Path(row['path'])
            if not p.is_file() or sha(p) != row['sha256']: changes.append(str(p.relative_to(candidate)))
        comparison = protected_source_comparison(candidate, before)
        comparison_path = run / 'protected-source-comparison.json'
        save(comparison_path, comparison)
        protected_changes = comparison['changes']
        result = {'returncode': code, 'timed_out': timed_out, 'protected_changes': protected_changes,
                  'generated_report_changed': 'experiment/report.md' in changes, 'isolation': isolation,
                  'stdout': ref(run / 'stdout.txt'), 'stderr': ref(run / 'stderr.txt'),
                  'output_files': files(candidate / 'experiment'), 'command': ref(run / 'command.json'),
                  'protected_source_comparison': ref(comparison_path)}
        save(receipt, result);emit(output, 'isolated_execution_returned', returncode=code, timed_out=timed_out)
    if result['protected_changes']: raise ValueError('Generated probe modified protected inputs: ' + str(result['protected_changes']))
    # Review observed execution even when it fails. Failure cannot become completion.
    sys.path.insert(0, str(skills / 'input-interview-machinery/scripts'))
    import checkpoint
    import run as review
    from selection_preparation import obj, array, TEXT
    review_references = review_output_references(
        run / 'source' / 'experiment', result['output_files'])
    review_inputs = review_references + [result['stdout'], result['stderr']]
    if result.get('protected_source_comparison'):
        review_inputs.append(result['protected_source_comparison'])
    evidence = review_evidence_set(review_inputs)
    execution_contract = execution_contract_from_request(read(request))
    packet = {'assignment': assignment, 'execution_contract': execution_contract,
              'execution': review_execution_projection(result),
              'evidence': evidence,
              'original_source_manifest': source_manifest(read(request)['source_units'])}
    sys.path.insert(0, str(skills / 'atom-assessment-machinery/scripts'))
    from evidence_transport import pack, unpack
    packed = pack(packet)
    if unpack(packed) != packet: raise ValueError('Review transport changed evidence')
    prompt = ('Assess this actual disposable experiment against each assigned case. Use code and bounded trace projections, not the generated report alone. '
              'Determine whether the real source ran, whether assumptions replaced missing product behavior, and whether the observation supports the case. '
              'A correctly demonstrated missing product connection can satisfy this research experiment. An execution failure cannot. '
              'Return every case once with supported, unsupported or cannot_assess, explain why and cite captured evidence. '
              'Each citation must identify exactly one supplied evidence path and one exact contiguous quote from that file. '
              'The evidence path identifies the supplied transport entry; projected text is materialized for downstream verification while its raw source remains preserved. '
              'Use multiple citation objects when a judgment needs multiple files or fragments; never join paths or quotes. '
              'Metadata-only entries prove artifact identity and preservation, not omitted content. '
              'For file-write judgments, use execution_contract as authoritative; assignment '
              'allowed_paths describe generated code edits, while its write_contract separately '
              'defines permitted runtime evidence and temporary writes. '
              'Do not claim live identity, payment-provider or full checkout proof. No tools.\n' + json.dumps(packed, ensure_ascii=False, separators=(',', ':')))
    if len(prompt) > 1048576: raise ValueError('Review exceeds CLI input limit; no call made')
    ids = [c['id'] for c in assignment['cases']]
    texts = {x['path']: x['text'] for x in evidence}
    legacy = saved_legacy_review(output / 'review', ids)
    if legacy:
        answer = repair_legacy_review(output, legacy[0], legacy[1], ids, texts,
                                      checkpoint, review, obj, array, TEXT)
    else:
        schema = review_schema(ids, list(texts), obj, array, TEXT)
        answer, _ = checkpoint.call(
            output / 'review', 'experiment-review', prompt, schema,
            lambda p: review.CodexTransport(p, {
                'provider':'codex', 'model':'gpt-6-astra', 'reasoning':'medium'}))
        validate_review_citations(answer, ids, texts)
    complete = result['returncode'] == 0 and not result['timed_out'] and all(c['verdict']=='supported' for c in answer['cases'])
    handoff = {'status': 'experiment_supported' if complete else 'experiment_needs_attention',
               'selection': bound['selection'], 'generation': ref(generation / 'result.json'),
               'execution': ref(receipt), 'review': answer, 'product_modified': False, 'goal_complete': False}
    save(output / 'handoff.json', handoff)
    research_result = research_result_from_handoff(
        state, output, output / 'handoff.json', handoff)
    verify_assessment_admission(state, output, research_result)
    return {'action': handoff['status'], 'handoff': str(output / 'handoff.json'),
            'research_result': str(research_result)}
