import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from loop import build_run, content_hash, execute, read

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.cfg = read(ROOT / 'config/loop.json')
        self.inputs = {k: {'status': 'unconnected'} for k in self.cfg['adapters']}

    def measured(self, total=0):
        self.cfg['window'] = {'start': '2026-10-24T00:00:00+00:00', 'end': '2026-10-31T00:00:00+00:00'}
        self.cfg['attribution']['verified'] = True
        self.inputs['measurement'] = {
            'status': 'measured', 'campaign_id': self.cfg['campaign_id'], 'window': self.cfg['window'],
            'observed_at': NOW.isoformat(), 'through': NOW.isoformat(), 'cumulative': True,
            'baseline_verified': True, 'receipt_verified': True, 'dedup_scope': 'campaign',
            'source_method': 'email_subject_code', 'evidence_refs': ['EV-SYNTHETIC-ONLY'],
            'excluded': {'existing': 2, 'duplicate': 1, 'test': 1, 'spam': 0},
            'new_attributed_signups': total, 'unknown_source_signups': 1,
            'auxiliary': {'impressions': 200, 'visits': 30},
            'raw_email': 'synthetic@example.invalid',
        }

    def approved(self, status='posted'):
        digest = content_hash(self.cfg['draft']['body'])
        asset = self.cfg['campaign_id'] + '-A-' + digest[:16]
        self.inputs['approval'] = {
            'status': 'approved', 'asset_id': asset, 'content_sha256': digest,
            'human_reviewed': True, 'scope': 'single_post', 'channel': 'synthetic',
            'account_ref': 'test-account', 'approved_at': '2026-10-24T10:00:00+00:00',
        }
        self.inputs['publication'] = {
            'status': status, 'asset_id': asset, 'channel': 'synthetic', 'account_ref': 'test-account',
            'url': 'https://example.invalid/synthetic-post', 'posted_at': '2026-10-24T11:00:00+00:00',
        }

    def test_unconnected_is_not_zero_or_published(self):
        run = build_run(self.cfg, self.inputs, now=NOW)
        self.assertIsNone(run['measurement']['new_attributed_signups'])
        self.assertEqual(run['state'], 'awaiting_approval')
        self.assertFalse(run['next_execution']['scheduled'])

    def test_automatic_request_does_not_claim_registered_schedule(self):
        self.cfg['schedule']['requested_mode'] = 'manual_start_then_daily'
        run = build_run(self.cfg, self.inputs, now=NOW)
        self.assertEqual(run['next_execution']['mode'], 'automatic_pending_connection')
        self.assertFalse(run['next_execution']['scheduled'])
        self.assertEqual(run['approval']['status'], 'unconnected')
        self.assertIsNone(run['publication']['url'])

    def test_simulation_rejects_production_campaign(self):
        self.cfg['simulation'] = True
        with self.assertRaisesRegex(ValueError, 'isolated MOCK campaign'):
            build_run(self.cfg, self.inputs, now=NOW)

    def test_zero_differs_from_unmeasured_and_raw_email_is_excluded(self):
        self.measured()
        run = build_run(self.cfg, self.inputs, now=NOW)
        self.assertEqual(run['measurement']['new_attributed_signups'], 0)
        self.assertEqual(run['next_action']['kind'], 'conversion')
        self.assertNotIn('synthetic@example.invalid', json.dumps(run))

    def test_receipt_rejects_unverified_or_invalid_measurement(self):
        for field, value in [('baseline_verified', False), ('receipt_verified', False),
                             ('cumulative', False), ('new_attributed_signups', -1),
                             ('new_attributed_signups', True), ('dedup_scope', 'day')]:
            with self.subTest(field=field, value=value):
                self.measured()
                self.inputs['measurement'][field] = value
                with self.assertRaises(ValueError):
                    build_run(self.cfg, self.inputs, now=NOW)

    def test_approval_binds_exact_body_and_account(self):
        self.approved()
        altered = copy.deepcopy(self.cfg)
        altered['draft']['body'] += '\nChanged'
        with self.assertRaises(ValueError):
            build_run(altered, self.inputs, now=NOW)
        self.inputs['publication']['account_ref'] = 'different-account'
        with self.assertRaises(ValueError):
            build_run(self.cfg, self.inputs, now=NOW)

    def test_cumulative_snapshot_is_not_summed_and_prior_guides_next(self):
        self.measured(3)
        self.approved()
        first = build_run(self.cfg, self.inputs, now=NOW)
        self.measured(4)
        second = build_run(self.cfg, self.inputs, previous=first, now=NOW)
        self.assertEqual(second['measurement']['new_attributed_signups'], 4)
        self.assertEqual(second['previous_recommendation'], first['next_action'])
        self.assertEqual(second['state'], 'measured')
        self.inputs['measurement']['through'] = '2026-10-24T01:00:00+00:00'
        with self.assertRaises(ValueError):
            build_run(self.cfg, self.inputs, previous=second, now=NOW)

    def test_uncertain_stays_uncertain_until_receipt_confirmed(self):
        self.approved('uncertain')
        first = build_run(self.cfg, self.inputs, now=NOW)
        self.inputs['publication'] = {'status': 'unconnected'}
        second = build_run(self.cfg, self.inputs, previous=first, now=NOW)
        self.assertEqual(second['state'], 'publication_uncertain')

    def test_posted_receipt_survives_disconnection_and_rejects_duplicate(self):
        self.approved()
        first = build_run(self.cfg, self.inputs, now=NOW)
        self.inputs['publication']['url'] += '-duplicate'
        with self.assertRaises(ValueError):
            build_run(self.cfg, self.inputs, previous=first, now=NOW)
        self.inputs['publication'] = {'status': 'unconnected'}
        self.inputs['approval'] = {'status': 'unconnected'}
        second = build_run(self.cfg, self.inputs, previous=first, now=NOW)
        self.assertEqual(second['publication'], first['publication'])
        self.assertEqual(second['approval'], first['approval'])

    def test_file_bridge_history_and_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'research.json').write_text(json.dumps({'status': 'pending'}))
            self.cfg['adapters']['research'] = {'driver': 'manual_json', 'path': 'research.json'}
            cfg_path = base / 'loop.json'
            cfg_path.write_text(json.dumps(self.cfg))
            out = base / 'runs'
            first_path, first = execute(cfg_path, out)
            original = first_path.read_bytes()
            _, second = execute(cfg_path, out)
            self.assertEqual(second['previous_run'], first['run_id'])
            self.assertEqual(first_path.read_bytes(), original)
            self.assertEqual(second['research']['status'], 'pending')
            (out / '.loop.lock').touch()
            with self.assertRaises(ValueError):
                execute(cfg_path, out)
            self.assertTrue((out / '.loop.lock').exists())


if __name__ == '__main__':
    unittest.main()
