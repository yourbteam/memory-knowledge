import json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ReadinessSchemaTests(unittest.TestCase):
    def test_schema_cli(self):
        path=ROOT/"skills/requirement-to-atom-readiness-machinery/scripts/readiness_controller.py"
        command=[sys.executable,str(path),"schema"]
        first=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(first.returncode,0)
        self.assertEqual(first.stdout,subprocess.check_output(command,text=True))
        schema=json.loads(first.stdout)
        self.assertEqual(schema,json.loads((ROOT/"skills/requirement-to-atom-readiness-machinery/schemas/readiness-request.schema.json").read_text()))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(len(schema["properties"]["machinery_contracts"]["allOf"]),12)
        self.assertEqual(subprocess.run(command+[str(path)],capture_output=True).returncode,2)

class ReadinessKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec=importlib.util.spec_from_file_location('kernel',ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/readiness_controller.py')
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
    def test_duplicate_and_nonfinite_json(self):
        for raw in [b'{"a":1,"a":2}',b'{"a":NaN}',b'\xef\xbb\xbf{}']:
            with self.assertRaises(self.module.Refused):self.module.decode(raw,'test')
    def test_canonical_chain(self):
        m=self.module;events=m.chain([('run_started',{'request_sha256':'a'*64}),('input_admitted',{'identity':'captured'})])
        self.assertEqual(events[0]['previous'],m.GENESIS)
        self.assertEqual(events[1]['previous'],events[0]['sha256'])
        self.assertEqual(events,m.chain([('run_started',{'request_sha256':'a'*64}),('input_admitted',{'identity':'captured'})]))
    def test_tip_guard(self):
        self.module.require_tip('a'*64,'a'*64)
        for bad in [True,None,'a'*64+'\n','b'*64]:
            with self.assertRaises(self.module.Refused):self.module.require_tip(bad,'a'*64)
    def test_path_contract(self):
        for path in ['relative','/a/../b','/a//b','/a/']:
            with self.assertRaises(self.module.Refused):self.module.absolute(path)


class ReadinessUpstreamTests(ReadinessKernelTests):
    def test_adapter_sources_are_bound_to_controller_identity(self):
        from unittest.mock import patch
        m = self.module
        expected = m.adapter_code_sha256()
        original = m.read_file
        def changed(path, limit):
            raw = original(path, limit)
            return raw + b" " if Path(path).name == "requirements_adapter.py" else raw
        with patch.object(m, "read_file", side_effect=changed):
            self.assertNotEqual(m.adapter_code_sha256(), expected)

    def test_upstream_errors_are_explicit_refusals(self):
        from unittest.mock import patch
        m = self.module
        with patch.object(m, "_verify_upstreams", side_effect=ValueError("missing sealed evidence")):
            with self.assertRaisesRegex(m.Refused, "upstream verification refused.*missing sealed evidence"):
                m.verify_upstreams({}, None)

    def test_installed_runtime_is_fixed_local_code(self):
        files, runtime, *_ = self.module.upstream_modules()
        self.assertEqual(files["requirements-exporter"], ROOT / "skills/requirements-machinery/scripts/cover.py")
        self.assertEqual(set(runtime), {p.name for p in files["requirements-exporter"].parent.glob("*.py")})
        self.assertEqual(runtime["cover.py"], files["requirements-exporter"].read_bytes())


class EvidenceGraphSchemaTests(unittest.TestCase):
    def test_closed_evidence_and_graph_cli(self):
        from jsonschema import Draft202012Validator
        module=ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/evidence_adapter.py'
        for name,file in [('evidence','evidence-manifest.schema.json'),('graph','graph.schema.json')]:
            command=[sys.executable,str(module),'schema',name]
            raw=subprocess.check_output(command,text=True)
            self.assertEqual(raw,subprocess.check_output(command,text=True))
            schema=json.loads(raw);Draft202012Validator.check_schema(schema)
            self.assertEqual(schema,json.loads((module.parents[1]/'schemas'/file).read_text()))
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(len(schema['$defs']['node']['oneOf']),6)
            self.assertEqual(subprocess.run(command+[str(module)],capture_output=True).returncode,2)


class EvidenceGraphRuntimeTests(unittest.TestCase):
    # Captured through the real returning-discount start path, 2026-09-08 UTC.
    captured_graph = {'conditions': [{'blocking_class': 'mandatory-evidence', 'condition_id': 'mysql-query-timeout', 'dependency_layer': 0, 'node_id': 'condition-caf0c95602feb1b3f3a91a8e', 'recovery_condition': 'A declared read-only probe reaches the configured MySQL server and retains a real query result or a newly classified terminal access outcome.', 'requirement_ordinal': 1, 'source_ordinal': 2}, {'blocking_class': 'mandatory-evidence', 'condition_id': 'missing-real-discount-cases', 'dependency_layer': 0, 'node_id': 'condition-e0cb7d46691df738fc200700', 'recovery_condition': 'Immutable real eligible and rejection cases are admitted with provenance and content hashes.', 'requirement_ordinal': 1, 'source_ordinal': 3}, {'blocking_class': 'mandatory-evidence', 'condition_id': 'external-temporary-evidence', 'dependency_layer': 0, 'node_id': 'condition-93632efc22dc675b28b72885', 'recovery_condition': 'All atom evidence and ledgers are snapshotted into run-owned immutable storage and rehash successfully on replay.', 'requirement_ordinal': 1, 'source_ordinal': 5}, {'blocking_class': 'mandatory-evidence', 'condition_id': 'open-atom-blocker', 'dependency_layer': 0, 'node_id': 'condition-da28c11de7420da53d5d8fe6', 'recovery_condition': 'Every atom-linked blocker is verified and closed or remains a blocking dependency before completion can be derived.', 'requirement_ordinal': 1, 'source_ordinal': 6}, {'blocking_class': 'semantic', 'condition_id': 'evaluator-self-trust', 'dependency_layer': 0, 'node_id': 'condition-6992ed11f122b95ee315fa8e', 'recovery_condition': 'Verification is redesigned so an independent evaluator derives every criterion from raw observations with candidate outcome and self-reported metrics withheld.', 'requirement_ordinal': 2, 'source_ordinal': 4}, {'blocking_class': 'owner', 'condition_id': 'consent-design-undetermined', 'dependency_layer': 0, 'node_id': 'condition-327d2eccde9202c2f91bb6de', 'recovery_condition': 'The owner records the cross-tour consent, retention, and matching decision.', 'requirement_ordinal': 1, 'source_ordinal': 0}, {'blocking_class': 'owner', 'condition_id': 'aws-probe-scope-expansion', 'dependency_layer': 0, 'node_id': 'condition-7aa43af5554f167f7f00c5b9', 'recovery_condition': 'The owner authorizes or rejects scope expansion to create the checked-in zero-input AWS inventory probe.', 'requirement_ordinal': 1, 'source_ordinal': 1}], 'edges': [{'source': 'req-4d1c8689e6cfbe2f', 'target': 'condition-327d2eccde9202c2f91bb6de', 'type': 'governed-by'}, {'source': 'req-4d1c8689e6cfbe2f', 'target': 'condition-7aa43af5554f167f7f00c5b9', 'type': 'governed-by'}, {'source': 'req-7d434c081c6d4413', 'target': 'condition-327d2eccde9202c2f91bb6de', 'type': 'governed-by'}, {'source': 'req-a85e221564f8558a', 'target': 'condition-327d2eccde9202c2f91bb6de', 'type': 'governed-by'}, {'source': 'req-b260643af25432ba', 'target': 'condition-7aa43af5554f167f7f00c5b9', 'type': 'governed-by'}, {'source': 'req-e51c9757aeaa8d3d', 'target': 'condition-327d2eccde9202c2f91bb6de', 'type': 'governed-by'}, {'source': 'req-e51c9757aeaa8d3d', 'target': 'condition-7aa43af5554f167f7f00c5b9', 'type': 'governed-by'}, {'source': 'req-2b531c2ceab9c0bd', 'target': 'condition-da28c11de7420da53d5d8fe6', 'type': 'verified-by'}, {'source': 'req-4d1c8689e6cfbe2f', 'target': 'condition-93632efc22dc675b28b72885', 'type': 'verified-by'}, {'source': 'req-4d1c8689e6cfbe2f', 'target': 'condition-caf0c95602feb1b3f3a91a8e', 'type': 'verified-by'}, {'source': 'req-4d1c8689e6cfbe2f', 'target': 'condition-da28c11de7420da53d5d8fe6', 'type': 'verified-by'}, {'source': 'req-4d1c8689e6cfbe2f', 'target': 'condition-e0cb7d46691df738fc200700', 'type': 'verified-by'}, {'source': 'req-7d434c081c6d4413', 'target': 'condition-caf0c95602feb1b3f3a91a8e', 'type': 'verified-by'}, {'source': 'req-7d434c081c6d4413', 'target': 'condition-e0cb7d46691df738fc200700', 'type': 'verified-by'}, {'source': 'req-a85e221564f8558a', 'target': 'condition-6992ed11f122b95ee315fa8e', 'type': 'verified-by'}, {'source': 'req-a85e221564f8558a', 'target': 'condition-93632efc22dc675b28b72885', 'type': 'verified-by'}, {'source': 'req-a85e221564f8558a', 'target': 'condition-caf0c95602feb1b3f3a91a8e', 'type': 'verified-by'}, {'source': 'req-a85e221564f8558a', 'target': 'condition-da28c11de7420da53d5d8fe6', 'type': 'verified-by'}, {'source': 'req-a85e221564f8558a', 'target': 'condition-e0cb7d46691df738fc200700', 'type': 'verified-by'}, {'source': 'req-b260643af25432ba', 'target': 'condition-93632efc22dc675b28b72885', 'type': 'verified-by'}, {'source': 'req-b260643af25432ba', 'target': 'condition-caf0c95602feb1b3f3a91a8e', 'type': 'verified-by'}, {'source': 'req-b260643af25432ba', 'target': 'condition-e0cb7d46691df738fc200700', 'type': 'verified-by'}, {'source': 'req-e17b44a659f36a19', 'target': 'condition-6992ed11f122b95ee315fa8e', 'type': 'verified-by'}, {'source': 'req-e17b44a659f36a19', 'target': 'condition-93632efc22dc675b28b72885', 'type': 'verified-by'}, {'source': 'req-e17b44a659f36a19', 'target': 'condition-da28c11de7420da53d5d8fe6', 'type': 'verified-by'}, {'source': 'req-e17b44a659f36a19', 'target': 'condition-e0cb7d46691df738fc200700', 'type': 'verified-by'}, {'source': 'req-e51c9757aeaa8d3d', 'target': 'condition-6992ed11f122b95ee315fa8e', 'type': 'verified-by'}, {'source': 'req-e51c9757aeaa8d3d', 'target': 'condition-93632efc22dc675b28b72885', 'type': 'verified-by'}, {'source': 'req-e51c9757aeaa8d3d', 'target': 'condition-caf0c95602feb1b3f3a91a8e', 'type': 'verified-by'}, {'source': 'req-e51c9757aeaa8d3d', 'target': 'condition-da28c11de7420da53d5d8fe6', 'type': 'verified-by'}], 'nodes': [{'id': 'condition-327d2eccde9202c2f91bb6de', 'record': {'answer': None, 'answer_contract': 'owner-only-pending', 'owner': 'owner', 'question': 'The owner records the cross-tour consent, retention, and matching decision.'}, 'type': 'authority_decision'}, {'id': 'condition-6992ed11f122b95ee315fa8e', 'record': {'execution_route': 'Verification is redesigned so an independent evaluator derives every criterion from raw observations with candidate outcome and self-reported metrics withheld.', 'independence_rule': 'unassessed', 'observable': "| 6 | Evaluation and final assessment can trust the candidate's own verdict | Critical | A candidate can effectively grade itself |", 'rejection_cases': [], 'status': 'blocked', 'success_cases': []}, 'type': 'verification'}, {'id': 'condition-7aa43af5554f167f7f00c5b9', 'record': {'answer': None, 'answer_contract': 'owner-only-pending', 'owner': 'owner', 'question': 'The owner authorizes or rejects scope expansion to create the checked-in zero-input AWS inventory probe.'}, 'type': 'authority_decision'}, {'id': 'condition-93632efc22dc675b28b72885', 'record': {'execution_route': 'All atom evidence and ledgers are snapshotted into run-owned immutable storage and rehash successfully on replay.', 'independence_rule': 'unassessed', 'observable': '| 7 | Atom evidence is externally referenced and later ledgers are temporary | High | A completed atom can become unreadable after temporary files disappear |', 'rejection_cases': [], 'status': 'blocked', 'success_cases': []}, 'type': 'verification'}, {'id': 'condition-caf0c95602feb1b3f3a91a8e', 'record': {'execution_route': 'A declared read-only probe reaches the configured MySQL server and retains a real query result or a newly classified terminal access outcome.', 'independence_rule': 'unassessed', 'observable': 'PDO reached configured host with host network access and returned SQLSTATE HY000 2002 Operation timed out; no query result was received.', 'rejection_cases': [], 'status': 'blocked', 'success_cases': []}, 'type': 'verification'}, {'id': 'condition-da28c11de7420da53d5d8fe6', 'record': {'execution_route': 'Every atom-linked blocker is verified and closed or remains a blocking dependency before completion can be derived.', 'independence_rule': 'unassessed', 'observable': '| 8 | Atom completion does not reconcile its blocker lifecycle | High | Work can be declared complete with unresolved blocker records |', 'rejection_cases': [], 'status': 'blocked', 'success_cases': []}, 'type': 'verification'}, {'id': 'condition-e0cb7d46691df738fc200700', 'record': {'execution_route': 'Immutable real eligible and rejection cases are admitted with provenance and content hashes.', 'independence_rule': 'unassessed', 'observable': '`Atom 1: Tour discount-rule resolver` had already been approved before a real eligible and rejection case was frozen; the configured MySQL read then timed out, and the blocker states that implementation could not start without violating the no-synthetic-case rule.', 'rejection_cases': [], 'status': 'blocked', 'success_cases': []}, 'type': 'verification'}, {'id': 'req-2b531c2ceab9c0bd', 'record': {'disposition': 'blocked', 'exact_text': 'The owner receives the readiness report and decision queue to supply missing decisions and approve or reject the atom sequence. Evidence, research, and planning machinery receive only their provenance-bound gap or planning inputs, and Atom Building Machinery receives only owner-approved ordered atom envelopes, with no model or controller authorized to grant approval or begin implementation.', 'maturity': 'unassessed', 'ordinal': 4, 'requirement_id': 'req-2b531c2ceab9c0bd', 'source_anchors': [{'piece_id': 'p-0001', 'quote': 'The owner receives the readiness report and decision queue to supply missing decisions and approve or reject the atom sequence; evidence, research, and planning machinery receive only their provenance-bound gap or planning inputs; and Atom Building Machinery receives only owner-approved ordered atom envelopes, with no model or controller authorized to grant approval or begin implementation. _Source: `/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ ## q3 — What is it given to work from, and where does each of those come from?', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}, {'piece_id': 'p-0001', 'quote': 'The owner receives the readiness report and decision queue to supply missing decisions and approve or reject the atom sequence; evidence, research, and planning machinery receive only their provenance-bound gap or planning inputs; and Atom Building Machinery receives only owner-approved ordered atom envelopes, with no model or controller authorized to grant approval or begin implementation.', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]}, 'type': 'requirement'}, {'id': 'req-4d1c8689e6cfbe2f', 'record': {'disposition': 'blocked', 'exact_text': 'The machinery must freeze and hash its inputs; map every requirement to its evidence, dependencies, authority, and verification obligations; identify missing, stale, inaccessible, or contradictory links; dispatch only bounded deterministic probes or code-controlled one-question interviews to resolve them; preserve every transition in a resumable ledger; and compile dependency-ordered atom envelopes only after every readiness gate passes.', 'maturity': 'unassessed', 'ordinal': 1, 'requirement_id': 'req-4d1c8689e6cfbe2f', 'source_anchors': [{'piece_id': 'p-0001', 'quote': 'The machinery must freeze and hash its inputs; map every requirement to its evidence, dependencies, authority, and verification obligations; identify missing, stale, inaccessible, or contradictory links; dispatch only bounded deterministic probes or code-controlled one-question interviews to resolve them; preserve every transition in a resumable ledger; and compile dependency-ordered atom envelopes only after every readiness gate passes. _Source: `/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ ## q5 — What must it produce, and what does that thing look like?', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}, {'piece_id': 'p-0001', 'quote': 'The machinery must freeze and hash its inputs; map every requirement to its evidence, dependencies, authority, and verification obligations; identify missing, stale, inaccessible, or contradictory links; dispatch only bounded deterministic probes or code-controlled one-question interviews to resolve them; preserve every transition in a resumable ledger; and compile dependency-ordered atom envelopes only after every readiness gate passes.', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]}, 'type': 'requirement'}, {'id': 'req-7d434c081c6d4413', 'record': {'disposition': 'blocked', 'exact_text': 'Before implementation begins, the owner can determine whether a feature goal has enough provenance-bound evidence, resolved decisions, mapped dependencies, and complete requirements to be decomposed into safe implementation atoms, or otherwise receive the exact next unresolved item without speculative work beginning.', 'maturity': 'unassessed', 'ordinal': 6, 'requirement_id': 'req-7d434c081c6d4413', 'source_anchors': [{'piece_id': 'p-0001', 'quote': 'This machinery makes it possible for the owner, before implementation begins, to determine whether a feature goal has enough provenance-bound evidence, resolved decisions, mapped dependencies, and complete requirements to be decomposed into safe implementation atoms, or otherwise to receive the exact next unresolved item without speculative work beginning. _Source: `/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ ## q2 — Who reads or receives what it produces, and what do they do with it?', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}, {'piece_id': 'p-0001', 'quote': 'This machinery makes it possible for the owner, before implementation begins, to determine whether a feature goal has enough provenance-bound evidence, resolved decisions, mapped dependencies, and complete requirements to be decomposed into safe implementation atoms, or otherwise to receive the exact next unresolved item without speculative work beginning.', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]}, 'type': 'requirement'}, {'id': 'req-a85e221564f8558a', 'record': {'disposition': 'blocked', 'exact_text': 'The controller may declare readiness only when deterministic checks confirm that every requirement has a provenance-bound disposition, all dependencies and contradictions are resolved, all mandatory evidence is current and reproducible, the package passes schema, integrity, and replay validation, and every proposed atom has explicit verification and stop conditions. `needs_owner` and `blocked` are valid resumable run outcomes but never readiness, and only the owner may approve the resulting atom sequence and authorize Atom Building Machinery to begin.', 'maturity': 'unassessed', 'ordinal': 2, 'requirement_id': 'req-a85e221564f8558a', 'source_anchors': [{'piece_id': 'p-0001', 'quote': 'The controller may declare readiness only when deterministic checks confirm that every requirement has a provenance-bound disposition, all dependencies and contradictions are resolved, all mandatory evidence is current and reproducible, the package passes schema, integrity, and replay validation, and every proposed atom has explicit verification and stop conditions; `needs_owner` and `blocked` are valid resumable run outcomes but never readiness, and only the owner may approve the resulting atom sequence and authorize Atom Building Machinery to begin. _Source: `/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ ## q7 — What must it never do, and what makes it stop rather than guess?', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}, {'piece_id': 'p-0001', 'quote': 'The controller may declare readiness only when deterministic checks confirm that every requirement has a provenance-bound disposition, all dependencies and contradictions are resolved, all mandatory evidence is current and reproducible, the package passes schema, integrity, and replay validation, and every proposed atom has explicit verification and stop conditions; `needs_owner` and `blocked` are valid resumable run outcomes but never readiness, and only the owner may approve the resulting atom sequence and authorize Atom Building Machinery to begin.', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]}, 'type': 'requirement'}, {'id': 'req-b260643af25432ba', 'record': {'disposition': 'blocked', 'exact_text': 'The machinery receives a source-quoted description from Description Machinery; enumerated, source-linked requirements from Requirements Machinery; repository, project, environment, and authority boundaries from task intake and owner decisions; immutable code, database, infrastructure, runtime, and failure evidence from deterministic probes or Info Intake; current machinery contracts from `memory-knowledge`; and execution telemetry and blocker history from controller ledgers and the Blocker Catalog, with every input carrying its origin, identity, and content hash.', 'maturity': 'unassessed', 'ordinal': 7, 'requirement_id': 'req-b260643af25432ba', 'source_anchors': [{'piece_id': 'p-0001', 'quote': 'The machinery receives a source-quoted description from Description Machinery; enumerated, source-linked requirements from Requirements Machinery; repository, project, environment, and authority boundaries from task intake and owner decisions; immutable code, database, infrastructure, runtime, and failure evidence from deterministic probes or Info Intake; current machinery contracts from `memory-knowledge`; and execution telemetry and blocker history from controller ledgers and the Blocker Catalog, with every input carrying its origin, identity, and content hash. _Source: `/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ ## q4 — What must it do with what it is given?', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]}, 'type': 'requirement'}, {'id': 'req-e17b44a659f36a19', 'record': {'disposition': 'blocked', 'exact_text': 'The machinery produces a versioned, hash-bound readiness package containing a machine-readable readiness ledger, a requirement-to-evidence-and-dependency graph, and a verdict with reasons for every requirement. While blocked it also contains the ordered unresolved-evidence and owner-decision queue, and when ready it instead contains dependency-ordered, independently testable atom envelopes defining scope, inputs, boundaries, prerequisites, acceptance checks, verification paths, and stop conditions, together with a human-readable report and replay receipt.', 'maturity': 'unassessed', 'ordinal': 5, 'requirement_id': 'req-e17b44a659f36a19', 'source_anchors': [{'piece_id': 'p-0001', 'quote': 'The machinery produces a versioned, hash-bound readiness package containing a machine-readable readiness ledger, a requirement-to-evidence-and-dependency graph, and a verdict with reasons for every requirement; while blocked it also contains the ordered unresolved-evidence and owner-decision queue, and when ready it instead contains dependency-ordered, independently testable atom envelopes defining scope, inputs, boundaries, prerequisites, acceptance checks, verification paths, and stop conditions, together with a human-readable report and replay receipt. _Source: `/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ ## q6 — How does anybody tell it is done, and who decides?', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}, {'piece_id': 'p-0001', 'quote': 'The machinery produces a versioned, hash-bound readiness package containing a machine-readable readiness ledger, a requirement-to-evidence-and-dependency graph, and a verdict with reasons for every requirement; while blocked it also contains the ordered unresolved-evidence and owner-decision queue, and when ready it instead contains dependency-ordered, independently testable atom envelopes defining scope, inputs, boundaries, prerequisites, acceptance checks, verification paths, and stop conditions, together with a human-readable report and replay receipt.', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]}, 'type': 'requirement'}, {'id': 'req-e51c9757aeaa8d3d', 'record': {'disposition': 'blocked', 'exact_text': 'The machinery must never invent a requirement, fact, dependency, evidence item, or owner decision; infer legal, business, permission, or promotion authority; inspect an undeclared source; mutate a product system; execute an implementation atom; or allow a model to control identity, ordering, state, validation, or pass/fail decisions. It must stop with an explicit reason and the single next required question whenever an input is missing, inaccessible, stale, unverifiable, provenance-free, or contradictory, model outputs are invalid or disagree beyond deterministic rules, required authority is absent, or any readiness invariant fails.', 'maturity': 'unassessed', 'ordinal': 3, 'requirement_id': 'req-e51c9757aeaa8d3d', 'source_anchors': [{'piece_id': 'p-0001', 'quote': 'The machinery must never invent a requirement, fact, dependency, evidence item, or owner decision; infer legal, business, permission, or promotion authority; inspect an undeclared source; mutate a product system; execute an implementation atom; or allow a model to control identity, ordering, state, validation, or pass/fail decisions, and it must stop with an explicit reason and the single next required question whenever an input is missing, inaccessible, stale, unverifiable, provenance-free, or contradictory, model outputs are invalid or disagree beyond deterministic rules, required authority is absent, or any readiness invariant fails. _Source: `/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ ## q8 — What is deliberately not settled here, and left to whoever builds it?', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}, {'piece_id': 'p-0001', 'quote': 'The machinery must never invent a requirement, fact, dependency, evidence item, or owner decision; infer legal, business, permission, or promotion authority; inspect an undeclared source; mutate a product system; execute an implementation atom; or allow a model to control identity, ordering, state, validation, or pass/fail decisions, and it must stop with an explicit reason and the single next required question whenever an input is missing, inaccessible, stale, unverifiable, provenance-free, or contradictory, model outputs are invalid or disagree beyond deterministic rules, required authority is absent, or any readiness invariant fails.', 'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]}, 'type': 'requirement'}], 'schema_version': 1}

    def adapter(self):
        import importlib.util
        path = ROOT / 'skills/requirement-to-atom-readiness-machinery/scripts/evidence_adapter.py'
        spec = importlib.util.spec_from_file_location('evidence_graph_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_captured_graph_and_dependency_rejection(self):
        import copy
        adapter = self.adapter()
        graph = copy.deepcopy(self.captured_graph)
        adapter.validate(graph, adapter.graph_schema())
        self.assertEqual(len(graph['conditions']), 7)
        self.assertEqual(graph['conditions'][0]['condition_id'], 'mysql-query-timeout')
        layers = adapter.verify_edges(graph['nodes'], graph['edges'])
        self.assertTrue(all(value == 0 for value in layers.values()))
        a, b = [n['id'] for n in graph['nodes'] if n['type'] == 'requirement'][:2]
        for extra in [
            [{'type':'requires','source':a,'target':a}],
            [{'type':'supports','source':a,'target':b}],
            [{'type':'requires','source':a,'target':b}, {'type':'requires','source':b,'target':a}],
            [graph['edges'][0]],
        ]:
            with self.assertRaises(adapter.EvidenceRefused):
                adapter.verify_edges(graph['nodes'], graph['edges'] + extra)

    def test_capture_graph_rejects_extra_authority(self):
        import copy
        adapter = self.adapter()
        graph = copy.deepcopy(self.captured_graph)
        authority = next(n for n in graph['nodes'] if n['type'] == 'authority_decision')
        authority['record']['answer'] = 'approved'
        with self.assertRaises(adapter.EvidenceRefused):
            adapter.validate(graph, adapter.graph_schema())


class InterviewEngineTests(ReadinessKernelTests):
    # Real prepared state and explicitly transport-adapted research judgments captured 2026-09-08.
    # This pins deterministic admission, not new model execution or model-output truth.
    captured_pending = {'attempt': 1,
 'attempt_key': 'condition-c80e6a40f897a45920b67b6b:0',
 'envelopes': [{'envelope': {'attempt': 1,
                             'authorization': 'not-granted; preparation and submitted responses do '
                                              'not authorize a launch',
                             'envelope_sha256': 'db300c0d93eb60f4e0df137d409445c64f57200047d0063fc8d6efd66d9f5213',
                             'family': 'verification-adequacy',
                             'launcher': {'launcher': '/Users/kamenkamenov/.nvm/versions/node/v24.9.0/bin/codex',
                                          'sha256': '134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477',
                                          'target': '/Users/kamenkamenov/.nvm/versions/node/v24.9.0/lib/node_modules/@openai/codex/bin/codex.js',
                                          'version': 'codex-cli 0.151.0'},
                             'model_runtime': {'model': 'gpt-5.5',
                                               'provider': 'openai-codex-cli',
                                               'reasoning_effort': 'high'},
                             'node_id': 'condition-c80e6a40f897a45920b67b6b',
                             'predecessor_sha256': 'a1478c221c8b61c031d5fe1990ef1df72ce5f4ebe6235492a988bb46f1f11756',
                             'response_path': '/private/tmp/atom7-probe-S9SWcH/adapter-cases/success/run/interviews/00000089/seat-1-response.json',
                             'run_id': '33c3041f552c138e5aa73c9c79ecad71c7627564f8df4174e95889da705a8863',
                             'schema_version': 1,
                             'seat': 'seat-1',
                             'semantic_payload': {'allowed_verdicts': ['adequate',
                                                                       'inadequate',
                                                                       'cannot_assess'],
                                                  'answer_type': 'not-applicable',
                                                  'candidate': None,
                                                  'choices': [],
                                                  'criteria': [{'criterion_id': 'independent-evaluator',
                                                                'quote': '| 6 | Evaluation and '
                                                                         'final assessment can '
                                                                         "trust the candidate's "
                                                                         'own verdict | Critical | '
                                                                         'A candidate can '
                                                                         'effectively grade itself '
                                                                         '|',
                                                                'source_object_sha256': 'bd123e5ef8d894f79f142407c10417a84a3d1cb227ac8da23887c3bf19b23db0'}],
                                                  'dependency_ids': [],
                                                  'evidence': [{'access_receipt': {'outcome': 'accessible',
                                                                                   'pointer': '/access',
                                                                                   'source_id': 'telemetry-byte-receipt'},
                                                                'affected_requirement_ids': ['req-a85e221564f8558a',
                                                                                             'req-e17b44a659f36a19',
                                                                                             'req-e51c9757aeaa8d3d'],
                                                                'capture_method': 'Local capture '
                                                                                  'of the '
                                                                                  'previously '
                                                                                  'recorded '
                                                                                  'telemetry '
                                                                                  'findings; '
                                                                                  'byte-for-byte '
                                                                                  'reread checked '
                                                                                  'by SHA-256.',
                                                                'captured_at_utc': '2026-09-08T16:34:29.161663+00:00',
                                                                'claim': '| 6 | Evaluation and '
                                                                         'final assessment can '
                                                                         "trust the candidate's "
                                                                         'own verdict | Critical | '
                                                                         'A candidate can '
                                                                         'effectively grade itself '
                                                                         '|',
                                                                'evidence_id': 'telemetry-review',
                                                                'excerpt': '| 6 | Evaluation and '
                                                                           'final assessment can '
                                                                           "trust the candidate's "
                                                                           'own verdict | Critical '
                                                                           '| A candidate can '
                                                                           'effectively grade '
                                                                           'itself |',
                                                                'fitness': {'accessible_at_capture': True,
                                                                            'authorized_for_declared_use': True,
                                                                            'current': True,
                                                                            'fit': True,
                                                                            'hash_valid': True,
                                                                            'present': True,
                                                                            'reproducible': True},
                                                                'freshness_rule': {'kind': 'immutable',
                                                                                   'max_age_seconds': 0},
                                                                'limitations': ['Captured finding '
                                                                                'about evaluator '
                                                                                'self-trust, not a '
                                                                                'new model '
                                                                                'judgment or '
                                                                                'current repair '
                                                                                'verification.'],
                                                                'model_share_authorization': {'receipt_source_id': None,
                                                                                              'use': 'local-only'},
                                                                'origin': '/private/tmp/atom7-probe-S9SWcH/adapter-cases/sources/graph-telemetry-review',
                                                                'reproduction_receipt': {'outcome': 'reproduced',
                                                                                         'pointer': '/reproduction',
                                                                                         'source_id': 'telemetry-byte-receipt'},
                                                                'required_maturity': 'current-system',
                                                                'sensitivity_class': 'internal',
                                                                'source_object_sha256': 'bd123e5ef8d894f79f142407c10417a84a3d1cb227ac8da23887c3bf19b23db0'}],
                                                  'family': 'verification-adequacy',
                                                  'forbidden_judgments': ['owner authority',
                                                                          'requirements creation',
                                                                          'scope expansion',
                                                                          'legal or commercial '
                                                                          'policy approval',
                                                                          'model sharing '
                                                                          'authorization',
                                                                          'implementation approval',
                                                                          'execution',
                                                                          'readiness '
                                                                          'certification'],
                                                  'question': 'Would the listed observable and '
                                                              'rejection criteria prove the '
                                                              'practical outcome without trusting '
                                                              'the producer conclusion?',
                                                  'subjects': [{'id': 'req-a85e221564f8558a',
                                                                'record': {'disposition': 'blocked',
                                                                           'exact_text': 'The '
                                                                                         'controller '
                                                                                         'may '
                                                                                         'declare '
                                                                                         'readiness '
                                                                                         'only '
                                                                                         'when '
                                                                                         'deterministic '
                                                                                         'checks '
                                                                                         'confirm '
                                                                                         'that '
                                                                                         'every '
                                                                                         'requirement '
                                                                                         'has a '
                                                                                         'provenance-bound '
                                                                                         'disposition, '
                                                                                         'all '
                                                                                         'dependencies '
                                                                                         'and '
                                                                                         'contradictions '
                                                                                         'are '
                                                                                         'resolved, '
                                                                                         'all '
                                                                                         'mandatory '
                                                                                         'evidence '
                                                                                         'is '
                                                                                         'current '
                                                                                         'and '
                                                                                         'reproducible, '
                                                                                         'the '
                                                                                         'package '
                                                                                         'passes '
                                                                                         'schema, '
                                                                                         'integrity, '
                                                                                         'and '
                                                                                         'replay '
                                                                                         'validation, '
                                                                                         'and '
                                                                                         'every '
                                                                                         'proposed '
                                                                                         'atom has '
                                                                                         'explicit '
                                                                                         'verification '
                                                                                         'and stop '
                                                                                         'conditions. '
                                                                                         '`needs_owner` '
                                                                                         'and '
                                                                                         '`blocked` '
                                                                                         'are '
                                                                                         'valid '
                                                                                         'resumable '
                                                                                         'run '
                                                                                         'outcomes '
                                                                                         'but '
                                                                                         'never '
                                                                                         'readiness, '
                                                                                         'and only '
                                                                                         'the '
                                                                                         'owner '
                                                                                         'may '
                                                                                         'approve '
                                                                                         'the '
                                                                                         'resulting '
                                                                                         'atom '
                                                                                         'sequence '
                                                                                         'and '
                                                                                         'authorize '
                                                                                         'Atom '
                                                                                         'Building '
                                                                                         'Machinery '
                                                                                         'to '
                                                                                         'begin.',
                                                                           'maturity': 'unassessed',
                                                                           'ordinal': 2,
                                                                           'requirement_id': 'req-a85e221564f8558a',
                                                                           'source_anchors': [{'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'controller '
                                                                                                        'may '
                                                                                                        'declare '
                                                                                                        'readiness '
                                                                                                        'only '
                                                                                                        'when '
                                                                                                        'deterministic '
                                                                                                        'checks '
                                                                                                        'confirm '
                                                                                                        'that '
                                                                                                        'every '
                                                                                                        'requirement '
                                                                                                        'has '
                                                                                                        'a '
                                                                                                        'provenance-bound '
                                                                                                        'disposition, '
                                                                                                        'all '
                                                                                                        'dependencies '
                                                                                                        'and '
                                                                                                        'contradictions '
                                                                                                        'are '
                                                                                                        'resolved, '
                                                                                                        'all '
                                                                                                        'mandatory '
                                                                                                        'evidence '
                                                                                                        'is '
                                                                                                        'current '
                                                                                                        'and '
                                                                                                        'reproducible, '
                                                                                                        'the '
                                                                                                        'package '
                                                                                                        'passes '
                                                                                                        'schema, '
                                                                                                        'integrity, '
                                                                                                        'and '
                                                                                                        'replay '
                                                                                                        'validation, '
                                                                                                        'and '
                                                                                                        'every '
                                                                                                        'proposed '
                                                                                                        'atom '
                                                                                                        'has '
                                                                                                        'explicit '
                                                                                                        'verification '
                                                                                                        'and '
                                                                                                        'stop '
                                                                                                        'conditions; '
                                                                                                        '`needs_owner` '
                                                                                                        'and '
                                                                                                        '`blocked` '
                                                                                                        'are '
                                                                                                        'valid '
                                                                                                        'resumable '
                                                                                                        'run '
                                                                                                        'outcomes '
                                                                                                        'but '
                                                                                                        'never '
                                                                                                        'readiness, '
                                                                                                        'and '
                                                                                                        'only '
                                                                                                        'the '
                                                                                                        'owner '
                                                                                                        'may '
                                                                                                        'approve '
                                                                                                        'the '
                                                                                                        'resulting '
                                                                                                        'atom '
                                                                                                        'sequence '
                                                                                                        'and '
                                                                                                        'authorize '
                                                                                                        'Atom '
                                                                                                        'Building '
                                                                                                        'Machinery '
                                                                                                        'to '
                                                                                                        'begin. '
                                                                                                        '_Source: '
                                                                                                        '`/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ '
                                                                                                        '## '
                                                                                                        'q7 '
                                                                                                        '— '
                                                                                                        'What '
                                                                                                        'must '
                                                                                                        'it '
                                                                                                        'never '
                                                                                                        'do, '
                                                                                                        'and '
                                                                                                        'what '
                                                                                                        'makes '
                                                                                                        'it '
                                                                                                        'stop '
                                                                                                        'rather '
                                                                                                        'than '
                                                                                                        'guess?',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'},
                                                                                              {'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'controller '
                                                                                                        'may '
                                                                                                        'declare '
                                                                                                        'readiness '
                                                                                                        'only '
                                                                                                        'when '
                                                                                                        'deterministic '
                                                                                                        'checks '
                                                                                                        'confirm '
                                                                                                        'that '
                                                                                                        'every '
                                                                                                        'requirement '
                                                                                                        'has '
                                                                                                        'a '
                                                                                                        'provenance-bound '
                                                                                                        'disposition, '
                                                                                                        'all '
                                                                                                        'dependencies '
                                                                                                        'and '
                                                                                                        'contradictions '
                                                                                                        'are '
                                                                                                        'resolved, '
                                                                                                        'all '
                                                                                                        'mandatory '
                                                                                                        'evidence '
                                                                                                        'is '
                                                                                                        'current '
                                                                                                        'and '
                                                                                                        'reproducible, '
                                                                                                        'the '
                                                                                                        'package '
                                                                                                        'passes '
                                                                                                        'schema, '
                                                                                                        'integrity, '
                                                                                                        'and '
                                                                                                        'replay '
                                                                                                        'validation, '
                                                                                                        'and '
                                                                                                        'every '
                                                                                                        'proposed '
                                                                                                        'atom '
                                                                                                        'has '
                                                                                                        'explicit '
                                                                                                        'verification '
                                                                                                        'and '
                                                                                                        'stop '
                                                                                                        'conditions; '
                                                                                                        '`needs_owner` '
                                                                                                        'and '
                                                                                                        '`blocked` '
                                                                                                        'are '
                                                                                                        'valid '
                                                                                                        'resumable '
                                                                                                        'run '
                                                                                                        'outcomes '
                                                                                                        'but '
                                                                                                        'never '
                                                                                                        'readiness, '
                                                                                                        'and '
                                                                                                        'only '
                                                                                                        'the '
                                                                                                        'owner '
                                                                                                        'may '
                                                                                                        'approve '
                                                                                                        'the '
                                                                                                        'resulting '
                                                                                                        'atom '
                                                                                                        'sequence '
                                                                                                        'and '
                                                                                                        'authorize '
                                                                                                        'Atom '
                                                                                                        'Building '
                                                                                                        'Machinery '
                                                                                                        'to '
                                                                                                        'begin.',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]},
                                                                'type': 'requirement'},
                                                               {'id': 'req-e17b44a659f36a19',
                                                                'record': {'disposition': 'blocked',
                                                                           'exact_text': 'The '
                                                                                         'machinery '
                                                                                         'produces '
                                                                                         'a '
                                                                                         'versioned, '
                                                                                         'hash-bound '
                                                                                         'readiness '
                                                                                         'package '
                                                                                         'containing '
                                                                                         'a '
                                                                                         'machine-readable '
                                                                                         'readiness '
                                                                                         'ledger, '
                                                                                         'a '
                                                                                         'requirement-to-evidence-and-dependency '
                                                                                         'graph, '
                                                                                         'and a '
                                                                                         'verdict '
                                                                                         'with '
                                                                                         'reasons '
                                                                                         'for '
                                                                                         'every '
                                                                                         'requirement. '
                                                                                         'While '
                                                                                         'blocked '
                                                                                         'it also '
                                                                                         'contains '
                                                                                         'the '
                                                                                         'ordered '
                                                                                         'unresolved-evidence '
                                                                                         'and '
                                                                                         'owner-decision '
                                                                                         'queue, '
                                                                                         'and when '
                                                                                         'ready it '
                                                                                         'instead '
                                                                                         'contains '
                                                                                         'dependency-ordered, '
                                                                                         'independently '
                                                                                         'testable '
                                                                                         'atom '
                                                                                         'envelopes '
                                                                                         'defining '
                                                                                         'scope, '
                                                                                         'inputs, '
                                                                                         'boundaries, '
                                                                                         'prerequisites, '
                                                                                         'acceptance '
                                                                                         'checks, '
                                                                                         'verification '
                                                                                         'paths, '
                                                                                         'and stop '
                                                                                         'conditions, '
                                                                                         'together '
                                                                                         'with a '
                                                                                         'human-readable '
                                                                                         'report '
                                                                                         'and '
                                                                                         'replay '
                                                                                         'receipt.',
                                                                           'maturity': 'unassessed',
                                                                           'ordinal': 5,
                                                                           'requirement_id': 'req-e17b44a659f36a19',
                                                                           'source_anchors': [{'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'machinery '
                                                                                                        'produces '
                                                                                                        'a '
                                                                                                        'versioned, '
                                                                                                        'hash-bound '
                                                                                                        'readiness '
                                                                                                        'package '
                                                                                                        'containing '
                                                                                                        'a '
                                                                                                        'machine-readable '
                                                                                                        'readiness '
                                                                                                        'ledger, '
                                                                                                        'a '
                                                                                                        'requirement-to-evidence-and-dependency '
                                                                                                        'graph, '
                                                                                                        'and '
                                                                                                        'a '
                                                                                                        'verdict '
                                                                                                        'with '
                                                                                                        'reasons '
                                                                                                        'for '
                                                                                                        'every '
                                                                                                        'requirement; '
                                                                                                        'while '
                                                                                                        'blocked '
                                                                                                        'it '
                                                                                                        'also '
                                                                                                        'contains '
                                                                                                        'the '
                                                                                                        'ordered '
                                                                                                        'unresolved-evidence '
                                                                                                        'and '
                                                                                                        'owner-decision '
                                                                                                        'queue, '
                                                                                                        'and '
                                                                                                        'when '
                                                                                                        'ready '
                                                                                                        'it '
                                                                                                        'instead '
                                                                                                        'contains '
                                                                                                        'dependency-ordered, '
                                                                                                        'independently '
                                                                                                        'testable '
                                                                                                        'atom '
                                                                                                        'envelopes '
                                                                                                        'defining '
                                                                                                        'scope, '
                                                                                                        'inputs, '
                                                                                                        'boundaries, '
                                                                                                        'prerequisites, '
                                                                                                        'acceptance '
                                                                                                        'checks, '
                                                                                                        'verification '
                                                                                                        'paths, '
                                                                                                        'and '
                                                                                                        'stop '
                                                                                                        'conditions, '
                                                                                                        'together '
                                                                                                        'with '
                                                                                                        'a '
                                                                                                        'human-readable '
                                                                                                        'report '
                                                                                                        'and '
                                                                                                        'replay '
                                                                                                        'receipt. '
                                                                                                        '_Source: '
                                                                                                        '`/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ '
                                                                                                        '## '
                                                                                                        'q6 '
                                                                                                        '— '
                                                                                                        'How '
                                                                                                        'does '
                                                                                                        'anybody '
                                                                                                        'tell '
                                                                                                        'it '
                                                                                                        'is '
                                                                                                        'done, '
                                                                                                        'and '
                                                                                                        'who '
                                                                                                        'decides?',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'},
                                                                                              {'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'machinery '
                                                                                                        'produces '
                                                                                                        'a '
                                                                                                        'versioned, '
                                                                                                        'hash-bound '
                                                                                                        'readiness '
                                                                                                        'package '
                                                                                                        'containing '
                                                                                                        'a '
                                                                                                        'machine-readable '
                                                                                                        'readiness '
                                                                                                        'ledger, '
                                                                                                        'a '
                                                                                                        'requirement-to-evidence-and-dependency '
                                                                                                        'graph, '
                                                                                                        'and '
                                                                                                        'a '
                                                                                                        'verdict '
                                                                                                        'with '
                                                                                                        'reasons '
                                                                                                        'for '
                                                                                                        'every '
                                                                                                        'requirement; '
                                                                                                        'while '
                                                                                                        'blocked '
                                                                                                        'it '
                                                                                                        'also '
                                                                                                        'contains '
                                                                                                        'the '
                                                                                                        'ordered '
                                                                                                        'unresolved-evidence '
                                                                                                        'and '
                                                                                                        'owner-decision '
                                                                                                        'queue, '
                                                                                                        'and '
                                                                                                        'when '
                                                                                                        'ready '
                                                                                                        'it '
                                                                                                        'instead '
                                                                                                        'contains '
                                                                                                        'dependency-ordered, '
                                                                                                        'independently '
                                                                                                        'testable '
                                                                                                        'atom '
                                                                                                        'envelopes '
                                                                                                        'defining '
                                                                                                        'scope, '
                                                                                                        'inputs, '
                                                                                                        'boundaries, '
                                                                                                        'prerequisites, '
                                                                                                        'acceptance '
                                                                                                        'checks, '
                                                                                                        'verification '
                                                                                                        'paths, '
                                                                                                        'and '
                                                                                                        'stop '
                                                                                                        'conditions, '
                                                                                                        'together '
                                                                                                        'with '
                                                                                                        'a '
                                                                                                        'human-readable '
                                                                                                        'report '
                                                                                                        'and '
                                                                                                        'replay '
                                                                                                        'receipt.',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]},
                                                                'type': 'requirement'},
                                                               {'id': 'req-e51c9757aeaa8d3d',
                                                                'record': {'disposition': 'blocked',
                                                                           'exact_text': 'The '
                                                                                         'machinery '
                                                                                         'must '
                                                                                         'never '
                                                                                         'invent a '
                                                                                         'requirement, '
                                                                                         'fact, '
                                                                                         'dependency, '
                                                                                         'evidence '
                                                                                         'item, or '
                                                                                         'owner '
                                                                                         'decision; '
                                                                                         'infer '
                                                                                         'legal, '
                                                                                         'business, '
                                                                                         'permission, '
                                                                                         'or '
                                                                                         'promotion '
                                                                                         'authority; '
                                                                                         'inspect '
                                                                                         'an '
                                                                                         'undeclared '
                                                                                         'source; '
                                                                                         'mutate a '
                                                                                         'product '
                                                                                         'system; '
                                                                                         'execute '
                                                                                         'an '
                                                                                         'implementation '
                                                                                         'atom; or '
                                                                                         'allow a '
                                                                                         'model to '
                                                                                         'control '
                                                                                         'identity, '
                                                                                         'ordering, '
                                                                                         'state, '
                                                                                         'validation, '
                                                                                         'or '
                                                                                         'pass/fail '
                                                                                         'decisions. '
                                                                                         'It must '
                                                                                         'stop '
                                                                                         'with an '
                                                                                         'explicit '
                                                                                         'reason '
                                                                                         'and the '
                                                                                         'single '
                                                                                         'next '
                                                                                         'required '
                                                                                         'question '
                                                                                         'whenever '
                                                                                         'an input '
                                                                                         'is '
                                                                                         'missing, '
                                                                                         'inaccessible, '
                                                                                         'stale, '
                                                                                         'unverifiable, '
                                                                                         'provenance-free, '
                                                                                         'or '
                                                                                         'contradictory, '
                                                                                         'model '
                                                                                         'outputs '
                                                                                         'are '
                                                                                         'invalid '
                                                                                         'or '
                                                                                         'disagree '
                                                                                         'beyond '
                                                                                         'deterministic '
                                                                                         'rules, '
                                                                                         'required '
                                                                                         'authority '
                                                                                         'is '
                                                                                         'absent, '
                                                                                         'or any '
                                                                                         'readiness '
                                                                                         'invariant '
                                                                                         'fails.',
                                                                           'maturity': 'unassessed',
                                                                           'ordinal': 3,
                                                                           'requirement_id': 'req-e51c9757aeaa8d3d',
                                                                           'source_anchors': [{'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'machinery '
                                                                                                        'must '
                                                                                                        'never '
                                                                                                        'invent '
                                                                                                        'a '
                                                                                                        'requirement, '
                                                                                                        'fact, '
                                                                                                        'dependency, '
                                                                                                        'evidence '
                                                                                                        'item, '
                                                                                                        'or '
                                                                                                        'owner '
                                                                                                        'decision; '
                                                                                                        'infer '
                                                                                                        'legal, '
                                                                                                        'business, '
                                                                                                        'permission, '
                                                                                                        'or '
                                                                                                        'promotion '
                                                                                                        'authority; '
                                                                                                        'inspect '
                                                                                                        'an '
                                                                                                        'undeclared '
                                                                                                        'source; '
                                                                                                        'mutate '
                                                                                                        'a '
                                                                                                        'product '
                                                                                                        'system; '
                                                                                                        'execute '
                                                                                                        'an '
                                                                                                        'implementation '
                                                                                                        'atom; '
                                                                                                        'or '
                                                                                                        'allow '
                                                                                                        'a '
                                                                                                        'model '
                                                                                                        'to '
                                                                                                        'control '
                                                                                                        'identity, '
                                                                                                        'ordering, '
                                                                                                        'state, '
                                                                                                        'validation, '
                                                                                                        'or '
                                                                                                        'pass/fail '
                                                                                                        'decisions, '
                                                                                                        'and '
                                                                                                        'it '
                                                                                                        'must '
                                                                                                        'stop '
                                                                                                        'with '
                                                                                                        'an '
                                                                                                        'explicit '
                                                                                                        'reason '
                                                                                                        'and '
                                                                                                        'the '
                                                                                                        'single '
                                                                                                        'next '
                                                                                                        'required '
                                                                                                        'question '
                                                                                                        'whenever '
                                                                                                        'an '
                                                                                                        'input '
                                                                                                        'is '
                                                                                                        'missing, '
                                                                                                        'inaccessible, '
                                                                                                        'stale, '
                                                                                                        'unverifiable, '
                                                                                                        'provenance-free, '
                                                                                                        'or '
                                                                                                        'contradictory, '
                                                                                                        'model '
                                                                                                        'outputs '
                                                                                                        'are '
                                                                                                        'invalid '
                                                                                                        'or '
                                                                                                        'disagree '
                                                                                                        'beyond '
                                                                                                        'deterministic '
                                                                                                        'rules, '
                                                                                                        'required '
                                                                                                        'authority '
                                                                                                        'is '
                                                                                                        'absent, '
                                                                                                        'or '
                                                                                                        'any '
                                                                                                        'readiness '
                                                                                                        'invariant '
                                                                                                        'fails. '
                                                                                                        '_Source: '
                                                                                                        '`/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ '
                                                                                                        '## '
                                                                                                        'q8 '
                                                                                                        '— '
                                                                                                        'What '
                                                                                                        'is '
                                                                                                        'deliberately '
                                                                                                        'not '
                                                                                                        'settled '
                                                                                                        'here, '
                                                                                                        'and '
                                                                                                        'left '
                                                                                                        'to '
                                                                                                        'whoever '
                                                                                                        'builds '
                                                                                                        'it?',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'},
                                                                                              {'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'machinery '
                                                                                                        'must '
                                                                                                        'never '
                                                                                                        'invent '
                                                                                                        'a '
                                                                                                        'requirement, '
                                                                                                        'fact, '
                                                                                                        'dependency, '
                                                                                                        'evidence '
                                                                                                        'item, '
                                                                                                        'or '
                                                                                                        'owner '
                                                                                                        'decision; '
                                                                                                        'infer '
                                                                                                        'legal, '
                                                                                                        'business, '
                                                                                                        'permission, '
                                                                                                        'or '
                                                                                                        'promotion '
                                                                                                        'authority; '
                                                                                                        'inspect '
                                                                                                        'an '
                                                                                                        'undeclared '
                                                                                                        'source; '
                                                                                                        'mutate '
                                                                                                        'a '
                                                                                                        'product '
                                                                                                        'system; '
                                                                                                        'execute '
                                                                                                        'an '
                                                                                                        'implementation '
                                                                                                        'atom; '
                                                                                                        'or '
                                                                                                        'allow '
                                                                                                        'a '
                                                                                                        'model '
                                                                                                        'to '
                                                                                                        'control '
                                                                                                        'identity, '
                                                                                                        'ordering, '
                                                                                                        'state, '
                                                                                                        'validation, '
                                                                                                        'or '
                                                                                                        'pass/fail '
                                                                                                        'decisions, '
                                                                                                        'and '
                                                                                                        'it '
                                                                                                        'must '
                                                                                                        'stop '
                                                                                                        'with '
                                                                                                        'an '
                                                                                                        'explicit '
                                                                                                        'reason '
                                                                                                        'and '
                                                                                                        'the '
                                                                                                        'single '
                                                                                                        'next '
                                                                                                        'required '
                                                                                                        'question '
                                                                                                        'whenever '
                                                                                                        'an '
                                                                                                        'input '
                                                                                                        'is '
                                                                                                        'missing, '
                                                                                                        'inaccessible, '
                                                                                                        'stale, '
                                                                                                        'unverifiable, '
                                                                                                        'provenance-free, '
                                                                                                        'or '
                                                                                                        'contradictory, '
                                                                                                        'model '
                                                                                                        'outputs '
                                                                                                        'are '
                                                                                                        'invalid '
                                                                                                        'or '
                                                                                                        'disagree '
                                                                                                        'beyond '
                                                                                                        'deterministic '
                                                                                                        'rules, '
                                                                                                        'required '
                                                                                                        'authority '
                                                                                                        'is '
                                                                                                        'absent, '
                                                                                                        'or '
                                                                                                        'any '
                                                                                                        'readiness '
                                                                                                        'invariant '
                                                                                                        'fails.',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]},
                                                                'type': 'requirement'}]},
                             'semantic_payload_sha256': '1cff3cbfe9eaba36371bad33b9771647530f043a1ffa3600ec2b70fd1f74e6d2',
                             'timeout_ms': 300000},
                'response_schema': {'additionalProperties': False,
                                    'properties': {'attempt': {'const': 1,
                                                               'maximum': 2,
                                                               'minimum': 1,
                                                               'type': 'integer'},
                                                   'criteria': {'items': {'additionalProperties': False,
                                                                          'properties': {'criterion_id': {'enum': ['independent-evaluator'],
                                                                                                          'maxLength': 8192,
                                                                                                          'minLength': 1,
                                                                                                          'pattern': '\\S',
                                                                                                          'type': 'string'},
                                                                                         'evidence_ids': {'items': {'maxLength': 8192,
                                                                                                                    'minLength': 1,
                                                                                                                    'pattern': '\\S',
                                                                                                                    'type': 'string'},
                                                                                                          'maxItems': 256,
                                                                                                          'minItems': 1,
                                                                                                          'type': 'array',
                                                                                                          'uniqueItems': True},
                                                                                         'reason': {'maxLength': 8192,
                                                                                                    'minLength': 1,
                                                                                                    'pattern': '\\S',
                                                                                                    'type': 'string'},
                                                                                         'verdict': {'enum': ['satisfied',
                                                                                                              'unsatisfied',
                                                                                                              'cannot_assess'],
                                                                                                     'type': 'string'}},
                                                                          'required': ['criterion_id',
                                                                                       'verdict',
                                                                                       'evidence_ids',
                                                                                       'reason'],
                                                                          'type': 'object'},
                                                                'maxItems': 256,
                                                                'minItems': 1,
                                                                'type': 'array'},
                                                   'envelope_sha256': {'const': 'db300c0d93eb60f4e0df137d409445c64f57200047d0063fc8d6efd66d9f5213',
                                                                       'pattern': '^[0-9a-f]{64}$',
                                                                       'type': 'string'},
                                                   'evidence_ids': {'items': {'enum': ['telemetry-review'],
                                                                              'maxLength': 8192,
                                                                              'minLength': 1,
                                                                              'pattern': '\\S',
                                                                              'type': 'string'},
                                                                    'maxItems': 256,
                                                                    'minItems': 1,
                                                                    'type': 'array',
                                                                    'uniqueItems': True},
                                                   'family': {'const': 'verification-adequacy',
                                                              'type': 'string'},
                                                   'node_id': {'const': 'condition-c80e6a40f897a45920b67b6b',
                                                               'maxLength': 8192,
                                                               'minLength': 1,
                                                               'pattern': '\\S',
                                                               'type': 'string'},
                                                   'quotes': {'items': {'additionalProperties': False,
                                                                        'properties': {'evidence_id': {'maxLength': 8192,
                                                                                                       'minLength': 1,
                                                                                                       'pattern': '\\S',
                                                                                                       'type': 'string'},
                                                                                       'quote': {'maxLength': 8192,
                                                                                                 'minLength': 1,
                                                                                                 'pattern': '\\S',
                                                                                                 'type': 'string'}},
                                                                        'required': ['evidence_id',
                                                                                     'quote'],
                                                                        'type': 'object'},
                                                              'maxItems': 256,
                                                              'minItems': 1,
                                                              'type': 'array',
                                                              'uniqueItems': True},
                                                   'reason': {'maxLength': 8192,
                                                              'minLength': 1,
                                                              'pattern': '\\S',
                                                              'type': 'string'},
                                                   'run_id': {'const': '33c3041f552c138e5aa73c9c79ecad71c7627564f8df4174e95889da705a8863',
                                                              'pattern': '^[0-9a-f]{64}$',
                                                              'type': 'string'},
                                                   'schema_version': {'const': 1,
                                                                      'type': 'integer'},
                                                   'seat': {'const': 'seat-1',
                                                            'enum': ['seat-1', 'seat-2'],
                                                            'type': 'string'},
                                                   'verdict': {'enum': ['adequate',
                                                                        'inadequate',
                                                                        'cannot_assess'],
                                                               'type': 'string'}},
                                    'required': ['schema_version',
                                                 'run_id',
                                                 'node_id',
                                                 'family',
                                                 'attempt',
                                                 'seat',
                                                 'envelope_sha256',
                                                 'verdict',
                                                 'evidence_ids',
                                                 'quotes',
                                                 'reason',
                                                 'criteria'],
                                    'type': 'object'}},
               {'envelope': {'attempt': 1,
                             'authorization': 'not-granted; preparation and submitted responses do '
                                              'not authorize a launch',
                             'envelope_sha256': 'e3336d10592d6b64420c33a252254c7eed4bf6d62676a1c35334d4ac75409575',
                             'family': 'verification-adequacy',
                             'launcher': {'launcher': '/Users/kamenkamenov/.nvm/versions/node/v24.9.0/bin/codex',
                                          'sha256': '134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477',
                                          'target': '/Users/kamenkamenov/.nvm/versions/node/v24.9.0/lib/node_modules/@openai/codex/bin/codex.js',
                                          'version': 'codex-cli 0.151.0'},
                             'model_runtime': {'model': 'gpt-5.5',
                                               'provider': 'openai-codex-cli',
                                               'reasoning_effort': 'high'},
                             'node_id': 'condition-c80e6a40f897a45920b67b6b',
                             'predecessor_sha256': 'a1478c221c8b61c031d5fe1990ef1df72ce5f4ebe6235492a988bb46f1f11756',
                             'response_path': '/private/tmp/atom7-probe-S9SWcH/adapter-cases/success/run/interviews/00000089/seat-2-response.json',
                             'run_id': '33c3041f552c138e5aa73c9c79ecad71c7627564f8df4174e95889da705a8863',
                             'schema_version': 1,
                             'seat': 'seat-2',
                             'semantic_payload': {'allowed_verdicts': ['adequate',
                                                                       'inadequate',
                                                                       'cannot_assess'],
                                                  'answer_type': 'not-applicable',
                                                  'candidate': None,
                                                  'choices': [],
                                                  'criteria': [{'criterion_id': 'independent-evaluator',
                                                                'quote': '| 6 | Evaluation and '
                                                                         'final assessment can '
                                                                         "trust the candidate's "
                                                                         'own verdict | Critical | '
                                                                         'A candidate can '
                                                                         'effectively grade itself '
                                                                         '|',
                                                                'source_object_sha256': 'bd123e5ef8d894f79f142407c10417a84a3d1cb227ac8da23887c3bf19b23db0'}],
                                                  'dependency_ids': [],
                                                  'evidence': [{'access_receipt': {'outcome': 'accessible',
                                                                                   'pointer': '/access',
                                                                                   'source_id': 'telemetry-byte-receipt'},
                                                                'affected_requirement_ids': ['req-a85e221564f8558a',
                                                                                             'req-e17b44a659f36a19',
                                                                                             'req-e51c9757aeaa8d3d'],
                                                                'capture_method': 'Local capture '
                                                                                  'of the '
                                                                                  'previously '
                                                                                  'recorded '
                                                                                  'telemetry '
                                                                                  'findings; '
                                                                                  'byte-for-byte '
                                                                                  'reread checked '
                                                                                  'by SHA-256.',
                                                                'captured_at_utc': '2026-09-08T16:34:29.161663+00:00',
                                                                'claim': '| 6 | Evaluation and '
                                                                         'final assessment can '
                                                                         "trust the candidate's "
                                                                         'own verdict | Critical | '
                                                                         'A candidate can '
                                                                         'effectively grade itself '
                                                                         '|',
                                                                'evidence_id': 'telemetry-review',
                                                                'excerpt': '| 6 | Evaluation and '
                                                                           'final assessment can '
                                                                           "trust the candidate's "
                                                                           'own verdict | Critical '
                                                                           '| A candidate can '
                                                                           'effectively grade '
                                                                           'itself |',
                                                                'fitness': {'accessible_at_capture': True,
                                                                            'authorized_for_declared_use': True,
                                                                            'current': True,
                                                                            'fit': True,
                                                                            'hash_valid': True,
                                                                            'present': True,
                                                                            'reproducible': True},
                                                                'freshness_rule': {'kind': 'immutable',
                                                                                   'max_age_seconds': 0},
                                                                'limitations': ['Captured finding '
                                                                                'about evaluator '
                                                                                'self-trust, not a '
                                                                                'new model '
                                                                                'judgment or '
                                                                                'current repair '
                                                                                'verification.'],
                                                                'model_share_authorization': {'receipt_source_id': None,
                                                                                              'use': 'local-only'},
                                                                'origin': '/private/tmp/atom7-probe-S9SWcH/adapter-cases/sources/graph-telemetry-review',
                                                                'reproduction_receipt': {'outcome': 'reproduced',
                                                                                         'pointer': '/reproduction',
                                                                                         'source_id': 'telemetry-byte-receipt'},
                                                                'required_maturity': 'current-system',
                                                                'sensitivity_class': 'internal',
                                                                'source_object_sha256': 'bd123e5ef8d894f79f142407c10417a84a3d1cb227ac8da23887c3bf19b23db0'}],
                                                  'family': 'verification-adequacy',
                                                  'forbidden_judgments': ['owner authority',
                                                                          'requirements creation',
                                                                          'scope expansion',
                                                                          'legal or commercial '
                                                                          'policy approval',
                                                                          'model sharing '
                                                                          'authorization',
                                                                          'implementation approval',
                                                                          'execution',
                                                                          'readiness '
                                                                          'certification'],
                                                  'question': 'Would the listed observable and '
                                                              'rejection criteria prove the '
                                                              'practical outcome without trusting '
                                                              'the producer conclusion?',
                                                  'subjects': [{'id': 'req-a85e221564f8558a',
                                                                'record': {'disposition': 'blocked',
                                                                           'exact_text': 'The '
                                                                                         'controller '
                                                                                         'may '
                                                                                         'declare '
                                                                                         'readiness '
                                                                                         'only '
                                                                                         'when '
                                                                                         'deterministic '
                                                                                         'checks '
                                                                                         'confirm '
                                                                                         'that '
                                                                                         'every '
                                                                                         'requirement '
                                                                                         'has a '
                                                                                         'provenance-bound '
                                                                                         'disposition, '
                                                                                         'all '
                                                                                         'dependencies '
                                                                                         'and '
                                                                                         'contradictions '
                                                                                         'are '
                                                                                         'resolved, '
                                                                                         'all '
                                                                                         'mandatory '
                                                                                         'evidence '
                                                                                         'is '
                                                                                         'current '
                                                                                         'and '
                                                                                         'reproducible, '
                                                                                         'the '
                                                                                         'package '
                                                                                         'passes '
                                                                                         'schema, '
                                                                                         'integrity, '
                                                                                         'and '
                                                                                         'replay '
                                                                                         'validation, '
                                                                                         'and '
                                                                                         'every '
                                                                                         'proposed '
                                                                                         'atom has '
                                                                                         'explicit '
                                                                                         'verification '
                                                                                         'and stop '
                                                                                         'conditions. '
                                                                                         '`needs_owner` '
                                                                                         'and '
                                                                                         '`blocked` '
                                                                                         'are '
                                                                                         'valid '
                                                                                         'resumable '
                                                                                         'run '
                                                                                         'outcomes '
                                                                                         'but '
                                                                                         'never '
                                                                                         'readiness, '
                                                                                         'and only '
                                                                                         'the '
                                                                                         'owner '
                                                                                         'may '
                                                                                         'approve '
                                                                                         'the '
                                                                                         'resulting '
                                                                                         'atom '
                                                                                         'sequence '
                                                                                         'and '
                                                                                         'authorize '
                                                                                         'Atom '
                                                                                         'Building '
                                                                                         'Machinery '
                                                                                         'to '
                                                                                         'begin.',
                                                                           'maturity': 'unassessed',
                                                                           'ordinal': 2,
                                                                           'requirement_id': 'req-a85e221564f8558a',
                                                                           'source_anchors': [{'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'controller '
                                                                                                        'may '
                                                                                                        'declare '
                                                                                                        'readiness '
                                                                                                        'only '
                                                                                                        'when '
                                                                                                        'deterministic '
                                                                                                        'checks '
                                                                                                        'confirm '
                                                                                                        'that '
                                                                                                        'every '
                                                                                                        'requirement '
                                                                                                        'has '
                                                                                                        'a '
                                                                                                        'provenance-bound '
                                                                                                        'disposition, '
                                                                                                        'all '
                                                                                                        'dependencies '
                                                                                                        'and '
                                                                                                        'contradictions '
                                                                                                        'are '
                                                                                                        'resolved, '
                                                                                                        'all '
                                                                                                        'mandatory '
                                                                                                        'evidence '
                                                                                                        'is '
                                                                                                        'current '
                                                                                                        'and '
                                                                                                        'reproducible, '
                                                                                                        'the '
                                                                                                        'package '
                                                                                                        'passes '
                                                                                                        'schema, '
                                                                                                        'integrity, '
                                                                                                        'and '
                                                                                                        'replay '
                                                                                                        'validation, '
                                                                                                        'and '
                                                                                                        'every '
                                                                                                        'proposed '
                                                                                                        'atom '
                                                                                                        'has '
                                                                                                        'explicit '
                                                                                                        'verification '
                                                                                                        'and '
                                                                                                        'stop '
                                                                                                        'conditions; '
                                                                                                        '`needs_owner` '
                                                                                                        'and '
                                                                                                        '`blocked` '
                                                                                                        'are '
                                                                                                        'valid '
                                                                                                        'resumable '
                                                                                                        'run '
                                                                                                        'outcomes '
                                                                                                        'but '
                                                                                                        'never '
                                                                                                        'readiness, '
                                                                                                        'and '
                                                                                                        'only '
                                                                                                        'the '
                                                                                                        'owner '
                                                                                                        'may '
                                                                                                        'approve '
                                                                                                        'the '
                                                                                                        'resulting '
                                                                                                        'atom '
                                                                                                        'sequence '
                                                                                                        'and '
                                                                                                        'authorize '
                                                                                                        'Atom '
                                                                                                        'Building '
                                                                                                        'Machinery '
                                                                                                        'to '
                                                                                                        'begin. '
                                                                                                        '_Source: '
                                                                                                        '`/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ '
                                                                                                        '## '
                                                                                                        'q7 '
                                                                                                        '— '
                                                                                                        'What '
                                                                                                        'must '
                                                                                                        'it '
                                                                                                        'never '
                                                                                                        'do, '
                                                                                                        'and '
                                                                                                        'what '
                                                                                                        'makes '
                                                                                                        'it '
                                                                                                        'stop '
                                                                                                        'rather '
                                                                                                        'than '
                                                                                                        'guess?',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'},
                                                                                              {'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'controller '
                                                                                                        'may '
                                                                                                        'declare '
                                                                                                        'readiness '
                                                                                                        'only '
                                                                                                        'when '
                                                                                                        'deterministic '
                                                                                                        'checks '
                                                                                                        'confirm '
                                                                                                        'that '
                                                                                                        'every '
                                                                                                        'requirement '
                                                                                                        'has '
                                                                                                        'a '
                                                                                                        'provenance-bound '
                                                                                                        'disposition, '
                                                                                                        'all '
                                                                                                        'dependencies '
                                                                                                        'and '
                                                                                                        'contradictions '
                                                                                                        'are '
                                                                                                        'resolved, '
                                                                                                        'all '
                                                                                                        'mandatory '
                                                                                                        'evidence '
                                                                                                        'is '
                                                                                                        'current '
                                                                                                        'and '
                                                                                                        'reproducible, '
                                                                                                        'the '
                                                                                                        'package '
                                                                                                        'passes '
                                                                                                        'schema, '
                                                                                                        'integrity, '
                                                                                                        'and '
                                                                                                        'replay '
                                                                                                        'validation, '
                                                                                                        'and '
                                                                                                        'every '
                                                                                                        'proposed '
                                                                                                        'atom '
                                                                                                        'has '
                                                                                                        'explicit '
                                                                                                        'verification '
                                                                                                        'and '
                                                                                                        'stop '
                                                                                                        'conditions; '
                                                                                                        '`needs_owner` '
                                                                                                        'and '
                                                                                                        '`blocked` '
                                                                                                        'are '
                                                                                                        'valid '
                                                                                                        'resumable '
                                                                                                        'run '
                                                                                                        'outcomes '
                                                                                                        'but '
                                                                                                        'never '
                                                                                                        'readiness, '
                                                                                                        'and '
                                                                                                        'only '
                                                                                                        'the '
                                                                                                        'owner '
                                                                                                        'may '
                                                                                                        'approve '
                                                                                                        'the '
                                                                                                        'resulting '
                                                                                                        'atom '
                                                                                                        'sequence '
                                                                                                        'and '
                                                                                                        'authorize '
                                                                                                        'Atom '
                                                                                                        'Building '
                                                                                                        'Machinery '
                                                                                                        'to '
                                                                                                        'begin.',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]},
                                                                'type': 'requirement'},
                                                               {'id': 'req-e17b44a659f36a19',
                                                                'record': {'disposition': 'blocked',
                                                                           'exact_text': 'The '
                                                                                         'machinery '
                                                                                         'produces '
                                                                                         'a '
                                                                                         'versioned, '
                                                                                         'hash-bound '
                                                                                         'readiness '
                                                                                         'package '
                                                                                         'containing '
                                                                                         'a '
                                                                                         'machine-readable '
                                                                                         'readiness '
                                                                                         'ledger, '
                                                                                         'a '
                                                                                         'requirement-to-evidence-and-dependency '
                                                                                         'graph, '
                                                                                         'and a '
                                                                                         'verdict '
                                                                                         'with '
                                                                                         'reasons '
                                                                                         'for '
                                                                                         'every '
                                                                                         'requirement. '
                                                                                         'While '
                                                                                         'blocked '
                                                                                         'it also '
                                                                                         'contains '
                                                                                         'the '
                                                                                         'ordered '
                                                                                         'unresolved-evidence '
                                                                                         'and '
                                                                                         'owner-decision '
                                                                                         'queue, '
                                                                                         'and when '
                                                                                         'ready it '
                                                                                         'instead '
                                                                                         'contains '
                                                                                         'dependency-ordered, '
                                                                                         'independently '
                                                                                         'testable '
                                                                                         'atom '
                                                                                         'envelopes '
                                                                                         'defining '
                                                                                         'scope, '
                                                                                         'inputs, '
                                                                                         'boundaries, '
                                                                                         'prerequisites, '
                                                                                         'acceptance '
                                                                                         'checks, '
                                                                                         'verification '
                                                                                         'paths, '
                                                                                         'and stop '
                                                                                         'conditions, '
                                                                                         'together '
                                                                                         'with a '
                                                                                         'human-readable '
                                                                                         'report '
                                                                                         'and '
                                                                                         'replay '
                                                                                         'receipt.',
                                                                           'maturity': 'unassessed',
                                                                           'ordinal': 5,
                                                                           'requirement_id': 'req-e17b44a659f36a19',
                                                                           'source_anchors': [{'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'machinery '
                                                                                                        'produces '
                                                                                                        'a '
                                                                                                        'versioned, '
                                                                                                        'hash-bound '
                                                                                                        'readiness '
                                                                                                        'package '
                                                                                                        'containing '
                                                                                                        'a '
                                                                                                        'machine-readable '
                                                                                                        'readiness '
                                                                                                        'ledger, '
                                                                                                        'a '
                                                                                                        'requirement-to-evidence-and-dependency '
                                                                                                        'graph, '
                                                                                                        'and '
                                                                                                        'a '
                                                                                                        'verdict '
                                                                                                        'with '
                                                                                                        'reasons '
                                                                                                        'for '
                                                                                                        'every '
                                                                                                        'requirement; '
                                                                                                        'while '
                                                                                                        'blocked '
                                                                                                        'it '
                                                                                                        'also '
                                                                                                        'contains '
                                                                                                        'the '
                                                                                                        'ordered '
                                                                                                        'unresolved-evidence '
                                                                                                        'and '
                                                                                                        'owner-decision '
                                                                                                        'queue, '
                                                                                                        'and '
                                                                                                        'when '
                                                                                                        'ready '
                                                                                                        'it '
                                                                                                        'instead '
                                                                                                        'contains '
                                                                                                        'dependency-ordered, '
                                                                                                        'independently '
                                                                                                        'testable '
                                                                                                        'atom '
                                                                                                        'envelopes '
                                                                                                        'defining '
                                                                                                        'scope, '
                                                                                                        'inputs, '
                                                                                                        'boundaries, '
                                                                                                        'prerequisites, '
                                                                                                        'acceptance '
                                                                                                        'checks, '
                                                                                                        'verification '
                                                                                                        'paths, '
                                                                                                        'and '
                                                                                                        'stop '
                                                                                                        'conditions, '
                                                                                                        'together '
                                                                                                        'with '
                                                                                                        'a '
                                                                                                        'human-readable '
                                                                                                        'report '
                                                                                                        'and '
                                                                                                        'replay '
                                                                                                        'receipt. '
                                                                                                        '_Source: '
                                                                                                        '`/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ '
                                                                                                        '## '
                                                                                                        'q6 '
                                                                                                        '— '
                                                                                                        'How '
                                                                                                        'does '
                                                                                                        'anybody '
                                                                                                        'tell '
                                                                                                        'it '
                                                                                                        'is '
                                                                                                        'done, '
                                                                                                        'and '
                                                                                                        'who '
                                                                                                        'decides?',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'},
                                                                                              {'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'machinery '
                                                                                                        'produces '
                                                                                                        'a '
                                                                                                        'versioned, '
                                                                                                        'hash-bound '
                                                                                                        'readiness '
                                                                                                        'package '
                                                                                                        'containing '
                                                                                                        'a '
                                                                                                        'machine-readable '
                                                                                                        'readiness '
                                                                                                        'ledger, '
                                                                                                        'a '
                                                                                                        'requirement-to-evidence-and-dependency '
                                                                                                        'graph, '
                                                                                                        'and '
                                                                                                        'a '
                                                                                                        'verdict '
                                                                                                        'with '
                                                                                                        'reasons '
                                                                                                        'for '
                                                                                                        'every '
                                                                                                        'requirement; '
                                                                                                        'while '
                                                                                                        'blocked '
                                                                                                        'it '
                                                                                                        'also '
                                                                                                        'contains '
                                                                                                        'the '
                                                                                                        'ordered '
                                                                                                        'unresolved-evidence '
                                                                                                        'and '
                                                                                                        'owner-decision '
                                                                                                        'queue, '
                                                                                                        'and '
                                                                                                        'when '
                                                                                                        'ready '
                                                                                                        'it '
                                                                                                        'instead '
                                                                                                        'contains '
                                                                                                        'dependency-ordered, '
                                                                                                        'independently '
                                                                                                        'testable '
                                                                                                        'atom '
                                                                                                        'envelopes '
                                                                                                        'defining '
                                                                                                        'scope, '
                                                                                                        'inputs, '
                                                                                                        'boundaries, '
                                                                                                        'prerequisites, '
                                                                                                        'acceptance '
                                                                                                        'checks, '
                                                                                                        'verification '
                                                                                                        'paths, '
                                                                                                        'and '
                                                                                                        'stop '
                                                                                                        'conditions, '
                                                                                                        'together '
                                                                                                        'with '
                                                                                                        'a '
                                                                                                        'human-readable '
                                                                                                        'report '
                                                                                                        'and '
                                                                                                        'replay '
                                                                                                        'receipt.',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]},
                                                                'type': 'requirement'},
                                                               {'id': 'req-e51c9757aeaa8d3d',
                                                                'record': {'disposition': 'blocked',
                                                                           'exact_text': 'The '
                                                                                         'machinery '
                                                                                         'must '
                                                                                         'never '
                                                                                         'invent a '
                                                                                         'requirement, '
                                                                                         'fact, '
                                                                                         'dependency, '
                                                                                         'evidence '
                                                                                         'item, or '
                                                                                         'owner '
                                                                                         'decision; '
                                                                                         'infer '
                                                                                         'legal, '
                                                                                         'business, '
                                                                                         'permission, '
                                                                                         'or '
                                                                                         'promotion '
                                                                                         'authority; '
                                                                                         'inspect '
                                                                                         'an '
                                                                                         'undeclared '
                                                                                         'source; '
                                                                                         'mutate a '
                                                                                         'product '
                                                                                         'system; '
                                                                                         'execute '
                                                                                         'an '
                                                                                         'implementation '
                                                                                         'atom; or '
                                                                                         'allow a '
                                                                                         'model to '
                                                                                         'control '
                                                                                         'identity, '
                                                                                         'ordering, '
                                                                                         'state, '
                                                                                         'validation, '
                                                                                         'or '
                                                                                         'pass/fail '
                                                                                         'decisions. '
                                                                                         'It must '
                                                                                         'stop '
                                                                                         'with an '
                                                                                         'explicit '
                                                                                         'reason '
                                                                                         'and the '
                                                                                         'single '
                                                                                         'next '
                                                                                         'required '
                                                                                         'question '
                                                                                         'whenever '
                                                                                         'an input '
                                                                                         'is '
                                                                                         'missing, '
                                                                                         'inaccessible, '
                                                                                         'stale, '
                                                                                         'unverifiable, '
                                                                                         'provenance-free, '
                                                                                         'or '
                                                                                         'contradictory, '
                                                                                         'model '
                                                                                         'outputs '
                                                                                         'are '
                                                                                         'invalid '
                                                                                         'or '
                                                                                         'disagree '
                                                                                         'beyond '
                                                                                         'deterministic '
                                                                                         'rules, '
                                                                                         'required '
                                                                                         'authority '
                                                                                         'is '
                                                                                         'absent, '
                                                                                         'or any '
                                                                                         'readiness '
                                                                                         'invariant '
                                                                                         'fails.',
                                                                           'maturity': 'unassessed',
                                                                           'ordinal': 3,
                                                                           'requirement_id': 'req-e51c9757aeaa8d3d',
                                                                           'source_anchors': [{'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'machinery '
                                                                                                        'must '
                                                                                                        'never '
                                                                                                        'invent '
                                                                                                        'a '
                                                                                                        'requirement, '
                                                                                                        'fact, '
                                                                                                        'dependency, '
                                                                                                        'evidence '
                                                                                                        'item, '
                                                                                                        'or '
                                                                                                        'owner '
                                                                                                        'decision; '
                                                                                                        'infer '
                                                                                                        'legal, '
                                                                                                        'business, '
                                                                                                        'permission, '
                                                                                                        'or '
                                                                                                        'promotion '
                                                                                                        'authority; '
                                                                                                        'inspect '
                                                                                                        'an '
                                                                                                        'undeclared '
                                                                                                        'source; '
                                                                                                        'mutate '
                                                                                                        'a '
                                                                                                        'product '
                                                                                                        'system; '
                                                                                                        'execute '
                                                                                                        'an '
                                                                                                        'implementation '
                                                                                                        'atom; '
                                                                                                        'or '
                                                                                                        'allow '
                                                                                                        'a '
                                                                                                        'model '
                                                                                                        'to '
                                                                                                        'control '
                                                                                                        'identity, '
                                                                                                        'ordering, '
                                                                                                        'state, '
                                                                                                        'validation, '
                                                                                                        'or '
                                                                                                        'pass/fail '
                                                                                                        'decisions, '
                                                                                                        'and '
                                                                                                        'it '
                                                                                                        'must '
                                                                                                        'stop '
                                                                                                        'with '
                                                                                                        'an '
                                                                                                        'explicit '
                                                                                                        'reason '
                                                                                                        'and '
                                                                                                        'the '
                                                                                                        'single '
                                                                                                        'next '
                                                                                                        'required '
                                                                                                        'question '
                                                                                                        'whenever '
                                                                                                        'an '
                                                                                                        'input '
                                                                                                        'is '
                                                                                                        'missing, '
                                                                                                        'inaccessible, '
                                                                                                        'stale, '
                                                                                                        'unverifiable, '
                                                                                                        'provenance-free, '
                                                                                                        'or '
                                                                                                        'contradictory, '
                                                                                                        'model '
                                                                                                        'outputs '
                                                                                                        'are '
                                                                                                        'invalid '
                                                                                                        'or '
                                                                                                        'disagree '
                                                                                                        'beyond '
                                                                                                        'deterministic '
                                                                                                        'rules, '
                                                                                                        'required '
                                                                                                        'authority '
                                                                                                        'is '
                                                                                                        'absent, '
                                                                                                        'or '
                                                                                                        'any '
                                                                                                        'readiness '
                                                                                                        'invariant '
                                                                                                        'fails. '
                                                                                                        '_Source: '
                                                                                                        '`/Users/kamenkamenov/memory-knowledge/Tasks/requirement-to-atom-readiness-machinery/sources/owner-answers-v4.md`_ '
                                                                                                        '## '
                                                                                                        'q8 '
                                                                                                        '— '
                                                                                                        'What '
                                                                                                        'is '
                                                                                                        'deliberately '
                                                                                                        'not '
                                                                                                        'settled '
                                                                                                        'here, '
                                                                                                        'and '
                                                                                                        'left '
                                                                                                        'to '
                                                                                                        'whoever '
                                                                                                        'builds '
                                                                                                        'it?',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'},
                                                                                              {'piece_id': 'p-0001',
                                                                                               'quote': 'The '
                                                                                                        'machinery '
                                                                                                        'must '
                                                                                                        'never '
                                                                                                        'invent '
                                                                                                        'a '
                                                                                                        'requirement, '
                                                                                                        'fact, '
                                                                                                        'dependency, '
                                                                                                        'evidence '
                                                                                                        'item, '
                                                                                                        'or '
                                                                                                        'owner '
                                                                                                        'decision; '
                                                                                                        'infer '
                                                                                                        'legal, '
                                                                                                        'business, '
                                                                                                        'permission, '
                                                                                                        'or '
                                                                                                        'promotion '
                                                                                                        'authority; '
                                                                                                        'inspect '
                                                                                                        'an '
                                                                                                        'undeclared '
                                                                                                        'source; '
                                                                                                        'mutate '
                                                                                                        'a '
                                                                                                        'product '
                                                                                                        'system; '
                                                                                                        'execute '
                                                                                                        'an '
                                                                                                        'implementation '
                                                                                                        'atom; '
                                                                                                        'or '
                                                                                                        'allow '
                                                                                                        'a '
                                                                                                        'model '
                                                                                                        'to '
                                                                                                        'control '
                                                                                                        'identity, '
                                                                                                        'ordering, '
                                                                                                        'state, '
                                                                                                        'validation, '
                                                                                                        'or '
                                                                                                        'pass/fail '
                                                                                                        'decisions, '
                                                                                                        'and '
                                                                                                        'it '
                                                                                                        'must '
                                                                                                        'stop '
                                                                                                        'with '
                                                                                                        'an '
                                                                                                        'explicit '
                                                                                                        'reason '
                                                                                                        'and '
                                                                                                        'the '
                                                                                                        'single '
                                                                                                        'next '
                                                                                                        'required '
                                                                                                        'question '
                                                                                                        'whenever '
                                                                                                        'an '
                                                                                                        'input '
                                                                                                        'is '
                                                                                                        'missing, '
                                                                                                        'inaccessible, '
                                                                                                        'stale, '
                                                                                                        'unverifiable, '
                                                                                                        'provenance-free, '
                                                                                                        'or '
                                                                                                        'contradictory, '
                                                                                                        'model '
                                                                                                        'outputs '
                                                                                                        'are '
                                                                                                        'invalid '
                                                                                                        'or '
                                                                                                        'disagree '
                                                                                                        'beyond '
                                                                                                        'deterministic '
                                                                                                        'rules, '
                                                                                                        'required '
                                                                                                        'authority '
                                                                                                        'is '
                                                                                                        'absent, '
                                                                                                        'or '
                                                                                                        'any '
                                                                                                        'readiness '
                                                                                                        'invariant '
                                                                                                        'fails.',
                                                                                               'sha256': '582d1b751894c0367fa0a8f42b028e7f3f7ea8702ac566ec0e5f111160423d60'}]},
                                                                'type': 'requirement'}]},
                             'semantic_payload_sha256': '1cff3cbfe9eaba36371bad33b9771647530f043a1ffa3600ec2b70fd1f74e6d2',
                             'timeout_ms': 300000},
                'response_schema': {'additionalProperties': False,
                                    'properties': {'attempt': {'const': 1,
                                                               'maximum': 2,
                                                               'minimum': 1,
                                                               'type': 'integer'},
                                                   'criteria': {'items': {'additionalProperties': False,
                                                                          'properties': {'criterion_id': {'enum': ['independent-evaluator'],
                                                                                                          'maxLength': 8192,
                                                                                                          'minLength': 1,
                                                                                                          'pattern': '\\S',
                                                                                                          'type': 'string'},
                                                                                         'evidence_ids': {'items': {'maxLength': 8192,
                                                                                                                    'minLength': 1,
                                                                                                                    'pattern': '\\S',
                                                                                                                    'type': 'string'},
                                                                                                          'maxItems': 256,
                                                                                                          'minItems': 1,
                                                                                                          'type': 'array',
                                                                                                          'uniqueItems': True},
                                                                                         'reason': {'maxLength': 8192,
                                                                                                    'minLength': 1,
                                                                                                    'pattern': '\\S',
                                                                                                    'type': 'string'},
                                                                                         'verdict': {'enum': ['satisfied',
                                                                                                              'unsatisfied',
                                                                                                              'cannot_assess'],
                                                                                                     'type': 'string'}},
                                                                          'required': ['criterion_id',
                                                                                       'verdict',
                                                                                       'evidence_ids',
                                                                                       'reason'],
                                                                          'type': 'object'},
                                                                'maxItems': 256,
                                                                'minItems': 1,
                                                                'type': 'array'},
                                                   'envelope_sha256': {'const': 'e3336d10592d6b64420c33a252254c7eed4bf6d62676a1c35334d4ac75409575',
                                                                       'pattern': '^[0-9a-f]{64}$',
                                                                       'type': 'string'},
                                                   'evidence_ids': {'items': {'enum': ['telemetry-review'],
                                                                              'maxLength': 8192,
                                                                              'minLength': 1,
                                                                              'pattern': '\\S',
                                                                              'type': 'string'},
                                                                    'maxItems': 256,
                                                                    'minItems': 1,
                                                                    'type': 'array',
                                                                    'uniqueItems': True},
                                                   'family': {'const': 'verification-adequacy',
                                                              'type': 'string'},
                                                   'node_id': {'const': 'condition-c80e6a40f897a45920b67b6b',
                                                               'maxLength': 8192,
                                                               'minLength': 1,
                                                               'pattern': '\\S',
                                                               'type': 'string'},
                                                   'quotes': {'items': {'additionalProperties': False,
                                                                        'properties': {'evidence_id': {'maxLength': 8192,
                                                                                                       'minLength': 1,
                                                                                                       'pattern': '\\S',
                                                                                                       'type': 'string'},
                                                                                       'quote': {'maxLength': 8192,
                                                                                                 'minLength': 1,
                                                                                                 'pattern': '\\S',
                                                                                                 'type': 'string'}},
                                                                        'required': ['evidence_id',
                                                                                     'quote'],
                                                                        'type': 'object'},
                                                              'maxItems': 256,
                                                              'minItems': 1,
                                                              'type': 'array',
                                                              'uniqueItems': True},
                                                   'reason': {'maxLength': 8192,
                                                              'minLength': 1,
                                                              'pattern': '\\S',
                                                              'type': 'string'},
                                                   'run_id': {'const': '33c3041f552c138e5aa73c9c79ecad71c7627564f8df4174e95889da705a8863',
                                                              'pattern': '^[0-9a-f]{64}$',
                                                              'type': 'string'},
                                                   'schema_version': {'const': 1,
                                                                      'type': 'integer'},
                                                   'seat': {'const': 'seat-2',
                                                            'enum': ['seat-1', 'seat-2'],
                                                            'type': 'string'},
                                                   'verdict': {'enum': ['adequate',
                                                                        'inadequate',
                                                                        'cannot_assess'],
                                                               'type': 'string'}},
                                    'required': ['schema_version',
                                                 'run_id',
                                                 'node_id',
                                                 'family',
                                                 'attempt',
                                                 'seat',
                                                 'envelope_sha256',
                                                 'verdict',
                                                 'evidence_ids',
                                                 'quotes',
                                                 'reason',
                                                 'criteria'],
                                    'type': 'object'}}],
 'family': 'verification-adequacy',
 'node_id': 'condition-c80e6a40f897a45920b67b6b'}
    captured_responses = [{'attempt': 1,
  'criteria': [{'criterion_id': 'independent-evaluator',
                'evidence_ids': ['telemetry-review'],
                'reason': 'The excerpt explicitly states that evaluation and final assessment can '
                          "trust the candidate's own verdict and that the candidate can grade "
                          'itself.',
                'verdict': 'unsatisfied'}],
  'envelope_sha256': 'db300c0d93eb60f4e0df137d409445c64f57200047d0063fc8d6efd66d9f5213',
  'evidence_ids': ['telemetry-review'],
  'family': 'verification-adequacy',
  'node_id': 'condition-c80e6a40f897a45920b67b6b',
  'quotes': [{'evidence_id': 'telemetry-review',
              'quote': "| 6 | Evaluation and final assessment can trust the candidate's own "
                       'verdict | Critical | A candidate can effectively grade itself |'}],
  'reason': 'The excerpt explicitly states that evaluation and final assessment can trust the '
            "candidate's own verdict and that the candidate can grade itself.",
  'run_id': '33c3041f552c138e5aa73c9c79ecad71c7627564f8df4174e95889da705a8863',
  'schema_version': 1,
  'seat': 'seat-1',
  'verdict': 'inadequate'},
 {'attempt': 1,
  'criteria': [{'criterion_id': 'independent-evaluator',
                'evidence_ids': ['telemetry-review'],
                'reason': 'The excerpt explicitly states that evaluation and final assessment can '
                          "trust the candidate's own verdict and that the candidate can grade "
                          'itself.',
                'verdict': 'unsatisfied'}],
  'envelope_sha256': 'e3336d10592d6b64420c33a252254c7eed4bf6d62676a1c35334d4ac75409575',
  'evidence_ids': ['telemetry-review'],
  'family': 'verification-adequacy',
  'node_id': 'condition-c80e6a40f897a45920b67b6b',
  'quotes': [{'evidence_id': 'telemetry-review',
              'quote': "| 6 | Evaluation and final assessment can trust the candidate's own "
                       'verdict | Critical | A candidate can effectively grade itself |'}],
  'reason': 'The excerpt explicitly states that evaluation and final assessment can trust the '
            "candidate's own verdict and that the candidate can grade itself.",
  'run_id': '33c3041f552c138e5aa73c9c79ecad71c7627564f8df4174e95889da705a8863',
  'schema_version': 1,
  'seat': 'seat-2',
  'verdict': 'inadequate'}]

    def test_seven_closed_family_contracts_and_projection(self):
        import jsonschema
        module = self.module
        self.assertEqual(len(module.FAMILY_VERDICTS), 7)
        schema = module.model_response_schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertEqual(schema, json.loads((ROOT / 'skills/requirement-to-atom-readiness-machinery/schemas/model-response.schema.json').read_text()))
        for family in module.FAMILY_VERDICTS:
            child = module.family_response_schema(family)
            self.assertFalse(child['additionalProperties'])
            self.assertEqual(set(child['required']), set(child['properties']))
            self.assertNotIn('cannot_assess', module.PROPOSED_FACTS[family])
            child['properties']['evidence_ids']['items']['enum'] = ['telemetry-review']
            self.assertNotIn('enum', child['properties']['node_id'])
            self.assertNotIn('enum', child['properties']['reason'])

    def test_captured_matching_pair_proposes_only_one_fact(self):
        result = self.module.evaluate_submission(self.captured_pending, self.module.canonical(self.captured_responses), None)
        self.assertEqual(result['status'], 'admitted')
        self.assertEqual(result['fact']['fact_type'], 'verification-adequacy:inadequate')
        self.assertEqual(result['fact']['authority'], 'proposed-only')
        self.assertNotIn('readiness', result['fact'])

    def test_captured_pair_rejection_mutations(self):
        import copy
        for name in ('missing', 'duplicate', 'foreign', 'unsupported', 'disagreeing', 'criterion', 'authority', 'cannot-assess'):
            rows = copy.deepcopy(self.captured_responses)
            if name == 'missing': rows.pop()
            if name == 'duplicate': rows[1] = rows[0]
            if name == 'foreign': rows[0]['evidence_ids'] = ['foreign']
            if name == 'unsupported': rows[0]['quotes'][0]['quote'] = 'not in evidence'
            if name == 'disagreeing':
                rows[1]['verdict'] = 'adequate'
                rows[1]['criteria'][0]['verdict'] = 'satisfied'
            if name == 'criterion': rows[0]['criteria'] = []
            if name == 'authority': rows[0]['approved'] = True
            if name == 'cannot-assess': rows[0]['verdict'] = 'cannot_assess'
            with self.subTest(name=name):
                result = self.module.evaluate_submission(self.captured_pending, self.module.canonical(rows), None)
                self.assertEqual(result['status'], 'rejected')
                self.assertIsNone(result['fact'])
                self.assertTrue(result['rejection'])

    def test_malformed_and_unprepared_submissions_are_retained_rejections(self):
        for pending, raw in ((self.captured_pending, b'{'), (None, self.module.canonical(self.captured_responses))):
            result = self.module.evaluate_submission(pending, raw, None)
            self.assertEqual(result['status'], 'rejected')
            self.assertIsNone(result['fact'])

    def test_response_bounds_and_closed_nested_criteria(self):
        import copy
        schema = self.captured_pending['envelopes'][0]['response_schema']
        for mutation in ('extra-field', 'too-many', 'bad-attempt', 'bool-attempt'):
            row = copy.deepcopy(self.captured_responses[0])
            if mutation == 'extra-field': row['criteria'][0]['permission'] = 'approved'
            if mutation == 'too-many': row['evidence_ids'] = ['telemetry-review'] * 257
            if mutation == 'bad-attempt': row['attempt'] = 3
            if mutation == 'bool-attempt': row['attempt'] = True
            with self.subTest(mutation=mutation), self.assertRaises(self.module.Refused):
                self.module.validate_shape(row, schema)


    def test_interview_journal_rejects_equal_valued_wrong_json_types(self):
        import base64, copy, tempfile
        module = self.module
        # Exercise the journal seam with code-created state and the captured response bytes.
        events = module.chain([('run_started', {'interview_state': module.initial_interview_state()})])
        raw = module.canonical(self.captured_responses)
        payload = {'submission_base64': base64.b64encode(raw).decode(), 'submission_sha256': module.digest(raw),
                   'result': module.evaluate_submission(None, raw, None)}
        event = module.chain([(e['event'], e['payload']) for e in events] + [('interview_rejected', payload)])[-1]
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory).resolve()
            transaction = work / 'run/interviews/00000001'
            transaction.mkdir(parents=True)
            head = work / 'run/interview-head.json'
            head.write_bytes(module.canonical({'ledger_tip': event['sha256'], 'event_count': 2}) + b'\n')
            path = transaction / 'event.json'
            path.write_bytes(module.canonical(event) + b'\n')
            state, _, _ = module.replay_interviews(work, copy.deepcopy(events), {}, None)
            self.assertEqual(len(state['rejections']), 1)
            for key, value in [('schema_version', True), ('sequence', 2.0)]:
                changed = copy.deepcopy(event)
                changed[key] = value
                path.write_bytes(module.canonical(changed) + b'\n')
                with self.subTest(key=key), self.assertRaises(module.Refused):
                    module.replay_interviews(work, copy.deepcopy(events), {}, None)
