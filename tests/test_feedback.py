import copy
import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from feedback import collect, learn

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)
URL = 'https://example.invalid/post'
POSTS = {URL: {'asset_id':'MOCK-A','posted_at':'2026-10-24T00:00:00+00:00'}}
METRIC = {'status':'measured','new_attributed_signups':0}


def fixture(category='signup_friction', count=2, source='own_post'):
    return {'status':'collected','campaign_id':'MOCK-C','observed_at':NOW.isoformat(),
      'coverage':[{'target_url':URL,'kind':source,'status':'complete','checked_at':NOW.isoformat(),'reason':'fixture'}],
      'events':[{'event_id':f'EV-{i}','source_url':URL+f'#reply{i}','target_url':URL,
        'source_kind':source,'created_at':NOW.isoformat(),'evidence_summary':'Synthetic application objection',
        'classification_reason':'Synthetic explicit barrier', 'category':category,
        'audience_fit':'yes','actor_type':'external','author_key':f'ANON-{i}'} for i in range(count)]}


class FeedbackTests(unittest.TestCase):
    def collect(self, raw, previous=None, posts=POSTS, targets=()):
        return collect(raw,'MOCK-C',posts,previous,NOW,targets)

    def test_two_people_barrier_drives_application_experiment(self):
        f = self.collect(fixture())
        d = learn(f,METRIC)
        self.assertEqual(d['kind'],'conversion')
        self.assertEqual(len(d['evidence_ids']),2)
        self.assertFalse(d['publication_authorized'])
        self.assertEqual(d['effect'],'not_established')

    def test_repeated_comments_not_multiple_people_or_daily_rewrite(self):
        raw=fixture(); raw['events'][1]['author_key']='ANON-0'
        f=self.collect(raw)
        self.assertEqual(learn(f,METRIC)['kind'],'investigate')
        again=self.collect(raw,f)
        self.assertEqual(len(again['events']),2)
        self.assertEqual(learn(again,METRIC)['kind'],'observe')
        extra=copy.deepcopy(raw['events'][0]); extra['event_id']='EV-extra'
        raw['events'].append(extra)
        self.assertEqual(learn(self.collect(raw,again),METRIC)['kind'],'observe')

    def test_community_not_campaign_conversion_evidence(self):
        f=self.collect(fixture(source='community'),posts={})
        self.assertEqual(learn(f,METRIC)['kind'],'research')
        self.assertTrue(all(e['asset_id'] is None for e in f['events']))

    def test_missing_and_partial_coverage_not_no_response(self):
        raw=fixture(count=0); raw['coverage'][0]['status']='unavailable'
        self.assertEqual(learn(self.collect(raw),METRIC)['kind'],'collect_reactions')
        raw['coverage'][0]['status']='complete'
        self.assertTrue(self.collect(raw)['collection_complete'])
        self.assertFalse(self.collect(raw,targets=['https://example.invalid/community'])['collection_complete'])

    def test_own_comment_requires_publication_and_valid_time(self):
        with self.assertRaises(ValueError): self.collect(fixture(),posts={})
        raw=fixture(); raw['events'][0]['created_at']='2026-10-23T00:00:00+00:00'
        with self.assertRaises(ValueError): self.collect(raw)

    def test_exclude_team_spam_unknown_fit_and_no_raw_identity(self):
        raw=fixture(); raw['events'][0]['actor_type']='team'; raw['events'][1]['audience_fit']='unknown'
        raw['events'][0]['raw_email']='secret@example.invalid'
        f=self.collect(raw)
        self.assertEqual(learn(f,METRIC)['kind'],'observe')
        self.assertNotIn('raw_email',f['events'][0])

    def test_unknown_author_does_not_establish_independent_people(self):
        raw=fixture()
        for e in raw['events']: e['author_key']=None
        self.assertEqual(learn(self.collect(raw),METRIC)['kind'],'observe')

    def test_conflicting_immutable_evidence_rejected(self):
        raw=fixture(); old=self.collect(raw); raw['events'][0]['category']='interest'
        with self.assertRaises(ValueError): self.collect(raw,old)

    def test_same_category_different_posts_does_not_fake_repetition(self):
        raw=fixture(); other='https://example.invalid/other'
        raw['coverage'].append(dict(raw['coverage'][0],target_url=other))
        raw['events'][1]['target_url']=other
        f=self.collect(raw,posts={**POSTS,other:POSTS[URL]})
        self.assertEqual(learn(f,METRIC)['kind'],'investigate')

    def test_signup_change_is_observed_not_causal_or_interest(self):
        f=self.collect(fixture(category='interest'))
        d=learn(f,dict(METRIC,new_attributed_signups=1),METRIC)
        self.assertEqual(d['signup_delta'],1)
        self.assertEqual(d['effect'],'not_established')
        self.assertEqual(d['kind'],'follow_up')
        self.assertEqual(learn(f,METRIC,dict(METRIC,new_attributed_signups=1))['kind'],'audit')

    def test_no_connector_needs_collection_and_preserves_history(self):
        old=self.collect(fixture()); f=self.collect({'status':'unconnected'},old)
        self.assertEqual(len(f['events']),2)
        self.assertEqual(learn(f,METRIC)['kind'],'collect_reactions')
