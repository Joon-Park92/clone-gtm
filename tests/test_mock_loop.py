import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from mock_loop import run_demo


class MockLoopIntegrationTests(unittest.TestCase):
    def test_seven_day_adapter_loop_in_isolated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'demo'
            report = run_demo(output)
            self.assertEqual(report['result'], 'PASS')
            self.assertEqual(report['manual_bootstrap_count'], 1)
            self.assertEqual(report['virtual_daily_ticks'], 7)
            self.assertEqual(report['mock_publish_send_calls'], 3)
            self.assertEqual(len(report['negative_cases_rejected']), 4)
            self.assertEqual(len(list((output / 'records').glob('RUN-*.json'))), 8)
            self.assertTrue(report['production_config_unchanged'])
            self.assertFalse(report['real_scheduler_registered'])
            self.assertFalse(report['real_credentials_read'])


if __name__ == '__main__':
    unittest.main()
