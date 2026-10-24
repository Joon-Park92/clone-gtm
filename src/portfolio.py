"""Pure planning core for evolving hypothesis portfolios. Never sends a post.
Agent judgments and observed outcomes enter through explicit, replaceable contracts.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from hashlib import sha256
import json
from typing import Protocol


class AgentAdapter(Protocol):
    def run(self, task: dict, rubric: dict, evidence: dict) -> dict: ...


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'Timezone required')
    return result


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def initial_state():
    return {'arms': {}, 'assets': {}, 'deployments': {}, 'outcomes': {}, 'incumbent': None,
            'promotions': [], 'used_credit_ids': [], 'generation_requests': {}, 'generation_completed': []}


def judge(subject, rubric, review, evidence):
    """Rubric criteria are data. Hashes pin both the task and criterion version."""
    require(review['subject_hash'] == digest(subject), 'Review subject mismatch')
    require(review['rubric_hash'] == digest(rubric), 'Review rubric mismatch')
    require(review['role'] == rubric['role'] and review.get('agent_id'), 'Wrong evaluator role')
    criteria = {item['id'] for item in rubric['criteria']}
    require(set(review['criteria']) == criteria and set(review['gates']) == set(rubric['gates']), 'Incomplete rubric review')
    accepted = True
    for item in review['criteria'].values():
        score = item['score']
        require(score is None or (type(score) is int and 0 <= score <= 2), 'Invalid rubric score')
        require(item.get('reason'), 'Review reasoning required')
        refs = item.get('evidence_refs', [])
        require(all(ref in evidence for ref in refs), 'Unknown review evidence')
        require(score is None or bool(refs), 'Score needs evidence')
        accepted &= score is not None and score >= rubric['minimum_each']
    for item in review['gates'].values():
        require(item['status'] in ('pass', 'fail', 'unknown') and item.get('reason'), 'Invalid review gate')
        require(all(ref in evidence for ref in item.get('evidence_refs', [])), 'Unknown gate evidence')
        require(item['status'] == 'unknown' or bool(item.get('evidence_refs')), 'Gate needs evidence')
        accepted &= item['status'] == 'pass'
    return {'accepted': bool(accepted), 'rubric_id': rubric['id'], 'rubric_hash': digest(rubric),
            'review': review, 'is_conversion_reward': False, 'publication_authorized': False}


def admit(cfg, state, hypothesis, generator_review, reviewer_review, rubrics, evidence):
    require(hypothesis['arm_id'] not in state['arms'], 'Arm version already exists')
    require(len([a for a in state['arms'].values() if a['status'] == 'active']) < cfg['policy']['max_active_arms'], 'Active arm budget exhausted')
    for key in ('domain', 'audience', 'problem', 'offer', 'prediction', 'falsifier', 'generator_id', 'changed_axis'):
        require(hypothesis.get(key), 'Missing hypothesis field: '+key)
    require(hypothesis['origin'] in ('seed', 'refinement', 'expansion'), 'Invalid hypothesis origin')
    require(hypothesis['evidence_refs'] and all(e in evidence for e in hypothesis['evidence_refs']), 'Hypothesis evidence missing')
    require(generator_review['agent_id'] == hypothesis['generator_id'], 'Generator identity mismatch')
    require(reviewer_review['agent_id'] != hypothesis['generator_id'], 'Independent reviewer required')
    require(rubrics['hypothesis_generator']['role'] == 'hypothesis_generator' and
            rubrics['hypothesis_reviewer']['role'] == 'hypothesis_reviewer', 'Role rubric mismatch')
    if hypothesis['origin'] != 'seed':
        require(hypothesis.get('parent_arm_id') in state['arms'], 'Unknown parent arm')
        parent = state['arms'][hypothesis['parent_arm_id']]['hypothesis']
        require((hypothesis['domain'] != parent['domain']) == (hypothesis['origin'] == 'expansion'), 'Lineage domain mismatch')
    reviews = [judge(hypothesis, rubrics[role], review, evidence) for role, review in
               [('hypothesis_generator', generator_review), ('hypothesis_reviewer', reviewer_review)]]
    require(all(r['accepted'] for r in reviews), 'Hypothesis did not pass review')
    state['arms'][hypothesis['arm_id']] = {'hypothesis': hypothesis, 'reviews': reviews, 'status': 'active'}


def set_asset(state, arm_id, body, review, rubric, evidence):
    require(arm_id in state['arms'] and body, 'Unknown arm or empty body')
    require(rubric['role'] == 'content_writer', 'Wrong content rubric')
    subject = {'arm_id': arm_id, 'body': body}
    result = judge(subject, rubric, review, evidence)
    require(result['accepted'], 'Content needs revision')
    asset_id = 'ASSET-'+digest(subject)[:16]
    # Semantic offer/audience changes require a new arm; a critic checks this, not a text hash.
    state['assets'][arm_id] = {'asset_id': asset_id, 'body': body, 'review': result}
    return asset_id


def eligible_accounts(cfg):
    return [a for a in cfg['accounts'] if a['active'] and a['ownership_confirmed'] and a['publishing_verified']]


def context(account):
    return account['account_id']+'|'+account['context_block']


def statistics(cfg, state, arm_id, ctx):
    outcomes = [o for key, o in state['outcomes'].items()
                if state['deployments'][key]['arm_id'] == arm_id and state['deployments'][key]['context'] == ctx]
    n, reward = len(outcomes), sum(len(o['credit_ids']) for o in outcomes)
    return {'n': n, 'reward': reward, 'signups_per_post': reward/n if n else None}


def plan_batch(cfg, state, now):
    """Equal slots: observed high, observed low, and a new/less-tested hypothesis."""
    if not cfg['window']['start'] or not cfg['window']['end']:
        return {'status': 'window_unfixed', 'jobs': []}
    if not timestamp(cfg['window']['start']) <= now < timestamp(cfg['window']['end']):
        return {'status': 'outside_window', 'jobs': []}
    accounts = sorted(eligible_accounts(cfg), key=lambda a: a['account_id'])
    if not accounts:
        return {'status': 'accounts_unconnected', 'jobs': []}
    arm_ids = sorted(key for key, value in state['arms'].items() if value['status'] == 'active' and key in state['assets'])
    if not arm_ids:
        return {'status': 'no_reviewed_arms', 'jobs': []}
    day = (now-timestamp(cfg['window']['start'])).days
    # Rotate identities across comparison lanes instead of fixing one hypothesis to one account.
    offset = day % len(accounts)
    accounts = accounts[offset:]+accounts[:offset]
    comparison = compare_arms(cfg, state)
    preferred = [comparison['high_arm'], comparison['low_arm']] if comparison['status'] == 'comparable' else []
    low_revision = None
    if preferred:
        children = [a for a in arm_ids if state['arms'][a]['hypothesis'].get('parent_arm_id') == preferred[1]
                    and state['arms'][a]['hypothesis']['origin'] == 'refinement']
        if children:
            low_revision = sorted(children)[-1]
            preferred[1] = low_revision
    jobs, selected = [], set()
    counts = {a: sum(d['arm_id'] == a for d in state['deployments'].values()) for a in arm_ids}
    for account in accounts:
        if len(jobs) >= cfg['policy']['max_parallel'] or len(selected) >= len(arm_ids):
            break
        today = [d for d in state['deployments'].values() if d['account_id'] == account['account_id'] and
                 timestamp(d['posted_at']).date() == now.date()]
        if len(today) >= cfg['policy']['max_posts_per_account_day']:
            continue
        remaining = [a for a in arm_ids if a not in selected]
        capacity = min(len(accounts), cfg['policy']['max_parallel'])
        lane = (day + len(jobs)) % 3 if capacity < 3 else len(jobs)
        if lane < len(preferred) and preferred[lane] in remaining:
            arm = preferred[lane]
            reason = 'observed_high' if lane == 0 else ('low_hypothesis_revision' if low_revision else 'observed_low')
        else:
            ctx = context(account)
            by_context = {a: sum(d['arm_id'] == a and d['context'] == ctx for d in state['deployments'].values()) for a in remaining}
            arm = min(remaining, key=lambda a: (by_context[a], counts[a], a))
            reason = 'new_or_less_tested' if preferred else 'balanced_initial_test'
        selected.add(arm)
        asset = state['assets'][arm]
        job = {'campaign_id': cfg['campaign_id'], 'arm_id': arm, 'asset_id': asset['asset_id'],
               'body': asset['body'], 'account_id': account['account_id'], 'context': context(account),
               'planned_at': now.isoformat(), 'policy_version': cfg['policy']['version'], 'allocation_reason': reason}
        job['deployment_id'] = 'DEP-'+digest(job)[:16]
        job['requires_human_approval'] = True
        jobs.append(job)
    return {'status': 'planned', 'jobs': jobs, 'comparison': comparison, 'external_calls': 0,
            'comparison_complete_batch': any(j['allocation_reason'] == 'observed_high' for j in jobs) and
                any(j['allocation_reason'] in ('observed_low', 'low_hypothesis_revision') for j in jobs)}


def record_publication(cfg, state, job, approval, receipt):
    require(job['campaign_id'] == cfg['campaign_id'], 'Wrong deployment campaign')
    accounts = {a['account_id']: a for a in eligible_accounts(cfg)}
    require(job['account_id'] in accounts, 'Account not eligible')
    require(job['context'] == context(accounts[job['account_id']]), 'Wrong account context')
    require(job['arm_id'] in state['arms'] and job['asset_id'] == state['assets'][job['arm_id']]['asset_id'] and
            job['body'] == state['assets'][job['arm_id']]['body'], 'Asset changed after allocation')
    require(approval.get('human_reviewed') is True and approval.get('job_hash') == digest(job), 'Exact human job approval required')
    require(receipt['deployment_id'] == job['deployment_id'] and receipt['account_id'] == job['account_id'], 'Wrong receipt target')
    require(receipt['status'] == 'posted' and receipt['url'].startswith('https://'), 'Confirmed publication required')
    require(timestamp(job['planned_at']) <= timestamp(approval['approved_at']) <= timestamp(receipt['posted_at']), 'Invalid posting order')
    require(timestamp(cfg['window']['start']) <= timestamp(receipt['posted_at']) < timestamp(cfg['window']['end']), 'Publication outside campaign')
    dep = dict(job, posted_at=receipt['posted_at'], url=receipt['url'])
    key = job['deployment_id']
    if key in state['deployments']:
        require(state['deployments'][key] == dep, 'Duplicate publication conflict')
        return
    require(not any(d['url'] == dep['url'] for d in state['deployments'].values()), 'Receipt already used')
    today = [d for d in state['deployments'].values() if d['account_id'] == job['account_id'] and
             timestamp(d['posted_at']).date() == timestamp(receipt['posted_at']).date()]
    require(len(today) < cfg['policy']['max_posts_per_account_day'], 'Daily account capacity exhausted')
    state['deployments'][key] = dep


def settle(cfg, state, outcomes, now):
    require(cfg['attribution']['verified'] and cfg['attribution']['level'] == 'deployment', 'Deployment attribution required for comparison')
    staged, used = {}, set(state['used_credit_ids'])
    for raw in outcomes:
        dep_id = raw['deployment_id']
        require(dep_id in state['deployments'], 'Unknown outcome deployment')
        dep = state['deployments'][dep_id]
        deadline = timestamp(dep['posted_at'])+timedelta(hours=cfg['policy']['outcome_hours'])
        require(deadline <= timestamp(cfg['window']['end']), 'Observation truncated by campaign end; do not compare as a complete window')
        require(deadline <= timestamp(raw['observed_through']) <= now, 'Outcome still pending')
        require(raw['campaign_id'] == cfg['campaign_id'], 'Wrong outcome campaign')
        require(raw['window_end'] == deadline.isoformat(), 'Unequal outcome window')
        require(raw['verified_receipts'] is True and raw['baseline_excluded'] is True and
                raw['campaign_deduplicated'] is True and raw['complete'] is True, 'Outcome verification incomplete')
        require(raw['evidence_refs'], 'Outcome evidence required')
        credits = raw['credit_ids']
        require(len(credits) == len(set(credits)) and all(c.startswith('CREDIT-') for c in credits), 'Invalid anonymous conversion credits')
        clean = {k: raw[k] for k in ('deployment_id', 'campaign_id', 'window_end', 'observed_through',
                 'credit_ids', 'evidence_refs', 'verified_receipts', 'baseline_excluded', 'campaign_deduplicated', 'complete')}
        previous = state['outcomes'].get(dep_id) or staged.get(dep_id)
        if previous:
            require(previous == clean, 'Outcome correction needs audited rebuild')
            continue
        require(not (set(credits) & used), 'Same applicant credited to multiple deployments')
        used.update(credits); staged[dep_id] = clean
    state['outcomes'].update(staged)
    state['used_credit_ids'] = sorted(used)


def compare_arms(cfg, state):
    base = {'status': 'insufficient_evidence', 'high_arm': None, 'low_arm': None,
            'causal_claim': False, 'unmeasured_is_low': False}
    if not cfg['attribution']['verified'] or cfg['attribution']['level'] != 'deployment':
        return dict(base, status='attribution_unverified')
    contexts = sorted(context(a) for a in eligible_accounts(cfg))
    arms = sorted(a for a, item in state['arms'].items() if item['status'] == 'active')
    if not contexts:
        return base
    stats = {a: {ctx: statistics(cfg, state, a, ctx) for ctx in contexts} for a in arms}
    comparable = [a for a in arms if all(stats[a][c]['n'] >= cfg['policy']['min_mature_per_context'] for c in contexts)]
    pending = [a for a in arms if a not in comparable]
    if len(comparable) < 2:
        return dict(base, pending_arms=pending, statistics=stats)
    means = {a: sum(stats[a][c]['signups_per_post'] for c in contexts)/len(contexts) for a in comparable}
    ordered = sorted(comparable, key=lambda a: (-means[a], a))
    if means[ordered[0]] == means[ordered[-1]]:
        return dict(base, status='tied', pending_arms=pending, statistics=stats, cohort=comparable)
    return dict(base, status='comparable', high_arm=ordered[0], low_arm=ordered[-1],
                cohort=comparable, pending_arms=pending, contexts=contexts, statistics=stats,
                average_signups_per_post=means,
                outcome_hash=digest(state['outcomes']), policy_hash=digest(cfg['policy']))


def winner_candidate(cfg, state):
    """An operational leader in the observed cohort, not a statistical best-arm claim."""
    comparison = compare_arms(cfg, state)
    if comparison['status'] != 'comparable':
        return dict(comparison, winner=None)
    high = comparison['high_arm']
    best_on_each_account = all(comparison['statistics'][high][ctx]['signups_per_post'] >=
        comparison['statistics'][other][ctx]['signups_per_post']
        for ctx in comparison['contexts'] for other in comparison['cohort'])
    return dict(comparison, status='candidate' if best_on_each_account else 'account_dependent',
                winner=high if best_on_each_account else None)


def promote(cfg, state, candidate, review, rubric, evidence):
    require(candidate['status'] == 'candidate' and candidate['winner'], 'No eligible winner candidate')
    require(candidate['outcome_hash'] == digest(state['outcomes']) and candidate['policy_hash'] == digest(cfg['policy']), 'Stale winner evidence')
    require(rubric['role'] == 'learning_reviewer', 'Wrong learning rubric')
    require(review['agent_id'] != state['arms'][candidate['winner']]['hypothesis']['generator_id'], 'Independent learning reviewer required')
    result = judge(candidate, rubric, review, evidence)
    require(result['accepted'], 'Winner review failed')
    arm = candidate['winner']
    if state['incumbent'] == arm:
        return None  # Do not generate the same descendants on every unchanged observation.
    event = {'winner': arm, 'candidate': candidate, 'review': result}
    event['promotion_id'] = 'PROMOTE-'+digest(event)[:16]
    state['incumbent'] = arm
    state['promotions'].append(event)
    return event


def generation_request(cfg, state, promotion):
    if promotion is None or promotion['promotion_id'] in state['generation_completed']:
        return None
    key = promotion['promotion_id']
    if key in state['generation_requests']:
        return state['generation_requests'][key]
    capacity = cfg['policy']['max_active_arms']-sum(a['status'] == 'active' for a in state['arms'].values())
    if capacity <= 0:
        return None
    low = promotion.get('candidate', {}).get('low_arm', promotion['winner'])
    request = {'parent_arm_id': promotion['winner'], 'refinement_parent_arm_id': low,
               'refinement_domain': state['arms'][low]['hypothesis']['domain'],
               'expansion_parent_arm_id': promotion['winner'], 'trigger': key,
               'maximum_candidates': min(capacity, cfg['policy']['new_arms_per_promotion']),
               'required_tracks': ['refinement', 'expansion'], 'reaction_evidence_required': True,
               'fresh_observations_required': True, 'human_publication_approval_required': True}
    state['generation_requests'][key] = request
    return request


def complete_generation(state, request, arm_ids):
    require(request == state['generation_requests'].get(request['trigger']), 'Unknown generation request')
    require(0 < len(arm_ids) <= request['maximum_candidates'] and len(arm_ids) == len(set(arm_ids)), 'Invalid candidate count')
    require(all(a in state['arms'] and state['arms'][a]['hypothesis']['parent_arm_id'] in
                (request['refinement_parent_arm_id'], request['expansion_parent_arm_id']) for a in arm_ids), 'Candidate lineage mismatch')
    if request['trigger'] not in state['generation_completed']:
        state['generation_completed'].append(request['trigger'])


def pending_generation_requests(state):
    return [request for key, request in state['generation_requests'].items() if key not in state['generation_completed']]
