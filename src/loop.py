"""File-based GTM coordinator. Adapters supply sanitized facts; no network effects."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def timestamp(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return dt


def require(condition, message):
    if not condition:
        raise ValueError(message)


def count(value):
    require(type(value) is int and value >= 0, 'Counts must be nonnegative integers')
    return value


def content_hash(body):
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


class Adapter(Protocol):
    def fetch(self, context: dict) -> dict: ...


class UnconnectedAdapter:
    def fetch(self, context):
        return {'status': 'unconnected'}


class JsonAdapter:
    """Read-only bridge for a human/agent/MCP to supply sanitized receipts."""
    def __init__(self, path):
        self.path = path

    def fetch(self, context):
        return read(self.path)


def adapter(spec, base):
    if spec['driver'] == 'unconnected':
        return UnconnectedAdapter()
    if spec['driver'] == 'manual_json':
        return JsonAdapter(base / spec['path'])
    raise ValueError('Unimplemented adapter driver: ' + spec['driver'])


def measurement(raw, cfg, now):
    if raw.get('status') != 'measured':
        require(raw.get('status') in ('unconnected', 'pending'), 'Invalid measurement status')
        return {'status': raw['status'], 'new_attributed_signups': None,
                'unknown_source_signups': None, 'auxiliary': None}
    window = cfg['window']
    require(window['start'] and window['end'], 'Measurement window not fixed')
    start, end = timestamp(window['start']), timestamp(window['end'])
    require(end - start == timedelta(days=7), 'Window must be exactly seven days')
    observed = timestamp(raw['observed_at'])
    through = timestamp(raw['through'])
    require(start <= through <= min(end, observed) and observed <= now,
            'Invalid measurement cutoff/observation time')
    require(raw['campaign_id'] == cfg['campaign_id'], 'Wrong measurement campaign')
    require(cfg['attribution']['verified'] is True, 'Attribution setup must be verified')
    require(raw['source_method'] == cfg['attribution']['method'], 'Attribution method mismatch')
    require(raw['window'] == window and raw['cumulative'] is True, 'Expected cumulative campaign snapshot')
    require(raw['baseline_verified'] is True and raw['receipt_verified'] is True,
            'Existing applicants and actual receipts must be verified')
    require(raw['dedup_scope'] == 'campaign', 'Deduplication must span campaign')
    require(raw['source_method'] in ('preserved_code', 'email_subject_code', 'self_report'),
            'Unknown attribution method')
    require(raw['evidence_refs'] and all(re.fullmatch(r'EV-[A-Za-z0-9_-]+', x)
            for x in raw['evidence_refs']), 'Use sanitized evidence IDs')
    exclusions = {k: count(raw['excluded'][k]) for k in ('existing', 'duplicate', 'test', 'spam')}
    auxiliary = {k: None if raw.get('auxiliary', {}).get(k) is None else count(raw['auxiliary'][k])
                 for k in ('impressions', 'visits')}
    # Never serialize raw adapter payloads, applicant identities, or emails.
    return {'status': 'measured', 'new_attributed_signups': count(raw['new_attributed_signups']),
            'unknown_source_signups': count(raw['unknown_source_signups']),
            'observed_at': raw['observed_at'], 'through': raw['through'],
            'cumulative': True, 'source_method': raw['source_method'],
            'excluded': exclusions, 'evidence_refs': raw['evidence_refs'], 'auxiliary': auxiliary}


def decide(metrics, cfg):
    if metrics['status'] != 'measured':
        return {'kind': 'observe', 'reason': '미측정: 성과 판단 보류',
                'one_change': 'MeasurementAdapter 연결 및 접수·기준 검증'}
    n = metrics['new_attributed_signups']
    if n > 0:
        return {'kind': 'follow_up', 'reason': '귀속 신청 관측; 인과 효과는 미확인',
                'one_change': '같은 고객 문제에서 콘텐츠의 요청 예시 하나 변경'}
    a, thresholds = metrics['auxiliary'], cfg['learning']
    impressions, visits = a['impressions'], a['visits']
    if impressions is None or visits is None:
        return {'kind': 'observe', 'reason': '보조 지표 미측정', 'one_change': '보조 지표 수집 연결'}
    if impressions < thresholds['minimum_impressions']:
        return {'kind': 'distribution', 'reason': '노출 표본 부족; 메시지 효과 판단 보류',
                'one_change': '배포 경로 하나 점검'}
    if visits < thresholds['minimum_visits']:
        return {'kind': 'message', 'reason': '노출 대비 방문 표본 부족; 원인 미확정',
                'one_change': '메시지 첫 문장 하나 변경'}
    return {'kind': 'conversion', 'reason': '방문은 있으나 확인된 신청 없음; 원인 미확정',
            'one_change': '설명·신청·추적 과정 중 병목 하나 확인'}


def build_run(cfg, inputs, previous=None, now=None):
    now = now or datetime.now(timezone.utc)
    require(cfg['schema_version'] == 1, 'Unsupported config schema')
    if cfg.get('simulation'):
        require(cfg['campaign_id'].startswith('MOCK-'), 'Simulation needs isolated MOCK campaign')
    for key in ('campaign_id', 'experiment_id'):
        require(re.fullmatch(r'[A-Za-z0-9_-]+', cfg[key]), 'Invalid ID')
    body = cfg['draft']['body']
    digest = content_hash(body)
    asset_id = cfg['campaign_id'] + '-A-' + digest[:16]
    approved = inputs['approval']
    publication = inputs['publication']
    require(approved.get('status') in ('unconnected', 'pending', 'approved'), 'Invalid approval status')
    approval_ok = approved.get('status') == 'approved'
    if approval_ok:
        require(approved['asset_id'] == asset_id and approved['content_sha256'] == digest,
                'Approval must match exact draft')
        require(approved['scope'] == 'single_post' and approved['human_reviewed'] is True,
                'Human single-post review required')
        require(bool(approved['channel']) and bool(approved['account_ref']), 'Approval target required')
        require(timestamp(approved['approved_at']) <= now, 'Approval cannot be in future')
    pstatus = publication.get('status')
    require(pstatus in ('unconnected', 'pending', 'failed', 'uncertain', 'posted'), 'Invalid publication status')
    receipt = {'status': pstatus, 'url': None, 'posted_at': None}
    if pstatus in ('posted', 'uncertain', 'failed'):
        require(approval_ok, 'Publication receipt requires matching approval')
        require(publication['asset_id'] == asset_id, 'Wrong publication asset')
        require(publication['channel'] == approved['channel'] and
                publication['account_ref'] == approved['account_ref'], 'Publication target mismatch')
    if pstatus == 'posted':
        require(publication['url'].startswith('https://'), 'Public post URL required')
        require(timestamp(approved['approved_at']) <= timestamp(publication['posted_at']) <= now,
                'Publication must follow approval')
        receipt.update(url=publication['url'], posted_at=publication['posted_at'])
    approval_record = {'status': approved['status'], 'matched': approval_ok}
    if approval_ok:
        approval_record.update({k: approved[k] for k in ('asset_id', 'content_sha256', 'channel', 'account_ref', 'scope', 'approved_at', 'human_reviewed')})
    if previous and previous['asset']['asset_id'] == asset_id:
        prior = previous['publication']
        if prior['status'] == 'posted':
            require(pstatus != 'posted' or receipt['url'] == prior['url'],
                    'Duplicate publication for same asset; reconcile manually')
            receipt = prior
            approval_record = previous['approval']
        elif prior['status'] == 'uncertain' and pstatus != 'posted':
            receipt = prior
    research = inputs['research']
    require(research.get('status') in ('unconnected', 'pending', 'observed'), 'Invalid research status')
    signals = []
    if research['status'] == 'observed':
        require(0 < len(research['signals']) <= 10, 'Research needs 1–10 sources')
        for item in research['signals']:
            require(item['url'].startswith('https://'), 'Source URL required')
            require(item['problem_observed'] is True, 'Customer problem must be observed')
            require(item['fit'] in ('yes', 'no', 'uncertain'), 'Invalid product fit')
            if item['published_at'] is not None:
                require(timestamp(item['published_at']) <= now, 'Source date in future')
            signals.append({k: item[k] for k in ('url', 'published_at', 'problem', 'fit', 'selection_reason')})
    metrics = measurement(inputs['measurement'], cfg, now)
    if previous and metrics['status'] == 'measured' and previous['measurement']['status'] == 'measured':
        require(timestamp(metrics['through']) >= timestamp(previous['measurement']['through']),
                'Snapshot cutoff cannot go backward')
    if receipt['status'] == 'uncertain':
        state = 'publication_uncertain'
    elif receipt['status'] == 'posted':
        state = 'measured' if metrics['status'] == 'measured' else 'awaiting_measurement'
    else:
        state = 'awaiting_publication' if approval_ok else 'awaiting_approval'
    return {
        'schema_version': 1, 'run_id': 'RUN-' + now.strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:6],
        'campaign_id': cfg['campaign_id'], 'experiment_id': cfg['experiment_id'],
        'started_at': now.isoformat(), 'timezone': cfg['timezone'], 'state': state,
        'mode': 'mock_simulation' if cfg.get('simulation') else 'local_coordination', 'previous_run': previous['run_id'] if previous else None,
        'hypothesis': cfg['hypothesis'],
        'previous_recommendation': previous['next_action'] if previous else None,
        'change_note': cfg['change_note'],
        'research': {'status': research['status'], 'signals': signals},
        'asset': {'asset_id': asset_id, 'body': body, 'content_sha256': digest,
                  'cta': cfg['draft']['cta'], 'attribution': cfg['attribution']},
        'approval': approval_record,
        'publication': receipt, 'measurement': metrics,
        'next_action': decide(metrics, cfg),
        'next_execution': {'suggested_at': (now + timedelta(days=1)).isoformat(),
                           'owner': cfg['schedule']['owner'], 'scheduled': False,
                           'mode': ('automatic_pending_connection' if cfg['schedule'].get('requested_mode') == 'manual_start_then_daily' else 'manual')},
        'adapter_status': {name: value['status'] for name, value in inputs.items()},
    }


def execute(config_path, output, now=None):
    cfg = read(config_path)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / '.loop.lock'
    try:
        handle = lock.open('x')
    except FileExistsError:
        raise ValueError('Another run may be active; inspect lock before recovery')
    try:
        handle.write(datetime.now(timezone.utc).isoformat())
        handle.close()
        previous = None
        records = [read(p) for p in output.glob('RUN-*.json')]
        records = [r for r in records if r['campaign_id'] == cfg['campaign_id']]
        if records:
            previous = max(records, key=lambda r: timestamp(r['started_at']))
        inputs = {name: adapter(cfg['adapters'][name], config_path.parent).fetch({'config': cfg, 'previous': previous})
                  for name in ('research', 'approval', 'publication', 'measurement')}
        result = build_run(cfg, inputs, previous, now=now)
        target = output / (result['run_id'] + '.json')
        # Exclusive creation plus a lock prevents silent history replacement.
        with target.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        require(read(target) == result, 'Run readback mismatch')
        return target, result
    finally:
        handle.close()
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/loop.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs')
    args = parser.parse_args()
    try:
        path, result = execute(args.config.resolve(), args.output.resolve())
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.exit(1, f'Loop stopped without external actions: {error}\n')
    print(json.dumps({'run_file': str(path), 'state': result['state'],
                     'new_attributed_signups': result['measurement']['new_attributed_signups'],
                     'next_action': result['next_action']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
