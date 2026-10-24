"""Reaction evidence and conversion-oriented learning; no network or sentiment score."""
from datetime import datetime
from collections import defaultdict

CATEGORIES = ('signup_friction', 'misunderstanding', 'trust', 'no_need', 'need', 'interest', 'other')
PRIORITY = ('signup_friction', 'misunderstanding', 'trust', 'no_need')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def time(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'Reaction time needs timezone')
    return result


def collect(raw, campaign, posts, previous, now, community_targets=()):
    """Merge immutable, sanitized events; a collection snapshot can be incomplete."""
    previous = previous or {}
    ledger = {item['event_id']: item for item in previous.get('events', [])}
    status = raw.get('status')
    require(status in ('unconnected', 'pending', 'collected'), 'Invalid feedback status')
    result = {'status': status, 'events': list(ledger.values()), 'new_event_ids': [],
              'coverage': [], 'missing_post_urls': sorted(set(posts) | set(community_targets)),
              'collection_complete': False}
    if previous.get('observed_at'):
        result['observed_at'] = previous['observed_at']
    if status != 'collected':
        return result
    require(raw['campaign_id'] == campaign, 'Wrong reaction campaign')
    observed = time(raw['observed_at'])
    require(observed <= now, 'Reaction observation in future')
    if previous.get('observed_at'):
        require(observed >= time(previous['observed_at']), 'Reaction observation moved backwards')
    coverage = {}
    for item in raw['coverage']:
        url = item['target_url']
        require(url.startswith('https://') and url not in coverage, 'Invalid/duplicate reaction target')
        require(item['kind'] in ('own_post', 'community'), 'Invalid reaction target kind')
        require(item['status'] in ('complete', 'partial', 'unavailable'), 'Invalid collection coverage')
        require(time(item['checked_at']) <= observed, 'Coverage after observation')
        require(item.get('reason'), 'Coverage reason required')
        if item['kind'] == 'own_post':
            require(url in posts, 'Own reactions need a verified publication receipt')
        else:
            require(url not in posts, 'Own post cannot be relabeled community')
        coverage[url] = {key: item[key] for key in ('target_url', 'kind', 'status', 'checked_at', 'reason')}
    for item in raw['events']:
        target = item['target_url']
        require(target in coverage and coverage[target]['status'] != 'unavailable', 'Event needs readable coverage')
        require(item['source_kind'] == coverage[target]['kind'], 'Reaction source mismatch')
        require(item['event_id'].startswith('EV-') and item['source_url'].startswith('https://'), 'Reaction source required')
        require(time(item['created_at']) <= time(coverage[target]['checked_at']), 'Reaction created after coverage')
        if item['source_kind'] == 'own_post':
            require(time(item['created_at']) >= time(posts[target]['posted_at']), 'Reaction predates publication')
        require(item.get('evidence_summary') and item.get('classification_reason'), 'Reaction evidence and reasoning required')
        require(item['category'] in CATEGORIES, 'Invalid reaction category')
        require(item['audience_fit'] in ('yes', 'no', 'unknown'), 'Audience fit required')
        require(item['actor_type'] in ('external', 'team', 'spam', 'unknown'), 'Actor classification required')
        author = item['author_key']
        require(author is None or (isinstance(author, str) and author.startswith('ANON-')), 'Use anonymous author key')
        asset = posts[target]['asset_id'] if item['source_kind'] == 'own_post' else None
        # Do not preserve usernames, raw comments, private identities, or arbitrary input fields.
        event = {key: item[key] for key in ('event_id', 'source_url', 'target_url', 'source_kind',
                 'created_at', 'evidence_summary', 'classification_reason', 'category',
                 'audience_fit', 'actor_type', 'author_key')}
        event['asset_id'] = asset
        if event['event_id'] in ledger:
            require(ledger[event['event_id']] == event, 'Reaction changed: record a reviewed correction separately')
        else:
            ledger[event['event_id']] = event
            result['new_event_ids'].append(event['event_id'])
    missing = sorted((set(posts) | set(community_targets)) - set(coverage))
    result.update(events=list(ledger.values()), coverage=list(coverage.values()),
                  observed_at=raw['observed_at'], missing_post_urls=missing,
                  collection_complete=bool(coverage) and not missing and
                      all(item['status'] == 'complete' for item in coverage.values()))
    return result


