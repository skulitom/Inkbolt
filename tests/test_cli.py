import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXE = Path(os.environ.get("INKBOLT_EXE", ROOT / "target/debug" / ("inkbolt.exe" if os.name == "nt" else "inkbolt")))


class CliTests(unittest.TestCase):
    def invoke(self, payload=b"", *args):
        process = subprocess.run([str(EXE), *args], input=payload, capture_output=True, timeout=10)
        self.assertEqual(process.stderr, b"")
        self.assertEqual(len(process.stdout.splitlines()), 1)
        return process.returncode, json.loads(process.stdout)

    def test_examples_and_validation(self):
        for name, kind in [("create-vector.json", "vector"), ("create-raster.json", "raster")]:
            code, response = self.invoke(b"", str(ROOT / "examples" / name))
            self.assertEqual(code, 0)
            self.assertEqual(response["result"]["kind"], kind)
            code, validated = self.invoke(json.dumps({"command": "document.validate", "document": response["result"]}).encode())
            self.assertEqual(code, 0)
            self.assertEqual(response, validated)

    def test_capabilities_and_schema(self):
        code, response = self.invoke(b"", "capabilities")
        self.assertEqual(code, 0)
        self.assertTrue(response["result"]["features"]["editing"])
        self.assertTrue(response["result"]["features"]["sessions"])
        code, schema = self.invoke(b"", "schema")
        self.assertEqual(code, 0)
        self.assertIn("$schema", schema["result"])
        self.assertIn("document.create", json.dumps(schema["result"]))

    def test_structured_error_cases(self):
        for payload, expected in [(b"{", "INVALID_REQUEST"),
            (b'{"command":"capabilities","extra":1}', "INVALID_REQUEST"),
            (b'{"command":"capabilities","command":"schema"}', "INVALID_REQUEST"),
            (b'{"command":"capabilities"}\n{}', "INVALID_REQUEST"),
            (b" " * (16 * 1024 * 1024 + 1), "REQUEST_TOO_LARGE"),
            (b'{"command":"document.create","id":"x","kind":"raster","width":0,"height":1}', "INVALID_DOCUMENT")]:
            code, response = self.invoke(payload)
            self.assertEqual(code, 1)
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], expected)

    def test_missing_file_and_excess_arguments(self):
        code, response = self.invoke(b"", str(ROOT / "missing-request.json"))
        self.assertEqual((code, response["error"]["code"]), (1, "IO_ERROR"))
        code, response = self.invoke(b"", "capabilities", "unexpected")
        self.assertEqual((code, response["error"]["code"]), (1, "INVALID_REQUEST"))


if __name__ == "__main__":
    unittest.main()
