import copy
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'src'))
from mock_refinement import BASE, CANDIDATE, review, proposal, run_demo
from refinement import assess, compare
from loop import build_run, read, decide

class RefinementTests(unittest.TestCase):
    def setUp(self):
        self.base, self.candidate, self.proposal = review(BASE, 1), review(CANDIDATE, 2), proposal()

    def compare(self):
        return compare(self.base, self.candidate, BASE, CANDIDATE, self.proposal)

    def test_bounded_cycle_does_not_authorize_or_claim_market_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_demo(Path(tmp)/'demo')
            self.assertEqual(result['decision'], 'candidate_for_human_review')
            self.assertFalse(result['publication_authorized'])
            self.assertEqual(result['market_validation'], 'pending_real_observation')

    def test_missing_evidence_or_forged_excerpt_rejected(self):
        self.base['criteria']['cta_clarity']['evidence_refs'] = []
        with self.assertRaises(ValueError): assess(self.base, BASE)
        self.base = review(BASE, 1)
        self.base['evidence']['DRAFT']['excerpt'] = 'invented quote'
        with self.assertRaises(ValueError): assess(self.base, BASE)

    def test_unknown_is_not_zero_and_blocks_selection(self):
        self.base['criteria']['cta_clarity']['score'] = None
        self.assertEqual(assess(self.base, BASE)['decision'], 'needs_evidence')
        self.assertEqual(self.compare()['decision'], 'needs_evidence')

    def test_hash_and_version_are_bound(self):
        for field in ('content_sha256', 'rubric_version'):
            bad = copy.deepcopy(self.base); bad[field] = 'wrong'
            with self.assertRaises(ValueError): assess(bad, BASE)

    def test_regression_blocks_candidate(self):
        self.candidate['criteria']['delegation_value']['score'] = 1
        self.assertEqual(self.compare()['decision'], 'hold')

    def test_fact_gate_precedes_optimization(self):
        self.base['gates']['claims_supported']['status'] = 'fail'
        self.assertEqual(assess(self.base, BASE)['decision'], 'repair_claims')
        self.assertEqual(self.compare()['decision'], 'needs_evidence')

    def test_stop_and_hold_prevent_endless_rewriting(self):
        self.proposal['attempt'] = 3
        self.assertEqual(self.compare()['decision'], 'stop_for_review')
        self.proposal['attempt'] = 1
        self.base['criteria']['cta_clarity']['score'] = 2
        self.assertEqual(self.compare()['decision'], 'hold')

    def test_multiple_changes_rejected(self):
        self.proposal['changed_variables'].append('audience')
        with self.assertRaises(ValueError): self.compare()

    def test_review_flows_into_run_without_approval(self):
        cfg = read(ROOT/'config/loop.json'); cfg['draft']['body'] = BASE
        inputs = {key: {'status': 'unconnected'} for key in cfg['adapters']}
        inputs['evaluation'] = self.base
        run = build_run(cfg, inputs)
        self.assertEqual(run['content_review']['weakest'], 'cta_clarity')
        self.assertEqual(run['state'], 'awaiting_approval')

    def test_same_snapshot_holds_and_correction_requires_audit(self):
        cfg = read(ROOT/'config/loop.json')
        previous = {'status':'measured', 'new_attributed_signups':3,
                    'auxiliary':{'impressions':200,'visits':30}}
        self.assertEqual(decide(previous, cfg, previous)['kind'], 'observe')
        corrected = dict(previous, new_attributed_signups=2)
        self.assertEqual(decide(corrected, cfg, previous)['kind'], 'audit')
