"""Accumulated captured-case checks; no model calls or product mutations.

The public canary supplies its actual operator observations. Controlled negative
variants below exercise production validators; they are not new domain facts.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def sibling(name):
    spec = importlib.util.spec_from_file_location('canary_'+name,ROOT/'tests'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


captured = sibling('test_requirement_to_atom_readiness')


class OperatorCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        location = os.environ.get('READINESS_CANARY_REPORT')
        if not location:
            raise unittest.SkipTest('Requires the real operator run from run_canary.py; skips cannot authorize activation')
        cls.folder = Path(location).parent
        cls.report = json.loads(Path(location).read_bytes())
        cls.commands = [json.loads((cls.folder/name).read_bytes()) for name in cls.report['commands']]
        cls.outputs = [json.loads(row['stdout']) for row in cls.commands if row['exit'] == 0]
        spec = importlib.util.spec_from_file_location('canary_coverage_kernel',ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/readiness_controller.py')
        cls.k = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.k)
        helper = captured.PackageCapturedStateTests()
        cls.capture = helper.captured()

    def run_existing(self, cls, method):
        """Reuse a real captured regression without accepting its claimed status."""
        if hasattr(cls,'setUpClass'):
            cls.setUpClass()
        case = cls(method)
        result = unittest.TestResult()
        case.run(result)
        self.assertFalse(result.skipped, result.skipped)
        self.assertTrue(result.wasSuccessful(), str(result.errors)+str(result.failures))

    def test_c01_blocked_mysql_first(self):
        state = next(s for s in self.outputs if s.get('queue_count') == 7)
        self.assertEqual(state['status'],'blocked')
        self.assertEqual(state['next_action']['condition_id'],'mysql-query-timeout')
        self.assertTrue(any(r['exit'] == 2 and 'prepare-interview' in r['command'] for r in self.commands))
        self.assertTrue(any(r['exit'] == 2 and 'export-next-atom' in r['command'] for r in self.commands))

    def test_c02_shared_semantic_node(self):
        state = next(s for s in self.outputs if len(s.get('interview_state',{}).get('proposals',[])) == 1)
        self.assertEqual(len(state['interview_state']['proposals']),1)
        self.run_existing(captured.InterviewEngineTests,'test_captured_matching_pair_proposes_only_one_fact')

    def test_c03_owner_only_gap(self):
        graph = copy.deepcopy(captured.EvidenceGraphRuntimeTests.captured_graph)
        graph['conditions'] = [q for q in graph['conditions'] if q['condition_id'] == 'consent-design-undetermined']
        wrapped = {'graph':graph,'graph_sha256':self.k.digest(self.k.canonical(graph)),
                   'queue':graph['conditions'],'next_action':graph['conditions'][0],'status':'needs_owner'}
        _, verdict = self.k.package_module().verdict(self.k,wrapped,self.k.initial_interview_state())
        self.assertEqual(verdict['readiness'],'needs_owner')
        self.assertEqual(verdict['next_action']['condition_id'],'consent-design-undetermined')
        self.run_existing(captured.ExternalRoutingTests,'test_owner_schema_rejects_model_actor_and_extra_choices')

    def test_c04_inaccessible_and_stale_evidence(self):
        node = next(n for n in self.capture['graph']['graph']['nodes'] if n['type'] == 'evidence')
        record = copy.deepcopy(node['record']['evidence'])
        adapter = self.k.evidence_module()
        # Removal of captured objects must fail; age alone must not resurrect it.
        result = adapter.fitness(record,{},record['captured_at_utc'])
        self.assertFalse(result['fit'])
        self.assertFalse(result['accessible_at_capture'])
        record['freshness_rule'] = {'kind':'max-age','max_age_seconds':1}
        result = adapter.fitness(record,{},'2099-01-01T00:00:00+00:00')
        self.assertFalse(result['current'])
        self.assertFalse(result['fit'])

    def test_c05_upstream_integrity(self):
        DescriptionExporterBoundaryTests = sibling('test_requirement_readiness_handoffs').DescriptionExporterBoundaryTests
        for method in ('test_parent_and_leaf_links_are_refused','test_source_change_before_publication_is_refused',
                       'test_hardlink_and_fifo_are_refused','test_duplicate_source_objects_violate_internal_contract'):
            self.run_existing(DescriptionExporterBoundaryTests,method)
        self.run_existing(captured.ReadinessUpstreamTests,'test_upstream_errors_are_explicit_refusals')

    def test_c06_invalid_model_responses(self):
        self.run_existing(captured.InterviewEngineTests,'test_captured_pair_rejection_mutations')
        self.run_existing(captured.InterviewEngineTests,'test_malformed_and_unprepared_submissions_are_retained_rejections')
        self.run_existing(captured.CodexLaunchTests,'test_timeout_terminates_real_external_edge_process')

    def test_c07_cycle_and_unresolved_contradiction(self):
        self.run_existing(captured.EvidenceGraphRuntimeTests,'test_captured_graph_and_dependency_rejection')
        graph = copy.deepcopy(self.capture['graph'])
        state = copy.deepcopy(self.capture['state'])
        fact = next(p for p in state['proposals'] if p['family'] == 'evidence-sufficiency')
        fact['verdict'] = 'contradictory'
        _, verdict = self.k.package_module().verdict(self.k,graph,state)
        self.assertNotEqual(verdict['readiness'],'ready')
        with self.assertRaisesRegex(self.k.Refused,'unresolved non-Plan obligations'):
            self.k.checked_candidates(None,None,graph,state)

    def test_c08_producer_cannot_grade_itself(self):
        self.run_existing(captured.PackageCapturedStateTests,'test_settled_capture_and_removed_evidence_verdicts')
        self.run_existing(captured.InterviewEngineTests,'test_captured_pair_rejection_mutations')
        state = next(s for s in self.outputs if len(s.get('interview_state',{}).get('proposals',[])) == 1)
        self.assertEqual(state['interview_state']['proposals'][0]['verdict'],'inadequate')

    def test_c09_incomplete_blocker_closeout(self):
        adapter = self.k.evidence_module()
        manifest = json.loads((self.folder/'inputs/evidence-0.json').read_bytes())
        source = next(r for r in manifest['source_files'] if r['id'] == 'failure-events')
        raw = Path(source['path']).read_bytes()
        self.assertEqual(self.k.digest(raw),source['sha256'])
        events = [json.loads(line) for line in raw.splitlines()]
        opening = next(e for e in events if e['event_type'] == 'pre_run_blocker_opened')
        upstream = next(s['upstream']['requirements_record'] for s in self.outputs if 'upstream' in s)
        handoff = json.loads((self.folder/'exports/requirements.json').read_bytes())
        upstream = {**upstream,'current_document_sha256':handoff['requirements_document']['sha256']}
        blocker_manifest = {'schema_version':1,'kind':'blockers',
                            'requirements_handoff_sha256':manifest['requirements_handoff_sha256'],
                            'source_files':[source],'requirement_bindings':[], 'conditions':[], 'evidence':[], 'edges':[]}
        # Isolate graph projection from the canonical ledger parser at its declared
        # input seam. These variants are not valid new blocker lifecycle events.
        for status in ('open','fixed-awaiting-verification','verified','closed'):
            parsed = [opening]
            if status != 'open':
                parsed.append({**opening,'event_type':'pre_run_blocker_transitioned','to_status':status})
            result = adapter.build_graph([blocker_manifest],upstream,lambda path,sha:raw,
                                         '2026-09-09T00:00:00+00:00',lambda data:parsed)
            self.assertEqual(bool(result['queue']),status != 'closed')

    def test_c10_ready_does_not_mean_approved(self):
        state = copy.deepcopy(self.capture['state'])
        _, verdict = self.k.package_module().verdict(self.k,self.capture['graph'],state)
        self.assertEqual(verdict['readiness'],'ready')
        self.assertEqual(self.k.package_module().approval(self.k,state,state['compilation']['sequence_sha256']),'not-approved')

    def test_c11_stale_sequence_approval(self):
        self.run_existing(captured.PackageCapturedStateTests,'test_approval_is_separate_and_exact_sequence_bound')

    def test_c12_approved_ordered_export(self):
        state = next(s for s in self.outputs if s.get('exported_atoms') == 2)
        self.assertEqual(state['readiness'],'ready')
        self.assertEqual(state['approval_state'],'approved')
        self.assertEqual([e['ordinal'] for e in state['interview_state']['atom_exports']],[1,2])

    def test_c13_missing_completion_blocks_successor(self):
        self.run_existing(captured.PackageCapturedStateTests,'test_next_release_cannot_skip_a_captured_request')
        self.assertTrue(any(r['exit'] == 2 and 'export-next-atom' in r['command'] and 'no admitted current completion' in r['stderr'] for r in self.commands))

    def test_c14_no_product_work_directory(self):
        request = json.loads((self.folder/'blocked-request.json').read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            product = root/'product'
            product.mkdir()
            request['runtime_boundary'] = {'authorized_root':str(root),'target_repositories':[str(product)],
                                           'product_edit_boundaries':[str(product/'app')]}
            work = product/'forbidden-work'
            with self.assertRaisesRegex(self.k.Refused,'overlaps protected boundary'):
                self.k.boundaries(request,work)
            self.assertFalse(work.exists())

    def test_c15_no_repository_model_context(self):
        self.run_existing(captured.CodexLaunchTests,'test_empty_cwd_and_ancestry')
        self.run_existing(captured.CodexLaunchTests,'test_cli_is_explicit_and_no_shell_or_resume')

    def test_c16_replay_preserves_packages(self):
        green = [s for s in self.outputs if s.get('exported_atoms') == 2]
        self.assertEqual(len(green),2)
        self.assertEqual(green[0],green[1])
        blocked = [s for s in self.outputs if s.get('readiness') == 'blocked' and 'package_manifest_sha256' in s]
        self.assertEqual(len(blocked),2)
        self.assertEqual(blocked[0],blocked[1])


class CanarySafetyTests(unittest.TestCase):
    def test_parent_traversal_is_refused(self):
        path = ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/run_canary.py'
        spec = importlib.util.spec_from_file_location('canary_paths',path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        with self.assertRaisesRegex(m.Refused,'parent traversal'):
            m.regular(ROOT/'tests'/'..'/'tests'/Path(__file__).name)

    def test_report_missing_inventories_cannot_authorize(self):
        path = ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/run_canary.py'
        spec = importlib.util.spec_from_file_location('canary_inventory',path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        # Protocol-only mutations; neither is a new canary execution.
        with tempfile.TemporaryDirectory() as folder:
            report_path = Path(folder).resolve()/'report.json'
            report = {'status':'passed','activation_allowed':True,'tested_sources':[], 'artifacts':[]}
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(m.Refused,'source inventory'):
                m.verify_report(report_path)
            report['tested_sources'] = m.tested_sources()
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(m.Refused,'artifact inventory'):
                m.verify_report(report_path)

    def test_incomplete_or_skipped_coverage_never_activates(self):
        import xml.etree.ElementTree as ET
        path = ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/run_canary.py'
        spec = importlib.util.spec_from_file_location('canary_gate',path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        suite = ET.Element('testsuite')
        for i,name in enumerate(m.CASE_NAMES,1):
            ET.SubElement(suite,'testcase',name=f'test_c{i:02d}_{name}')
        good = ET.tostring(suite)
        self.assertEqual(len(m.checked_suite(good)['integration_cases']),16)
        self.assertEqual(len(m.checked_suite(good)['requirements']),7)
        for tag in ('skipped','failure','error'):
            broken = ET.fromstring(good)
            ET.SubElement(broken[0],tag)
            with self.assertRaises(m.Refused):
                m.checked_suite(ET.tostring(broken))
        suite.remove(suite[0])
        with self.assertRaises(m.Refused):
            m.checked_suite(ET.tostring(suite))

    def test_unknown_request_is_refused_before_output(self):
        path = ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/run_canary.py'
        spec = importlib.util.spec_from_file_location('canary_safety',path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            request = root/'request.json'
            request.write_text('{}\n')
            with self.assertRaises(m.Refused):
                m.run(request,root/'output')
            self.assertFalse((root/'output').exists())

    def test_duplicate_json_is_refused(self):
        path = ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/run_canary.py'
        spec = importlib.util.spec_from_file_location('canary_json',path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        with self.assertRaises(m.Refused):
            m.decode(b'{"schema_version":1,"schema_version":1}')
