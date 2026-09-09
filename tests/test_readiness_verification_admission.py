"""Captured graph subcase plus explicitly constructed admission-boundary mutations.

The source document is a verification declaration, NOT a claimed completed run.
Every test pins that distinction: importing it must leave status blocked.
"""
import copy
import importlib.util
import json
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VerificationAdmissionTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'skills/requirement-to-atom-readiness-machinery/scripts/evidence_adapter.py'
        spec = importlib.util.spec_from_file_location('verification_admission', path)
        self.a = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.a)
        capture = runpy.run_path(str(ROOT / 'tests/test_requirement_to_atom_readiness.py'))
        graph = capture['EvidenceGraphRuntimeTests'].captured_graph
        self.requirements = [{k:v for k,v in n['record'].items() if k not in ('maturity','disposition')}
                             for n in graph['nodes'] if n['type']=='requirement']
        ids = [r['requirement_id'] for r in self.requirements]
        original = next(n['record'] for n in graph['nodes'] if n['type']=='verification')
        # Capture current checked-in test bytes as the declared case source. This
        # asserts provenance mechanics, not that these cases satisfy the feature.
        raw = (ROOT/'tests/test_requirement_to_atom_readiness.py').read_bytes()
        self.sources = {'case-source':raw, 'condition-source':original['observable'].encode()}
        self.document = {'requirement_ids':ids, 'record':{
            'observable':original['observable'],
            'success_cases':['a09-success-one-external-action'],
            'rejection_cases':['a09-failure-wrong-answer-or-skill-routing'],
            'execution_route':'scripts/run_pytest.sh tests/test_requirement_to_atom_readiness.py -q',
            'independence_rule':'independent'},
            'captured_cases':[{'case_id':ident,'kind':kind,'source_id':'case-source',
                              'sha256':self.a.digest(raw)} for ident,kind in [
                ('a09-success-one-external-action','success'),
                ('a09-failure-wrong-answer-or-skill-routing','failure')]]}
        self.condition = {'condition_id':'captured-verification-admission',
            'resolution_class':'verification','source_id':'condition-source',
            'source_quote':original['observable'],'requirement_ids':ids,
            'recovery_condition':'Assess the declared verification independently.', 'dependencies':[],
            'verification':{'source_id':'verification-source','pointer':''}}

    def build(self, document=None, condition=None, raw=None):
        a = self.a
        sources = {**self.sources, 'verification-source':raw if raw is not None else a.canonical(
            self.document if document is None else document)}
        files = [{'id':key,'path':'/captured/'+key,'sha256':a.digest(value),'size':len(value)}
                 for key,value in sources.items()]
        manifest = {'schema_version':1,'kind':'evidence','requirements_handoff_sha256':'a'*64,
            'source_files':files,'requirement_bindings':[],'evidence':[],
            'conditions':[self.condition if condition is None else condition],'edges':[]}
        def read(path, expected):
            value = sources[path.name]
            assert a.digest(value)==expected
            return value
        return a.build_graph([manifest], {'requirements':self.requirements,'handoff_sha256':'a'*64,
            'current_document_sha256':'b'*64},read,'2026-09-08T00:00:00+00:00')

    def test_import_preserves_declaration_without_certification(self):
        for independence in ('independent','producer-only','unassessed'):
            with self.subTest(independence=independence):
                doc = copy.deepcopy(self.document)
                doc['record']['independence_rule']=independence
                result = self.build(doc)
                node = next(n for n in result['graph']['nodes'] if n['type']=='verification')
                self.assertEqual(node['record'],{**doc['record'],'status':'blocked'})
                self.assertEqual(result['readiness'],'not-assessed')
                self.assertEqual(len(result['queue']),1)
                self.assertEqual(result,self.build(doc))

    def test_legacy_retains_explicit_incompleteness(self):
        condition=copy.deepcopy(self.condition);del condition['verification']
        result=self.build(condition=condition)
        record=next(n['record'] for n in result['graph']['nodes'] if n['type']=='verification')
        self.assertEqual((record['success_cases'],record['rejection_cases'],record['independence_rule'],record['status']),
                         ([],[],'unassessed','blocked'))

    def test_rejects_unsupported_verification(self):
        changes=[('success_cases',[]),('success_cases',['foreign']),
                 ('rejection_cases',self.document['record']['success_cases']),
                 ('status','verified'),('independence_rule','approved')]
        for field,value in changes:
            with self.subTest(field=field,value=value):
                doc=copy.deepcopy(self.document);doc['record'][field]=value
                with self.assertRaises(self.a.EvidenceRefused):self.build(doc)
        for field,value in [('sha256','0'*64),('source_id','foreign'),('case_id','foreign'),('kind','failure')]:
            with self.subTest(case_field=field):
                doc=copy.deepcopy(self.document);doc['captured_cases'][0][field]=value
                with self.assertRaises(self.a.EvidenceRefused):self.build(doc)
        doc=copy.deepcopy(self.document);doc['requirement_ids']=['foreign']
        with self.assertRaises(self.a.EvidenceRefused):self.build(doc)

    def test_rejects_unresolved_pointer_duplicate_json_and_wrong_route(self):
        for pointer in ('/missing','/~2','/record/success_cases/-1','/record/success_cases/00'):
            with self.subTest(pointer=pointer):
                condition=copy.deepcopy(self.condition);condition['verification']['pointer']=pointer
                with self.assertRaises(self.a.EvidenceRefused):self.build(condition=condition)
        raw=self.a.canonical(self.document).decode().replace('"independence_rule":"independent"',
                '"independence_rule":"independent","independence_rule":"independent"').encode()
        with self.assertRaises(self.a.EvidenceRefused):self.build(raw=raw)
        condition=copy.deepcopy(self.condition);condition['resolution_class']='owner-decision'
        with self.assertRaises(self.a.EvidenceRefused):self.build(condition=condition)

    def test_published_input_contract_matches_runtime(self):
        schema=json.loads((ROOT/'skills/requirement-to-atom-readiness-machinery/schemas/evidence-manifest.schema.json').read_text())
        self.assertEqual(schema,self.a.evidence_schema())
        self.a.validate(self.document,schema['$defs']['verification_document'])
