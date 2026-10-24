"""Evidence-bound editorial judgments; never a claim of conversion improvement."""
from hashlib import sha256

VERSION = 'mu-content-v1'
CRITERIA = ('customer_situation', 'delegation_value', 'product_honesty', 'cta_clarity')
GATES = ('claims_supported', 'early_access_clear')
MAX_REVISIONS = 2


def digest(body):
    return sha256(body.encode('utf-8')).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def assess(review, body):
    if review.get('status') in ('unconnected', 'pending'):
        return {'status': review['status'], 'decision': 'needs_review', 'weakest': None,
                'market_validation': 'not_established'}
    require(review.get('status') == 'reviewed', 'Invalid editorial review status')
    require(review['rubric_version'] == VERSION, 'Rubric version mismatch')
    require(review['content_sha256'] == digest(body), 'Review must match exact content')
    require(set(review['criteria']) == set(CRITERIA), 'Incomplete rubric criteria')
    require(set(review['gates']) == set(GATES), 'Incomplete factual gates')
    evidence = review['evidence']
    require(isinstance(evidence, dict), 'Evidence registry required')
    for item in evidence.values():
        require(item.get('source_ref') and item.get('observation'), 'Evidence needs source and observation')
        if item.get('kind') == 'draft_excerpt':
            require(item.get('excerpt') and item['excerpt'] in body, 'Draft evidence does not match content')
    scores = {}
    for name, item in review['criteria'].items():
        score = item['score']
        require(score is None or (type(score) is int and 0 <= score <= 2), 'Score must be null or 0–2')
        require(item.get('reason'), 'Criterion reasoning required')
        refs = item.get('evidence_refs', [])
        require(all(ref in evidence for ref in refs), 'Unknown evidence reference')
        require(score is None or bool(refs), 'Known score needs evidence')
        scores[name] = score
    for item in review['gates'].values():
        require(item['status'] in ('pass', 'fail', 'unknown'), 'Invalid factual gate')
        require(item.get('reason'), 'Gate reasoning required')
        refs = item.get('evidence_refs', [])
        require(all(ref in evidence for ref in refs), 'Unknown gate evidence')
        require(item['status'] == 'unknown' or bool(refs), 'Known gate needs evidence')
    failed = [name for name, item in review['gates'].items() if item['status'] == 'fail']
    unknown = [name for name, item in review['gates'].items() if item['status'] == 'unknown']
    if failed:
        decision, weakest = 'repair_claims', failed[0]
    elif unknown or any(score is None for score in scores.values()):
        decision, weakest = 'needs_evidence', None
    else:
        weakest = min(CRITERIA, key=lambda key: scores[key])
        decision = 'revise' if scores[weakest] < 2 else 'ready_for_human_review'
        if decision == 'ready_for_human_review':
            weakest = None
    return {'status': 'reviewed', 'rubric_version': VERSION, 'decision': decision,
            'weakest': weakest, 'scores': scores, 'failed_gates': failed,
            'unknown_gates': unknown, 'market_validation': 'not_established'}


def compare(base, candidate, base_body, candidate_body, proposal):
    """Accept at most one evidenced editorial change; external publication stays gated."""
    before, after = assess(base, base_body), assess(candidate, candidate_body)
    require(before['status'] == after['status'] == 'reviewed', 'Both drafts need review')
    require(proposal['parent_sha256'] == digest(base_body), 'Wrong revision parent')
    require(proposal['candidate_sha256'] == digest(candidate_body), 'Wrong revision candidate')
    target = proposal['target_criterion']
    require(target in CRITERIA, 'Unknown revision criterion')
    require(len(proposal['changed_variables']) == 1, 'Change one major variable')
    for field in ('hypothesis', 'prediction', 'observe_next', 'stop_rule', 'fixed_context'):
        require(proposal.get(field), 'Missing experiment reasoning: ' + field)
    attempt = proposal['attempt']
    require(type(attempt) is int and attempt > 0, 'Invalid revision attempt')
    if attempt > MAX_REVISIONS:
        decision, reason = 'stop_for_review', 'Revision budget exhausted'
    elif before['decision'] == 'ready_for_human_review':
        decision, reason = 'hold', 'Already meets rubric; no score-chasing revision'
    elif before['decision'] in ('repair_claims', 'needs_evidence') or after['decision'] in ('repair_claims', 'needs_evidence'):
        decision, reason = 'needs_evidence', 'Cannot accept unsupported revision'
    elif target != before['weakest']:
        decision, reason = 'hold', 'Address the diagnosed weakest criterion first'
    elif after['scores'][target] <= before['scores'][target]:
        decision, reason = 'hold', 'No supported improvement on target criterion'
    elif any(after['scores'][key] < before['scores'][key] for key in CRITERIA if key != target):
        decision, reason = 'hold', 'Another criterion regressed'
    else:
        decision, reason = 'candidate_for_human_review', 'Target improved with no criterion regression'
    return {'decision': decision, 'reason': reason, 'before': before, 'after': after,
            'target_criterion': target, 'proposal': proposal,
            'market_validation': 'pending_real_observation', 'publication_authorized': False}
