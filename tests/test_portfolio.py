import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts')); sys.path.insert(0,str(ROOT/'src'))
from mock_portfolio import (fixture_config, fixture_rubrics, evidence_fixture, MockGenerator, MockAgent,
                            JsonAgent, add_hypothesis, outcome, publish, START, run_demo)
from portfolio import (initial_state, admit, judge, digest, plan_batch, settle, winner_candidate,
                       record_publication, statistics, generation_request, compare_arms,
                       pending_generation_requests)


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.cfg=fixture_config(); self.rubrics=fixture_rubrics(); self.evidence=evidence_fixture()
        self.state=initial_state(); self.hypotheses=MockGenerator().propose(None,self.evidence)
        for h in self.hypotheses: add_hypothesis(self.cfg,self.state,h,self.rubrics,self.evidence)

    def jobs(self, day=0, **kwargs):
        return plan_batch(self.cfg,self.state,START+timedelta(days=day),**kwargs)['jobs']

    def test_three_accounts_parallel_distinct_jobs_and_approvals(self):
        jobs=self.jobs()
        self.assertEqual(len(jobs),3)
        self.assertEqual(len({j['account_id'] for j in jobs}),3)
        self.assertEqual(len({j['arm_id'] for j in jobs}),3)
        for job in jobs:
            self.assertTrue(job['requires_human_approval'])
            publish(self.cfg,self.state,job,START)
        self.assertEqual(self.jobs(),[])

    def test_content_edit_or_account_change_invalidates_approval(self):
        job=self.jobs()[0]
        approval={'human_reviewed':True,'job_hash':digest(job),'approved_at':START.isoformat()}
        receipt={'deployment_id':job['deployment_id'],'account_id':job['account_id'],'status':'posted',
                 'url':'https://example.invalid/p','posted_at':START.isoformat()}
        for field,value in [('body','changed'),('account_id','mock-account-unknown')]:
            changed=dict(job,**{field:value})
            with self.assertRaises(ValueError): record_publication(self.cfg,self.state,changed,approval,receipt)

    def test_pending_outcome_not_zero_and_replay_idempotent(self):
        job=self.jobs()[0]; publish(self.cfg,self.state,job,START)
        dep=self.state['deployments'][job['deployment_id']]
        early=outcome(self.cfg,dep,START,0)
        with self.assertRaises(ValueError): settle(self.cfg,self.state,[early],START)
        self.assertEqual(statistics(self.cfg,self.state,job['arm_id'],job['context'])['n'],0)
        at=START+timedelta(days=1); mature=outcome(self.cfg,dep,at,1)
        settle(self.cfg,self.state,[mature,mature],at)
        settle(self.cfg,self.state,[mature],at)
        self.assertEqual(len(self.state['used_credit_ids']),1)
        self.assertEqual(statistics(self.cfg,self.state,job['arm_id'],job['context'])['n'],1)

    def test_cross_arm_duplicate_credit_rejected_atomically(self):
        jobs=self.jobs()
        for j in jobs: publish(self.cfg,self.state,j,START)
        at=START+timedelta(days=1)
        obs=[outcome(self.cfg,self.state['deployments'][j['deployment_id']],at,1) for j in jobs[:2]]
        obs[1]['credit_ids']=obs[0]['credit_ids']
        with self.assertRaises(ValueError): settle(self.cfg,self.state,obs,at)
        self.assertEqual(self.state['outcomes'],{})

    def test_campaign_only_attribution_cannot_learn_or_select_winner(self):
        self.cfg['attribution']['level']='campaign'
        self.assertTrue(all(j['allocation_reason']=='balanced_initial_test' for j in self.jobs()))
        with self.assertRaises(ValueError): settle(self.cfg,self.state,[],START)
        self.assertEqual(winner_candidate(self.cfg,self.state)['status'],'attribution_unverified')

    def test_rubric_swap_rejects_old_review_then_accepts_new_contract(self):
        h=self.hypotheses[0]; agent=MockAgent('hypothesis_generator'); rubric=self.rubrics[agent.role]
        review=agent.run(h,rubric,self.evidence)
        changed=copy.deepcopy(rubric); changed['id']='generator-stricter-v2'
        changed['criteria'].append({'id':'negative_reaction','question':'반대 근거를 보았는가','required':True})
        with self.assertRaises(ValueError): judge(h,changed,review,self.evidence)
        new=agent.run(h,changed,self.evidence)
        self.assertTrue(judge(h,changed,new,self.evidence)['accepted'])
        new['criteria']['negative_reaction']['score']=None
        self.assertFalse(judge(h,changed,new,self.evidence)['accepted'])

    def test_generator_cannot_self_approve(self):
        h=dict(self.hypotheses[0],arm_id='ARM-NEW')
        gen=MockAgent('hypothesis_generator').run(h,self.rubrics['hypothesis_generator'],self.evidence)
        rev=MockAgent('hypothesis_reviewer').run(h,self.rubrics['hypothesis_reviewer'],self.evidence)
        rev['agent_id']=h['generator_id']
        with self.assertRaises(ValueError): admit(self.cfg,self.state,h,gen,rev,self.rubrics,self.evidence)

    def test_json_agent_uses_same_interface(self):
        h=self.hypotheses[0]; rubric=self.rubrics['hypothesis_reviewer']
        expected=MockAgent('hypothesis_reviewer').run(h,rubric,self.evidence)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'review.json'; p.write_text(json.dumps(expected))
            self.assertTrue(judge(h,rubric,JsonAgent(p).run(h,rubric,self.evidence),self.evidence)['accepted'])

    def test_unconnected_account_has_no_jobs(self):
        self.assertEqual(len(self.jobs()),3)
        for a in self.cfg['accounts']: a['publishing_verified']=False
        self.assertEqual(self.jobs(),[])

    def test_winner_needs_every_account_context_not_total_alone(self):
        job=self.jobs()[0]; publish(self.cfg,self.state,job,START)
        at=START+timedelta(days=1)
        settle(self.cfg,self.state,[outcome(self.cfg,self.state['deployments'][job['deployment_id']],at,100)],at)
        self.assertEqual(winner_candidate(self.cfg,self.state)['status'],'insufficient_evidence')

    def test_generation_request_retry_is_durable(self):
        promotion={'promotion_id':'PROMOTE-fixture','winner':'ARM-DELIVERY'}
        a=generation_request(self.cfg,self.state,promotion)
        self.assertEqual(a,generation_request(self.cfg,self.state,promotion))
        self.assertEqual(pending_generation_requests(self.state),[a])

    def test_seven_day_winner_generates_refinement_and_expansion(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=run_demo(Path(tmp)/'demo')
            self.assertEqual(result['incumbent'],'ARM-DELIVERY')
            self.assertEqual(result['final_arms'],5)
            self.assertEqual(result['generation_events'],1)
            self.assertEqual(result['external_calls'],0)
