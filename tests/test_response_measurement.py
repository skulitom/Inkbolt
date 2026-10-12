"""Actual RPC-line measurements must recover the same original CLI artifacts."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from measure_responses import measure_mcp
from test_cli import EXE


class ResponseMeasurementTests(unittest.TestCase):
    def test_every_mode_retains_pixels_and_measures_single_png_payload(self):
        result=measure_mcp(EXE)
        self.assertEqual(len(result['rows']),8)
        for row in result['rows']:
            self.assertEqual(row['status'],'passed',row)
            self.assertTrue(row['original_result_recovered'])
            self.assertGreater(row['wire_bytes'],row['text_bytes'])
            self.assertEqual(row['png_payload_occurrences'],[1] if row['case']=='png' else [])
        snapshots={r['response_format']:r for r in result['rows'] if r['case']=='snapshot'}
        self.assertLess(snapshots['structured']['wire_bytes'],snapshots['json']['wire_bytes']*.55)


if __name__=='__main__':unittest.main()
