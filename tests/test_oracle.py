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


class IdentityTests(unittest.TestCase):
    def test_oracle_identity_fields(self):
        o = runner.oracle_identity()
        self.assertTrue(isinstance(o, dict) and o, "oracle identity must be non-empty")
        self.assertIn("name", o)
        self.assertTrue(o["name"])
        if runner.FORMAT == "json":
            self.assertIn("python_version", o)
        elif runner.FORMAT == "jsx":
            self.assertIn("typescript", o)
        else:
            self.assertIn("libxml2", o)

    def test_dashboard_identity_propagation(self):
        import tempfile
        base = {"counts": {"pass": 1}, "source_revisions": {},
                "minifier": {"name": "Minify++", "version": "1.1.2", "commit": "x"*40},
                "oracle": {"name": "o", "version": "1"}, "generated_at": "2026-01-01T00:00:00Z"}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td/"res.json").write_text(json.dumps(base))
            (td/"pub.json").write_text(json.dumps(base))
            (td/"index.html").write_text("<h1>ok</h1>")
            runner.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")
            bad = dict(base); bad["minifier"] = {"name": "Minify++", "version": "1.1.1", "commit": "y"*40}
            (td/"pub.json").write_text(json.dumps(bad))
            with self.assertRaises(SystemExit):
                runner.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")

    def test_minifier_identity_reads_git_commit(self):
        import subprocess, tempfile, os
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=td, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=td, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=td, check=True)
            exe = td/"minify"
            exe.write_text("#!/bin/sh\necho 'Minify++ 1.1.2'\n")
            exe.chmod(0o755)
            subprocess.run(["git", "add", "minify"], cwd=td, check=True)
            subprocess.run(["git", "commit", "-qm", "c"], cwd=td, check=True)
            ident = runner.minifier_identity(exe)
            self.assertEqual(ident["name"], "Minify++")
            self.assertEqual(ident["version"], "1.1.2")
            self.assertTrue(ident["commit"])

if __name__=="__main__": unittest.main()
