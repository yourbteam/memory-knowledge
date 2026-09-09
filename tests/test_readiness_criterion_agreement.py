"""Real paid response reproduction; rejection changes are labeled mutations."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class CriterionAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('criterion_kernel',ROOT/'skills/requirement-to-atom-readiness-machinery/scripts/readiness_controller.py')
        cls.kernel=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.kernel)
        cls.capture=json.loads((ROOT/'tests/fixtures/readiness-criterion-agreement.json').read_bytes())

    def evaluate(self, rows=None, pending=None):
        k=self.kernel
        return k.evaluate_submission(pending or self.capture['pending'],
            k.canonical(rows if rows is not None else self.capture['responses']),None)

    def test_exact_live_pair_accepts_conclusions_preserves_both_citation_sets(self):
        before=self.kernel.canonical(self.capture)
        result=self.evaluate()
        self.assertEqual(result['status'],'admitted',result)
        fact=result['fact']
        self.assertEqual(fact['authority'],'proposed-only')
        self.assertEqual(fact['criteria'],[{'criterion_id':'complete-requirement-1','verdict':'satisfied'}])
        expected=[{'seat':row['seat'],'criteria':[{'criterion_id':c['criterion_id'],'evidence_ids':c['evidence_ids']} for c in row['criteria']]} for row in self.capture['responses']]
        self.assertEqual(fact['criterion_evidence_by_seat'],expected)
        self.assertNotEqual(expected[0]['criteria'],expected[1]['criteria'])
        self.assertEqual(before,self.kernel.canonical(self.capture))

    def test_citation_order_does_not_change_conclusion_or_lose_attribution(self):
        rows=copy.deepcopy(self.capture['responses'])
        rows[1]['criteria'][0]['evidence_ids'].reverse()
        result=self.evaluate(rows)
        self.assertEqual(result['status'],'admitted')
        self.assertEqual(result['fact']['criterion_evidence_by_seat'][1]['criteria'][0]['evidence_ids'],rows[1]['criteria'][0]['evidence_ids'])

    def test_invalid_evidence_and_genuine_disagreement_still_block(self):
        for change in ('foreign-citation','empty-citations','duplicate-citation','wrong-quote',
                       'missing-overall-evidence','missing-criterion','wrong-criterion',
                       'disagreement','cannot-assess','positive-with-negative-criterion','duplicate-seat'):
            with self.subTest(change=change):
                rows=copy.deepcopy(self.capture['responses']);row=rows[1]
                if change=='foreign-citation':row['criteria'][0]['evidence_ids']=['foreign']
                elif change=='empty-citations':row['criteria'][0]['evidence_ids']=[]
                elif change=='duplicate-citation':row['criteria'][0]['evidence_ids']*=2
                elif change=='wrong-quote':row['quotes'][0]['quote']='not captured'
                elif change=='missing-overall-evidence':row['evidence_ids'].pop()
                elif change=='missing-criterion':row['criteria']=[]
                elif change=='wrong-criterion':row['criteria'][0]['criterion_id']='foreign'
                elif change=='disagreement':
                    row['verdict']='insufficient';row['criteria'][0]['verdict']='unsatisfied'
                elif change=='cannot-assess':row['criteria'][0]['verdict']='cannot_assess'
                elif change=='positive-with-negative-criterion':row['criteria'][0]['verdict']='unsatisfied'
                elif change=='duplicate-seat':rows[1]=rows[0]
                result=self.evaluate(rows)
                self.assertEqual(result['status'],'rejected',result)
                self.assertIsNone(result['fact'])

    def test_same_contract_applies_to_verification_adequacy(self):
        # Family transport mutation only; not a new adequacy judgment.
        k=self.kernel;pending=copy.deepcopy(self.capture['pending']);rows=copy.deepcopy(self.capture['responses'])
        pending['family']='verification-adequacy'
        for seat,row in zip(pending['envelopes'],rows):
            seat['envelope']['family']='verification-adequacy'
            seat['envelope']['semantic_payload']['family']='verification-adequacy'
            seat['envelope']['semantic_payload']['required_maturity']='not-applicable'
            seat['response_schema']['properties']['family']['const']='verification-adequacy'
            seat['response_schema']['properties']['verdict']['enum']=list(k.FAMILY_VERDICTS['verification-adequacy'])
            row['family']='verification-adequacy';row['verdict']='adequate'
        result=self.evaluate(rows,pending)
        self.assertEqual(result['status'],'admitted')
        self.assertEqual(result['fact']['fact_type'],'verification-adequacy:adequate')
        rows[1]['verdict']='inadequate';rows[1]['criteria'][0]['verdict']='unsatisfied'
        self.assertEqual(self.evaluate(rows,pending)['status'],'rejected')

    def test_matching_negative_answers_do_not_become_positive(self):
        rows=copy.deepcopy(self.capture['responses'])
        for row in rows:
            row['verdict']='insufficient';row['criteria'][0]['verdict']='unsatisfied'
        result=self.evaluate(rows)
        self.assertEqual(result['status'],'admitted')
        self.assertEqual(result['fact']['fact_type'],'evidence-sufficiency:insufficient')
        self.assertEqual(result['fact']['criteria'][0]['verdict'],'unsatisfied')

if __name__=='__main__':
    unittest.main()
