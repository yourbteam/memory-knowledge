"""Mechanical contract checks; stub records do not establish semantic agreement quality."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def completed(tmp_path):
    helpers = load('complete_test_helpers', 'tests/test_description_machinery.py')
    args = helpers._span_fixture(tmp_path)
    helpers.from_intent.drive(*args)
    helpers._agreement_stub(args[1], 'q8')
    assert helpers.from_intent.drive(*args)['status'] == 'complete'
    exporter = load('complete_exporter', 'skills/description-machinery/scripts/export_handoff.py')
    adapter = load('complete_adapter', 'skills/requirement-to-atom-readiness-machinery/scripts/description_adapter.py')
    return helpers, args, exporter, adapter


def frozen_import(completed):
    _, args, exporter, adapter = completed
    handoff, evidence = exporter.validate_run(args[1])
    evidence.verify_unchanged()
    frozen = {str(p): raw for p, raw in evidence.files.items()}
    def read(path, expected):
        raw = frozen[str(path)]
        if exporter.digest(raw) != expected:
            raise ValueError('frozen hash mismatch')
        return raw
    producer = (ROOT / 'skills/description-machinery/from_intent.py').read_bytes()
    return handoff, frozen, lambda h: adapter.verify(h, read, exporter, producer)


def reseal(exporter, handoff):
    handoff['handoff_sha256'] = exporter.digest(exporter.canonical(
        {key: value for key, value in handoff.items() if key != 'handoff_sha256'}))


def test_complete_semantic_handoff_replays_without_original_sources(completed):
    _, args, exporter, _ = completed
    handoff, frozen, verify = frozen_import(completed)
    assert handoff['contract_version'] == 2
    assert len(handoff['evidence_records']) == 6
    first = verify(handoff)
    args[0].unlink()
    args[3].unlink()
    assert verify(handoff) == first
    assert first['reader_count'] == 16
    from jsonschema import Draft202012Validator
    Draft202012Validator(exporter.handoff_schema()).validate(handoff)


def test_each_bound_completion_member_is_required(completed):
    _, _, exporter, _ = completed
    handoff, frozen, verify = frozen_import(completed)
    for member in handoff['evidence_records']:
        before = frozen.pop(member['path'])
        with pytest.raises((ValueError, KeyError)):
            verify(handoff)
        frozen[member['path']] = before
        changed = copy.deepcopy(handoff)
        changed['evidence_records'].remove(member)
        reseal(exporter, changed)
        with pytest.raises(ValueError):
            verify(changed)


@pytest.mark.parametrize('mutation', ['vote', 'decision', 'catalog', 'reader', 'producer'])
def test_resealed_semantic_corruption_is_rejected(completed, mutation):
    _, args, exporter, _ = completed
    handoff, frozen, verify = frozen_import(completed)
    if mutation == 'producer':
        handoff['producer_source_sha256'] = '0' * 64
    else:
        suffix = {'vote':'agreement-q8/look-1/answer.json',
                  'decision':'agreement-q8/decision.json',
                  'catalog':'source-passages.json', 'reader':'look-1/q8.json'}[mutation]
        # Resolve the actual named member, not an invented directory spelling.
        if mutation == 'vote':
            path = next(p for p in frozen if '/agreement-q8/' in p and p.endswith('/answer.json'))
        else:
            path = str(args[1] / suffix)
        value = json.loads(frozen[path])
        if mutation == 'vote':
            value['agreement_verdict'] = 'different'
        elif mutation == 'decision':
            value['binding'] = '0' * 64
        elif mutation == 'catalog':
            value.pop()
        else:
            value['quote'] = 'Internal choices are delegated;'
        frozen[path] = json.dumps(value).encode()
        for member in handoff['evidence_records'] + handoff['reader_records']:
            if member['path'] == path:
                member['sha256'] = exporter.digest(frozen[path])
                if mutation == 'reader':
                    member['answer_sha256'] = exporter.digest(exporter.canonical(value))
    reseal(exporter, handoff)
    with pytest.raises(ValueError):
        verify(handoff)


def test_trimmed_restriction_cannot_complete(tmp_path):
    helpers = load('trimmed_test_helpers', 'tests/test_description_machinery.py')
    intent, work = tmp_path / 'intent.md', tmp_path / 'work'
    intent.write_text('Select the current tour discount. Never fall back to another tour.')
    helpers.from_intent.drive(intent, work, [])
    helpers._fill_look(work, quote='Select the current tour discount.', quoted_from=intent)
    result = helpers.from_intent.drive(intent, work, [])
    assert result['stopped'] == 'incomplete source passage'
    assert not (work / 'description.md').exists()


def test_catalog_preserves_blockquote_restrictions():
    producer = load('catalog_producer', 'skills/description-machinery/from_intent.py')
    text = '> Select this code.\n>\n> Never fall back.\n\nAnother source unit.'
    assert producer.source_passages({'source': text}) == [
        {'quoted_from':'source', 'quote':'> Select this code.\n>\n> Never fall back.'},
        {'quoted_from':'source', 'quote':'Another source unit.'}]


@pytest.mark.parametrize('version', [1, 2])
def test_historical_completion_contracts_remain_exportable(completed, version):
    # Deliberate mechanical compatibility derivative, not a historical model run.
    helpers, args, exporter, _ = completed
    state_path = args[1] / 'input-state.json'
    state = json.loads(state_path.read_text())
    state['contract'] = version
    helpers._write_json(state_path, state)
    records = [helpers.from_intent._records(args[1] / f'look-{seat}') for seat in (1, 2)]
    if version == 1:
        records[1]['q8'] = dict(records[0]['q8'])
        helpers._write_json(args[1] / 'look-2/q8.json', records[1]['q8'])
    else:
        citations = [{k: seat['q8'][k] for k in ('quote', 'quoted_from')} for seat in records]
        sources = {str(args[0]):args[0].read_text(), str(args[3]):args[3].read_text()}
        packet = helpers.from_intent._agreement_packet(helpers.from_intent.QUESTIONS[7], citations, state, sources)
        helpers._write_json(args[1] / 'agreement-q8/question.json', packet)
        helpers._agreement_stub(args[1], 'q8')
        votes = [json.loads((args[1] / f'agreement-q8/seat-{seat}/answer.json').read_text()) for seat in (1, 2)]
        helpers._write_json(args[1] / 'agreement-q8/decision.json', {
            'status':'agreed', 'binding':helpers.from_intent._digest(packet), 'votes':votes})
    answers = [(q, [{k:seat[q['id']][k] for k in ('quote','quoted_from')} for seat in records])
               for q in helpers.from_intent.QUESTIONS]
    (args[1] / 'description.md').write_bytes(helpers.from_intent._render_description(str(args[0]), answers))
    handoff, _, verify = frozen_import(completed)
    assert handoff['contract_version'] == version
    assert verify(handoff)['reader_count'] == 16