def learn(feedback, metrics, previous_metrics=None):
    """Prioritize evidenced application barriers. Counts are people, never signups."""
    delta = None
    if metrics['status'] == 'measured' and previous_metrics and previous_metrics['status'] == 'measured':
        delta = metrics['new_attributed_signups'] - previous_metrics['new_attributed_signups']
    groups = {'own_post': defaultdict(set), 'community': defaultdict(set)}
    usable = []
    for item in feedback['events']:
        if item['actor_type'] == 'external' and item['audience_fit'] == 'yes' and item['author_key']:
            groups[item['source_kind']][item['category']].add(item['author_key'])
            usable.append(item)
    new_ids = set(feedback['new_event_ids'])
    prior_people = {(item['target_url'], item['author_key'], item['category'])
                    for item in usable if item['event_id'] not in new_ids}
    fresh = [item for item in usable if item['event_id'] in new_ids and
             (item['target_url'], item['author_key'], item['category']) not in prior_people]
    own = [item for item in fresh if item['source_kind'] == 'own_post']
    decision = {'kind': 'observe', 'reason': '새 적격 반응 없음; 기존 근거만으로 재수정하지 않음',
                'one_change': '현재 조건 유지하고 추가 관측', 'evidence_ids': [],
                'signup_delta': delta, 'metric_status': metrics['status'],
                'effect': 'not_established', 'publication_authorized': False,
                'reaction_summary': {source: {key: len(values[key]) for key in CATEGORIES}
                                     for source, values in groups.items()},
                'coverage_complete': feedback['collection_complete']}
    if delta is not None and delta < 0:
        decision.update(kind='audit', reason='신청 집계 정정; 효과 판단 보류', one_change='제외·귀속 정정 확인')
        return decision
    if feedback['status'] != 'collected':
        decision.update(kind='collect_reactions', reason='댓글·커뮤니티 반응 미수집; 무반응이 아님',
                        one_change='게시 이력의 URL과 커뮤니티 관측 대상을 수집 Adapter에 전달')
        return decision
    # Require a fresh member of the cluster. Old objections cannot trigger a daily rewrite.
    for category in PRIORITY:
        if not any(item['category'] == category for item in own):
            continue
        targets = {item['target_url'] for item in own if item['category'] == category}
        target = max(sorted(targets), key=lambda url: len({item['author_key'] for item in usable
                     if item['source_kind'] == 'own_post' and item['category'] == category and item['target_url'] == url}))
        related = [item for item in usable if item['source_kind'] == 'own_post' and
                   item['category'] == category and item['target_url'] == target]
        repeated = len({item['author_key'] for item in related}) >= 2
        action = {'signup_friction': ('conversion', '신청 과정의 확인된 마찰 한 곳 수정', '신청 마찰'),
                  'misunderstanding': ('message', '반응에서 드러난 오해를 만드는 설명 한 곳 수정', '제품 오해'),
                  'trust': ('trust', '실제 근거가 있는 승인·권한 설명 한 곳 보완', '신뢰 우려'),
                  'no_need': ('audience', '고객 상황의 적합성 재조사', '문제·위임 수요 불일치')}[category]
        decision.update(kind=action[0] if repeated else 'investigate',
                        reason=f'{action[2]} 반응 관측; '+('독립 작성자 2명 이상, 실험 후보' if repeated else '한 사람의 신호, 재현·추가 확인 우선'),
                        one_change=action[1] if repeated else '해당 불편의 맥락·재현 여부 확인',
                        evidence_ids=[item['event_id'] for item in related], target_category=category,
                        hypothesis=f'{action[2]}가 사전 신청을 막을 수 있다',
                        alternative='도달 대상 차이·제품 미출시·다른 신청 마찰도 설명 가능',
                        prediction='같은 문제의 반응이 줄고 확인된 신규 귀속 신청이 늘어나는지 관측',
                        next_observation='다음 24시간 반응과 신청 증분; 비교 기간·도달·귀속 범위를 함께 기록',
                        stop_rule='측정 불가·비교 조건 차이·표본 부족이면 효과 보류; 악화하면 변경 재검토',
                        fixed_conditions=['channel', 'audience hypothesis', 'offer'],
                        counterevidence_ids=[item['event_id'] for item in usable
                           if item['source_kind'] == 'own_post' and item['category'] in ('interest', 'need')])
        return decision
    if own:
        decision.update(kind='follow_up', reason='신규 고객 반응; 관심 발언은 실제 신청과 별도',
                        one_change='조건을 유지하고 관심·무관심의 이유와 실제 신청 여부 관측',
                        evidence_ids=[item['event_id'] for item in own])
    elif fresh:
        decision.update(kind='research', reason='커뮤니티 반응은 고객 문제 근거; 우리 게시·전환 효과 아님',
                        one_change='반복되는 상황·반대 근거로 고객 가설 보완',
                        evidence_ids=[item['event_id'] for item in fresh])
    elif not feedback['collection_complete']:
        decision.update(kind='collect_reactions', reason='부분 수집 또는 접근 실패; 무반응 판단 불가',
                        one_change='누락된 게시글·답글 페이지와 커뮤니티 수집 보완')
    if delta is not None and delta > 0:
        decision['reason'] += '; 신규 귀속 신청 관측, 특정 반응·변경과의 인과는 미확인'
    return decision
