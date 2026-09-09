import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("runner",ROOT/"tools/conformance.py")
runner=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)

class OracleTests(unittest.TestCase):
    def test_smoke_sources_are_nonempty(self):
        self.assertTrue(all(c["text"] for c in runner.smoke_cases()))

    def test_xml_trivia_between_elements_is_significant(self):
        self.assertEqual(runner.compare("<r><a/> <b/></r>","<r><a/><b/></r>")[0],"semantic-difference")

    def test_namespace_document_passes(self):
        text='<r xmlns:x="urn:x"><x:a v="1"/></r>'
        self.assertEqual(runner.compare(text,text)[0],"pass")

    def test_doctype_is_outside_contract(self):
        with self.assertRaises(ValueError): runner.xml_value("<!DOCTYPE r><r/>")
if __name__=="__main__": unittest.main()
