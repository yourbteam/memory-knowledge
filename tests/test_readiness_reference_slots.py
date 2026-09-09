"""Captured live judgments; only fixed reference serialization changes."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / 'skills/requirement-to-atom-readiness-machinery/scripts'
CAPTURE = ROOT / 'tests/fixtures/readiness-transport/slots'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

k = module('slots_kernel', SCRIPTS / 'readiness_controller.py')
m = module('slots_transport', SCRIPTS / 'model_interview.py')

class ReferenceSlotsTests(unittest.TestCase):
    def capture(self, number, seat=1):
        launch = CAPTURE / ('candidate-%02d-launch' % number)
        schema = json.loads((launch / 'plan.json').read_bytes())['seats'][seat-1]['response_schema']
        attempt = launch / ('seat-%d/attempt-1' % seat)
        return schema, json.loads((attempt / 'response.json').read_bytes()), attempt

    def wire(self, schema, raw):
        result = copy.deepcopy(raw)
        for name, identities in m.reference_slots(k, schema).items():
            values = raw[name] if name == 'evidence_ids' else [q['evidence_id'] for q in raw[name]]
            # Never repair the failed capture or manufacture missing evidence.
            if len(values) != len(set(values)) or set(values) != set(identities):
                raise ValueError('captured references are incomplete or duplicated')
            result[name] = {value: value for value in values}
        return result

    def test_captured_failure_stays_rejected(self):
        schema, raw, _ = self.capture(5)
        old = module(
            'slots_old_transport', ROOT / 'tests/fixtures/readiness-transport/old_slots_transport.py')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            old.assemble_response(k, raw, schema, 'seat-1')
        with self.assertRaises(ValueError):
            self.wire(schema, raw)
        with self.assertRaises(ValueError):
            m.assemble_response(k, raw, schema, 'seat-1')

    def test_captured_successes_preserve_all_judgments_and_references(self):
        from jsonschema import Draft202012Validator
        for number in (3, 4):
            for seat in (1, 2):
                with self.subTest(candidate=number, seat=seat):
                    schema, raw, attempt = self.capture(number, seat)
                    wire = self.wire(schema, raw)
                    provider = m.provider_schema(m.compact_schema(k, schema))
                    Draft202012Validator(provider).validate(wire)
                    actual = m.assemble_response(k, wire, schema, 'seat-%d' % seat)
                    expected = json.loads((attempt / 'assembled-response.json').read_bytes())
                    for name in ('quotes', 'evidence_ids'):
                        self.assertEqual(sorted(actual[name], key=str), sorted(expected[name], key=str))
                        del actual[name]; del expected[name]
                    self.assertEqual(actual, expected)

    def test_provider_and_local_schema_reject_missing_extra_and_substituted_slots(self):
        from jsonschema import Draft202012Validator
        schema, raw, _ = self.capture(4)
        valid = self.wire(schema, raw)
        validator = Draft202012Validator(m.provider_schema(m.compact_schema(k, schema)))
        for name in ('evidence_ids', 'quotes'):
            for defect in ('missing', 'extra', 'substituted'):
                with self.subTest(field=name, defect=defect):
                    bad = copy.deepcopy(valid)
                    identity = next(iter(bad[name]))
                    if defect == 'missing': del bad[name][identity]
                    if defect == 'extra': bad[name]['foreign'] = 'foreign'
                    if defect == 'substituted': bad[name][identity] = 'requirement-7'
                    self.assertTrue(list(validator.iter_errors(bad)))
                    with self.assertRaises(ValueError):
                        m.assemble_response(k, bad, schema, 'seat-1')

    def test_subset_contract_is_not_expanded(self):
        schema, _, _ = self.capture(4)
        schema['properties']['evidence_ids']['minItems'] = 1
        self.assertEqual(m.reference_slots(k, schema), {})
        self.assertEqual(m.compact_schema(k, schema)['properties']['evidence_ids']['type'], 'array')
