#!/usr/bin/env python3
"""Prepare context, run two lenses and save a structured atom assessment."""
import argparse
import copy
import fcntl
import json
from pathlib import Path
import model_call as calls
from context import assemble
import evidence_catalog

HERE = Path(__file__).resolve().parent
LENS_SCHEMA = {'type': 'object', 'properties': {'analysis': {'type': 'string'}},
               'required': ['analysis'], 'additionalProperties': False}


def historical(root, path):
    packet = calls.read(path)
    if packet.get('mode') != 'historical_contribution_probe':
        raise ValueError('Historical input must explicitly declare historical_contribution_probe.')
    required = {'fixed_goal', 'historical_assignment', 'historical_pre_build_state',
                'completed_build', 'later_interview_background'}
    if not required <= set(packet.get('records', {})):
        raise ValueError('Historical context is missing an original assessment input.')
    for name, record in packet['records'].items():
        source = Path(record['source']['path'])
        source = source if source.is_absolute() else root / source
        if not source.resolve().is_relative_to(root) or calls.digest(source) != record['source']['sha256']:
            raise ValueError('Source changed or outside repository: ' + name)
        if calls.read(source) != record['data']:
            raise ValueError('Embedded source differs from saved file: ' + name)
    return packet


def compact(packet):
    """Remove only the builder's duplicate progress object, preserving a reversible pointer."""
    transport = copy.deepcopy(packet)
    for role, record in transport['records'].items():
        data = record['data']
        if isinstance(data, dict) and 'assessment_input' in data and 'completion' in data:
            progress = data['assessment_input'].get('progress_result')
            if progress is not None and data['completion'].get('progress_result') == progress:
                data['completion']['progress_result'] = {
                    '$ref': '/records/' + role + '/data/assessment_input/progress_result'}
    restored = copy.deepcopy(transport)
    for role, record in restored['records'].items():
        data = record['data']
        if isinstance(data, dict) and 'assessment_input' in data and 'completion' in data:
            pointer = {'$ref': '/records/' + role + '/data/assessment_input/progress_result'}
            if data['completion'].get('progress_result') == pointer:
                data['completion']['progress_result'] = data['assessment_input']['progress_result']
    if restored != packet:
        raise ValueError('Context transport did not round-trip.')
    return transport


def prepare(args):
    root = args.root.resolve()
    packet = historical(root, args.historical_context) if args.historical_context else assemble(root, args.cycle)
    if packet.get('missing_or_inconsistent'):
        raise ValueError('Cycle inputs need attention: ' + json.dumps(packet['missing_or_inconsistent']))
    settings = calls.read(args.settings)
    if set(settings) != {'model', 'reasoning', 'cli', 'timeout_seconds'}:
        raise ValueError('Settings need model, reasoning, cli, timeout_seconds.')
    if not all(isinstance(settings[k], str) and settings[k].strip() for k in ['model', 'reasoning', 'cli']):
        raise ValueError('Model, reasoning and CLI must be supplied.')
    if not isinstance(settings['timeout_seconds'], int) or settings['timeout_seconds'] <= 0:
        raise ValueError('Timeout must be positive seconds.')
    run = args.run.resolve()
    run.mkdir(parents=True, exist_ok=False)
    for name, value in [('context.json', packet), ('transport-context.json', compact(packet)),
                        ('settings.json', settings), ('prompts.json', calls.read(HERE/'prompts.json')),
                        ('final-schema.json', calls.read(HERE/'final-schema.json'))]:
        calls.save(run/name, value)
    catalog = evidence_catalog.build(packet)
    calls.save(run/'evidence-catalog.json', catalog)
    calls.save(run/'final-schema.json', evidence_catalog.final_schema(calls.read(HERE/'final-schema.json'), catalog))
    frozen = ['evidence-catalog.json', 'context.json', 'transport-context.json', 'settings.json', 'prompts.json', 'final-schema.json']
    calls.save(run/'manifest.json', {'files': {n: calls.digest(run/n) for n in frozen},
               'runtime': {p.name: calls.digest(p) for p in HERE.glob('*.py')}})
    calls.save(run/'state.json', {'status': 'prepared', 'stages': {}, 'active_stage': None})
    return run


