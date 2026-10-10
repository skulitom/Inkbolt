"""Registry evidence and generated report stay synchronized with the engine."""
import json
import unittest
import test_editing_cli as editing
from test_cli import ROOT


class ImplementationRegistryTests(unittest.TestCase):
    invoke = editing.EditingCliTests.invoke

    def test_implementation_registry(self):
        registry=json.loads((ROOT/"docs/features.json").read_text(encoding="utf8"))
        evidence_paths={p.relative_to(ROOT).as_posix() for p in [
            *(ROOT/'src').rglob('*.rs'),*(ROOT/'tests').rglob('*.rs'),
            *(ROOT/'tests').rglob('*.py')]}
        self.assertEqual(self.invoke(dict(command="implementation.status")),registry)
        self.assertEqual(registry["target"],167)
        self.assertEqual(len(registry["features"]),167)
        self.assertEqual(len({f["id"] for f in registry["features"]}),167)
        verified=[f for f in registry["features"] if f["status"]=="verified"]
        self.assertEqual(registry["verified"],len(verified))
        self.assertAlmostEqual(registry["percent"],len(verified)/167*100,places=6)
        for feature in registry["features"]:
            self.assertIn(feature["status"],("planned","in_progress","verified"))
            self.assertTrue(feature["acceptance"])
        for feature in verified:
            self.assertTrue(feature["evidence"])
            for evidence in feature["evidence"]:
                path,test=evidence.split("::")
                self.assertIn(path,evidence_paths)
                self.assertIn(test,(ROOT/path).read_text(encoding="utf8"))
        import importlib.util
        spec=importlib.util.spec_from_file_location("implementation_report",ROOT/"tools/update_report.py")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual((ROOT/"docs/IMPLEMENTATION.md").read_text(encoding="utf8"),module.report(registry))



if __name__ == "__main__":
    unittest.main()
