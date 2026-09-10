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
                "minifier": {"name": "Minify++", "version": "1.1.2", "version_string": "Minify++ 1.1.2", "commit": "a"*40},
                "oracle": runner.oracle_identity(), "generated_at": "2026-01-01T00:00:00Z"}
        # Ensure the oracle carries its required fields so the propagation test
        # is independent of the local runtime/oracle availability.
        required = {"json": ("name","implementation","python_version","parser"),
                    "jsx": ("name","node","typescript"),
                    "svg": ("name","version","libxml2"), "xml": ("name","version","libxml2")}[runner.FORMAT]
        for k in required:
            if not base["oracle"].get(k): base["oracle"][k] = "test"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td/"res.json").write_text(json.dumps(base))
            (td/"pub.json").write_text(json.dumps(base))
            (td/"index.html").write_text("<h1>ok</h1>")
            runner.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")
            bad = dict(base); bad["minifier"] = {"name": "Minify++", "version": "1.1.1", "commit": "b"*40}
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



def test_validate_identity_rejects_incomplete(self):
    import copy
    base = {"minifier": {"name": "Minify++", "version": "1.1.2", "version_string": "Minify++ 1.1.2", "commit": "a"*40},
            "oracle": runner.oracle_identity()}
    # missing identity object
    with self.assertRaises(SystemExit): runner.validate_identity({"oracle": base["oracle"]})
    # empty identity object
    with self.assertRaises(SystemExit): runner.validate_identity({"minifier": {}, "oracle": base["oracle"]})
    # empty required field
    bad = copy.deepcopy(base); bad["minifier"]["version_string"] = ""
    with self.assertRaises(SystemExit): runner.validate_identity(bad)
    # missing / malformed commit
    bad = copy.deepcopy(base); bad["minifier"]["commit"] = ""
    with self.assertRaises(SystemExit): runner.validate_identity(bad)
    bad = copy.deepcopy(base); bad["minifier"]["commit"] = "zz"
    with self.assertRaises(SystemExit): runner.validate_identity(bad)
    # oracle missing a format-specific field
    bad = copy.deepcopy(base); bad["oracle"] = {"name": "x"}
    with self.assertRaises(SystemExit): runner.validate_identity(bad)
    # expected commit mismatch
    with self.assertRaises(SystemExit): runner.validate_identity(base, expected_commit="f"*40)

def test_dashboard_rejects_matching_empty_identity(self):
    import tempfile
    empty = {"counts": {"pass": 1}, "source_revisions": {}, "minifier": {}, "oracle": {}, "generated_at": "2026-01-01T00:00:00Z"}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td/"res.json").write_text(json.dumps(empty))
        (td/"pub.json").write_text(json.dumps(empty))
        (td/"index.html").write_text("<h1>ok</h1>")
        with self.assertRaises(SystemExit):
            runner.verify_dashboard(td/"res.json", td/"index.html", td/"pub.json")

if __name__=="__main__": unittest.main()