def execute(run):
    with (run/'.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = calls.read(run/'manifest.json')
        for name, digest in manifest['files'].items():
            if calls.digest(run/name) != digest:
                raise ValueError('Frozen input changed: ' + name)
        for name, digest in manifest['runtime'].items():
            if calls.digest(HERE/name) != digest:
                raise ValueError('Runtime changed: use original code or a new run.')
        state = calls.read(run/'state.json')
        prompts = calls.read(run/'prompts.json')
        settings = calls.read(run/'settings.json')
        packet = calls.read(run/'context.json')
        context = json.dumps(calls.read(run/'transport-context.json'), ensure_ascii=False, separators=(',', ':'))
        catalog = calls.read(run/'evidence-catalog.json')
        answers = {}
        try:
            for stage in ['changed', 'remaining', 'final']:
                calls.SCHEMA = calls.read(run/'final-schema.json') if stage == 'final' else LENS_SCHEMA
                prompt = prompts['common'] + '\n' + prompts[stage] + '\nEVIDENCE PACKET:\n' + context
                if stage == 'final':
                    prompt = (prompts['common'] + '\n' + prompts[stage]
                              + '\nFor evidence fields select only supplied catalog IDs. Do not write locations. '
                              'Select passages supporting each finding, not merely mentioning its subject. '
                              'If evidence is unavailable, say so and use an empty evidence list. '
                              'The catalog represents every leaf of the original packet. Identical passages '
                              'are displayed once; all original locations remain saved.\nEVIDENCE CATALOG:\n'
                              + json.dumps(evidence_catalog.prompt_catalog(catalog), ensure_ascii=False, separators=(',', ':'))
                              + '\nSEPARATE LENS OUTPUTS:\n' + json.dumps(answers, ensure_ascii=False))
                if len(prompt) >= 1048576:
                    raise ValueError('Prompt exceeds CLI character limit; no truncation applied.')
                answers[stage] = calls.one_call(run, stage, prompt, state, settings)
            result = {'schema_version': 1, 'kind': 'atom_assessment',
                      'mode': packet.get('mode', 'cycle_assessment'), 'cycle_id': packet.get('cycle_id'),
                      'context': {'path': str(run/'context.json'), 'sha256': manifest['files']['context.json']},
                      'model_settings': settings, 'lenses': {k: answers[k] for k in ['changed','remaining']},
                      'assessment': answers['final'],
                      'resolved_evidence': evidence_catalog.selected(packet, catalog, answers['final']),
                      'updates_applied': False}
            calls.save(run/'handoff.json', result)
            state.update(status='completed', active_stage=None)
            state.pop('error', None)
        except Exception as error:
            state.update(status='failed', error=str(error))
            raise
        finally:
            calls.save(run/'state.json', state)
        return {'status': 'completed', 'handoff': str(run/'handoff.json'),
                'sha256': calls.digest(run/'handoff.json'), 'completed_calls': len(state['stages'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('start')
    source = start.add_mutually_exclusive_group(required=True)
    source.add_argument('--cycle', type=Path)
    source.add_argument('--historical-context', type=Path)
    start.add_argument('--root', type=Path, required=True)
    start.add_argument('--run', type=Path, required=True)
    start.add_argument('--settings', type=Path, default=HERE/'settings.json')
    start.add_argument('--prepare-only', action='store_true')
    resume = sub.add_parser('resume')
    resume.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    run = prepare(args) if args.command == 'start' else args.run.resolve()
    result = {'status':'prepared', 'run':str(run)} if getattr(args,'prepare_only',False) else execute(run)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
