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
