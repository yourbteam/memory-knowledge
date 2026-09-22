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

    def verify_reference(role, ref):
        if ref is None:
            issue('missing_record', role, 'No reference is recorded for this input.')
            return None, None
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
            return p, raw
        except (OSError, ValueError, TypeError) as error:
            issue('invalid_reference', role, str(error))
            return None, None

    def load(role, ref):
        p, raw = verify_reference(role, ref)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            records[role] = {'source': {'path': str(p.relative_to(root)), 'sha256': sha(raw)}, 'data': data}
            return data
        except (ValueError, TypeError) as error:
            issue('invalid_reference', role, str(error))
            return None

    cycle_path = Path(cycle_path).resolve()
    cycle = load('cycle', {'path': str(cycle_path), 'sha256': sha(cycle_path.read_bytes())})
    if not isinstance(cycle, dict):
        raise ValueError('Cycle must be an available JSON object.')
    goal = load('goal', cycle.get('goal'))
    answers = load('input_answers', cycle.get('input_answers'))
    selection = load('selection', cycle.get('selection'))
    research = cycle.get('research_result')
    build = None if research else load('build', cycle.get('build'))
    if research:
        if cycle.get('build') is not None:
            issue('conflicting_work', 'cycle', 'Research and build cannot both complete this selected job.')
        work = load('research_result', research)
        if work is not None:
            if work.get('kind') != 'selected_research_result' or work.get('goal') != cycle.get('goal') or work.get('selection') != cycle.get('selection'):
                issue('work_mismatch', 'research_result', 'Research must bind this exact selection and goal.')
            if not work.get('evidence'):
                issue('missing_evidence', 'research_result', 'Research needs saved supporting evidence.')
            package = load('research_assessment_package', work.get('assessment_package'))
            if package is not None:
                if (package.get('kind') != 'selected_research_assessment_package'
                        or package.get('goal') != cycle.get('goal')
                        or package.get('selection') != cycle.get('selection')):
                    issue('work_mismatch', 'research_assessment_package',
                          'Assessment package must bind this exact selection and goal.')
                admitted = {(item.get('path'), item.get('sha256'))
                            for item in work.get('evidence', [])}
                facts = package.get('execution_facts')
                if package.get('schema_version', 1) >= 2:
                    if not isinstance(facts, dict):
                        issue('missing_execution_facts', 'research_assessment_package',
                              'Version 2 package requires mechanically verified execution facts.')
                    else:
                        fact_records = {}
                        for name in ['execution_receipt', 'generation_receipt', 'bindings', 'source_provenance']:
                            reference = facts.get(name)
                            if not isinstance(reference, dict) or (reference.get('path'), reference.get('sha256')) not in admitted:
                                issue('execution_fact_mismatch', name,
                                      'Execution fact is not admitted by the research result.')
                                continue
                            path, raw = verify_reference('research_' + name, reference)
                            if raw is not None:
                                try: fact_records[name] = json.loads(raw)
                                except ValueError as error: issue('execution_fact_mismatch', name, str(error))
                        execution = fact_records.get('execution_receipt')
                        provenance = fact_records.get('source_provenance')
                        if execution is not None:
                            for name in ['returncode', 'timed_out', 'protected_changes', 'generated_report_changed']:
                                if facts.get(name) != execution.get(name):
                                    issue('execution_fact_mismatch', name,
                                          'Summary differs from the verified execution receipt.')
                        if provenance is not None:
                            if (facts.get('source_commit') != provenance.get('commit')
                                    or facts.get('source_file_count') != len(provenance.get('source_files', []))):
                                issue('execution_fact_mismatch', 'source_provenance',
                                      'Source summary differs from verified provenance.')
                        outcomes = facts.get('outcomes')
                        if not isinstance(outcomes, list) or not outcomes:
                            issue('missing_execution_facts', 'outcomes', 'No process or trace outcomes were supplied.')
                        else:
                            observed_process = []
                            observed_trace = []
                            for index, outcome in enumerate(outcomes):
                                role = 'research_outcome_' + str(index)
                                reference = outcome.get('evidence')
                                if (not isinstance(reference, dict)
                                        or (reference.get('path'), reference.get('sha256')) not in admitted):
                                    issue('execution_fact_mismatch', role, 'Outcome evidence is not admitted.')
                                    continue
                                path, raw = verify_reference(role, reference)
                                if raw is None: continue
                                try:
                                    data = json.loads(raw)
                                    if outcome.get('kind') == 'process':
                                        valid = (outcome.get('exit_status') == data.get('exit_status')
                                                 and outcome.get('stderr_empty') == (not bool(data.get('stderr'))))
                                        observed_process.append(outcome.get('exit_status') == 0)
                                    elif outcome.get('kind') == 'trace':
                                        checks = data.get('checks', [])
                                        failed = [item.get('name') for item in checks
                                                  if item.get('observed_expected') is not True]
                                        valid = (outcome.get('status') == data.get('status')
                                                 and outcome.get('check_count') == len(checks)
                                                 and outcome.get('failed_checks') == failed)
                                        observed_trace.append(not failed and data.get('status') == 'checked')
                                    else: valid = False
                                    if not valid: raise ValueError('Outcome summary differs from raw evidence.')
                                except (TypeError, ValueError) as error:
                                    issue('execution_fact_mismatch', role, str(error))
                            aggregates = {
                                'process_count': len(observed_process),
                                'trace_count': len(observed_trace),
                                'all_processes_passed': bool(observed_process) and all(observed_process),
                                'all_trace_checks_passed': bool(observed_trace) and all(observed_trace),
                            }
                            for name, expected in aggregates.items():
                                if facts.get(name) != expected:
                                    issue('execution_fact_mismatch', name,
                                          'Aggregate differs from verified outcome evidence.')
                for case in package.get('review', {}).get('cases', []):
                    for index, citation in enumerate(case.get('citations', [])):
                        role = 'research_citation_' + str(case.get('id', 'unknown')) + '_' + str(index)
                        reference = citation.get('evidence')
                        if not isinstance(reference, dict) or (reference.get('path'), reference.get('sha256')) not in admitted:
                            issue('citation_mismatch', role,
                                  'Assessment citation is not admitted by the research result.')
                            continue
                        path, raw = verify_reference(role, reference)
                        if raw is None:
                            continue
                        try:
                            text = raw.decode()
                            quote = citation['quote']
                            locations = citation['occurrences']
                            if (not quote.strip() or not locations
                                    or any(text[item['start']:item['end']] != quote for item in locations)):
                                raise ValueError('Saved quotation does not match its recorded locations.')
                        except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
                            issue('citation_mismatch', role, str(error))
            for index, evidence in enumerate(work.get('evidence', [])):
                # Raw evidence remains hash-verified and auditable outside the model prompt.
                verify_reference('research_evidence_' + str(index), evidence)
    previous = None
    if cycle.get('previous_cycle') is not None:
        previous = load('previous_cycle', cycle['previous_cycle'])
        if previous is not None:
            if previous.get('assessment') is not None:
                load('previous_assessment', previous['assessment'])
            elif previous.get('decision_resolution') is not None:
                decision = load('previous_decision', previous['decision_resolution'])
                if decision is not None and (decision.get('kind') != 'owner_decision_resolution'
                        or decision.get('goal') != previous.get('goal')
                        or decision.get('selection') != previous.get('selection')):
                    issue('decision_mismatch', 'previous_decision', 'Decision must bind the previous selection and goal.')
            else:
                issue('missing_record', 'previous_assessment', 'Previous cycle has neither assessment nor owner decision resolution.')
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
    return {'schema_version': 1, 'purpose': 'selected_research_assessment_context' if research else 'post_build_assessment_context',
            'mode': 'research_assessment' if research else 'cycle_assessment',
            'cycle_id': cycle.get('cycle_id'), 'records': records,
            'missing_or_inconsistent': issues,
            'collection_status': 'needs_inputs' if issues else 'references_verified',
            'previous_assessment_applicable': previous is not None and previous.get('assessment') is not None,
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
