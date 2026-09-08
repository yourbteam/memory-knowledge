"""Verify Requirements using the shared exporter over controller-frozen evidence."""
from pathlib import Path


def verify(handoff, read, exporter, runtime_bytes):
    exporter.validate_requirements_handoff(handoff)
    members = handoff['evidence_files']
    frozen = {}
    by_role = {}
    runtime = []
    for item in members:
        path = Path(item['path'])
        raw = read(path, item['sha256'])
        if len(raw) != item['size']:
            raise ValueError('Requirements evidence size differs from its sealed descriptor')
        if path in frozen and frozen[path] != raw:
            raise ValueError('Requirements evidence path has conflicting byte identities')
        frozen[path] = raw
        by_role.setdefault(item['role'], []).append(item)
        if item['role'] == 'runtime':
            name = item['identity']
            if path.name != name or name not in runtime_bytes or raw != runtime_bytes[name]:
                raise ValueError('Requirements runtime member differs from the pinned installed exporter runtime')
            runtime.append({'path': name, 'sha256': item['sha256']})
    if {r['path'] for r in runtime} != set(runtime_bytes):
        raise ValueError('Requirements runtime manifest is missing or adds a foreign executable member')
    if exporter.hashlib.sha256(exporter._handoff_canonical(sorted(runtime, key=lambda r: r['path']))).hexdigest() != handoff['exporter_source_sha256']:
        raise ValueError('Requirements exporter aggregate source identity differs')
    coverage = by_role['coverage'][0]
    work = Path(coverage['path']).parent
    runtime_roots = {Path(r['path']).parent for r in by_role.get('runtime', [])}
    if len(runtime_roots) != 1:
        raise ValueError('Requirements runtime members must name exactly one exporter source directory')
    rebuilt, evidence = exporter.build_requirements_handoff(
        work, handoff['requirements_document']['path'], handoff['coverage_sha256'],
        frozen_files=frozen, runtime_root=next(iter(runtime_roots)))
    if rebuilt != handoff:
        raise ValueError('Requirements handoff differs from full coverage, ruling, source and document reconstruction')
    if {p for p, raw in evidence.items() if isinstance(raw, bytes)} != set(frozen):
        raise ValueError('Requirements manifest includes unused or missing evidence')
    return {'schema_version': 1, 'record_id': 'requirements-' + handoff['handoff_sha256'],
            'handoff_sha256': handoff['handoff_sha256'], 'requirements': handoff['requirements'],
            'rejections': handoff['rejections'], 'owner_rulings': handoff['owner_rulings'],
            'unresolved_count': handoff['unresolved_count']}
