"""Collect a cycle's saved assessment inputs without interpreting their meaning."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def assemble(root, cycle_path):
    root = Path(root).resolve()
    records, issues = {}, []

    def issue(code, role, detail):
        issues.append({'code': code, 'role': role, 'detail': detail})

    def load(role, ref):
        if ref is None:
            issue('missing_record', role, 'No reference is recorded for this input.')
            return None
        try:
            if set(ref) != {'path', 'sha256'}:
                raise ValueError('Reference must contain path and sha256.')
            p = Path(ref['path'])
            p = p if p.is_absolute() else root / p
            if not p.resolve().is_relative_to(root) or p.is_symlink() or not p.is_file():
                raise ValueError('Reference must resolve to a regular file within the source repository.')
            raw = p.read_bytes()
            if sha(raw) != ref['sha256']:
                raise ValueError('File hash differs from the recorded reference.')
            data = json.loads(raw)
            records[role] = {'source': {'path': str(p.relative_to(root)), 'sha256': sha(raw)}, 'data': data}
            return data
        except (OSError, ValueError, TypeError) as error:
            issue('invalid_reference', role, str(error))
            return None

    cycle_path = Path(cycle_path).resolve()
    cycle = load('cycle', {'path': str(cycle_path), 'sha256': sha(cycle_path.read_bytes())})
    if not isinstance(cycle, dict):
        raise ValueError('Cycle must be an available JSON object.')
    goal = load('goal', cycle.get('goal'))
    answers = load('input_answers', cycle.get('input_answers'))
    selection = load('selection', cycle.get('selection'))
    build = load('build', cycle.get('build'))
    previous = None
    if cycle.get('previous_cycle') is not None:
        previous = load('previous_cycle', cycle['previous_cycle'])
        if previous is not None:
            load('previous_assessment', previous.get('assessment'))
            if previous.get('goal_id') != cycle.get('goal_id'):
                issue('goal_mismatch', 'previous_cycle', 'Previous cycle names a different goal.')
            if previous.get('cycle_id') == cycle.get('cycle_id'):
                issue('same_cycle', 'previous_cycle', 'Previous and current cycle identities must differ.')
    if goal is not None:
        fixed = goal.get('goal', {})
        if fixed.get('id') != cycle.get('goal_id'):
            issue('goal_mismatch', 'cycle', 'Cycle identity differs from the fixed goal.')
        if selection is not None and selection.get('goal') != fixed.get('outcome'):
            issue('goal_mismatch', 'selection', 'Selection does not carry the exact fixed delivery goal.')
        if build is not None:
            binding = build.get('completion', {}).get('goal_context', {})
            if binding.get('sha256') != cycle['goal']['sha256']:
                issue('goal_mismatch', 'build', 'Build completion is bound to a different fixed goal version.')
    if answers is not None:
        if answers.get('snapshot', {}).get('fixed_goal') != cycle.get('goal'):
            issue('goal_mismatch', 'input_answers', 'Answers and cycle do not reference the same fixed goal.')
        if selection is not None and selection.get('input_sha256') != cycle['input_answers']['sha256']:
            issue('input_version_mismatch', 'selection', 'Selection used a different answer snapshot.')
    if build is not None and build.get('completion', {}).get('achieved') is not True:
        issue('build_not_completed', 'build', 'Build has no recorded achieved contribution.')
    return {'schema_version': 1, 'purpose': 'post_build_assessment_context',
            'cycle_id': cycle.get('cycle_id'), 'records': records,
            'missing_or_inconsistent': issues,
            'collection_status': 'needs_inputs' if issues else 'references_verified',
            'previous_assessment_applicable': cycle.get('previous_cycle') is not None,
            'assessment_boundary': 'Reference verification is not a judgment of evidence sufficiency, scope alignment, progress or goal completion. Compare selected intent with the admitted atom and actual results in the preserved records. No historical wording or judgment has been rewritten.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--cycle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = assemble(args.root, args.cycle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    if json.loads(args.output.read_text()) != result:
        raise ValueError('Saved context did not round-trip unchanged.')
    print(json.dumps({'context': str(args.output.resolve()), 'collection_status': result['collection_status'],
                      'issues': result['missing_or_inconsistent']}))


if __name__ == '__main__':
    main()
