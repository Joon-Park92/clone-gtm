"""Exercise the full GTM loop with synthetic adapters and a virtual 7-day clock.
No network, credentials, live approvals, or real scheduler are used.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from loop import build_run, content_hash, execute, read

START = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
CAMPAIGN = 'MOCK-MU-KO-001'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    assert read(path) == value


def identity(cfg):
    digest = content_hash(cfg['draft']['body'])
    return CAMPAIGN + '-A-' + digest[:16], digest


class MockResearch:
    def fetch(self):
        return {'status': 'observed', 'signals': [{
            'url': 'https://example.invalid/mock-customer',
            'published_at': START.isoformat(), 'problem_observed': True,
            'problem': 'SYNTHETIC: 앱에서 날짜를 바꿔 확인하기 번거롭다.',
            'fit': 'yes', 'selection_reason': 'Synthetic ICP fixture, not a real customer',
        }]}


class MockApproval:
    def __init__(self):
        self.decisions = {}

    def fetch(self, cfg, at, approve):
        asset, digest = identity(cfg)
        if asset in self.decisions:
            return copy.deepcopy(self.decisions[asset])
        if not approve:
            return {'status': 'pending'}
        result = {'status': 'approved', 'asset_id': asset, 'content_sha256': digest,
                  'scope': 'single_post', 'human_reviewed': True,
                  'channel': 'mock_threads', 'account_ref': 'mock-account',
                  'approved_at': (at - timedelta(minutes=2)).isoformat(),
                  'simulation_only': True}
        self.decisions[asset] = result
        return copy.deepcopy(result)


class MockPublisher:
    def __init__(self):
        self.receipts = {}
        self.send_calls = 0

    def fetch(self, cfg, approval, at, uncertain=False, resolve=False):
        asset, _ = identity(cfg)
        if approval['status'] != 'approved':
            return {'status': 'pending'}
        if asset in self.receipts:
            result = self.receipts[asset]
            if resolve:
                result['status'] = 'posted'  # Read receipt; never send again.
            return copy.deepcopy(result)
        self.send_calls += 1
        self.receipts[asset] = {
            'status': 'uncertain' if uncertain else 'posted', 'asset_id': asset,
            'channel': 'mock_threads', 'account_ref': 'mock-account',
            'url': 'https://example.invalid/mock-post/' + asset,
            'posted_at': (at - timedelta(minutes=1)).isoformat(),
        }
        return copy.deepcopy(self.receipts[asset])


class MockMeasurement:
    # Synthetic identities only; this is not a real email parsing/dedup adapter.
    events = [
        (2, 'existing', 'code', 'normal'),
        (2, 'test-person', 'code', 'test'),
        (2, 'spam-person', 'code', 'spam'),
        (2, 'person-a', 'code', 'normal'),
        (2, 'person-b', 'code', 'normal'),
        (2, 'person-a', 'code', 'normal'),
        (2, 'person-unknown', 'unknown', 'normal'),
        (3, 'person-c', 'code', 'normal'),
        (8, 'outside-window', 'code', 'normal'),
    ]

    def fetch(self, cfg, day, at):
        if day == 0:
            return {'status': 'pending'}
        excluded = dict.fromkeys(('existing', 'duplicate', 'test', 'spam'), 0)
        people = {}
        for arrived, person, source, category in self.events:
            if arrived > day or arrived >= 7:
                continue
            if category in ('test', 'spam'):
                excluded[category] += 1
            elif person == 'existing':
                excluded['existing'] += 1
            elif person in people:
                excluded['duplicate'] += 1
                if source == 'code':
                    people[person] = source
            else:
                people[person] = source
        return {
            'status': 'measured', 'campaign_id': CAMPAIGN, 'window': cfg['window'],
            'observed_at': at.isoformat(), 'through': at.isoformat(), 'cumulative': True,
            'baseline_verified': True, 'receipt_verified': True, 'dedup_scope': 'campaign',
            'source_method': 'email_subject_code',
            'new_attributed_signups': sum(v == 'code' for v in people.values()),
            'unknown_source_signups': sum(v == 'unknown' for v in people.values()),
            'excluded': excluded, 'evidence_refs': ['EV-MOCK-SYNTHETIC-ONLY'],
            'auxiliary': {'impressions': 200, 'visits': 5 if day == 1 else 30},
        }


class VirtualScheduler:
    def ticks(self):
        yield 0, START, 'manual_bootstrap_mock'
        for day in range(1, 8):
            yield day, START + timedelta(days=day), 'automatic_tick_mock'
        # No day 8: seven-day window is closed.


def run_demo(output):
    output.mkdir(parents=True, exist_ok=False)
    original_config = (ROOT / 'config/loop.json').read_bytes()
    live = json.loads(original_config)
    # Whitelist data so real credential references and account IDs never enter demo.
    cfg = {k: copy.deepcopy(live[k]) for k in ('schema_version', 'timezone', 'hypothesis', 'draft', 'learning')}
    cfg.update(simulation=True, campaign_id=CAMPAIGN, experiment_id='MOCK-EXP-001',
               window={'start': START.isoformat(), 'end': (START + timedelta(days=7)).isoformat()},
               attribution={'method': 'email_subject_code', 'verified': True, 'campaign_code': CAMPAIGN},
               schedule={'owner': 'virtual_scheduler_only', 'requested_mode': 'manual_start_then_daily'},
               change_note='Synthetic bootstrap, not production or real approval')
    cfg['draft']['body'] = 'MOCK ONLY: ' + cfg['draft']['body']
    research, approval, publisher, metrics = MockResearch(), MockApproval(), MockPublisher(), MockMeasurement()
    records, rows, previous, hashes, last_inputs = [], [], None, {}, None
    for day, at, trigger in VirtualScheduler().ticks():
        if day == 2:
            assert previous['next_action']['kind'] == 'message'
            lines = cfg['draft']['body'].splitlines()
            lines[0] = 'MOCK ONLY: 인기 식당 예약 확인을 카카오톡으로 부탁한다면?'
            cfg['draft']['body'] = '\n'.join(lines)
            cfg['change_note'] = 'Applied prior message recommendation: change opening line only'
        if day == 4:
            assert previous['next_action']['kind'] == 'follow_up'
            cfg['draft']['body'] += '\nMOCK ONLY: 일요일 두 명 예약 가능 여부 요청 예시.'
            cfg['change_note'] = 'Applied prior follow-up recommendation: add one request example'
        review = approval.fetch(cfg, at, approve=day not in (0, 2))
        payloads = {'research': research.fetch(), 'approval': review,
                    'publication': publisher.fetch(cfg, review, at, uncertain=day == 4, resolve=day == 5),
                    'measurement': metrics.fetch(cfg, day, at)}
        step = output / 'inputs' / f'{day:02d}'
        cfg['adapters'] = {name: {'driver': 'manual_json', 'path': name + '.json'} for name in payloads}
        for name, payload in payloads.items():
            write_json(step / (name + '.json'), payload)
        write_json(step / 'config.json', cfg)
        path, record = execute(step / 'config.json', output / 'records', now=at)
        assert record['mode'] == 'mock_simulation'
        assert record['previous_run'] == (previous['run_id'] if previous else None)
        if previous:
            assert record['previous_recommendation'] == previous['next_action']
        for old_path, digest in hashes.items():
            assert hashlib.sha256(Path(old_path).read_bytes()).hexdigest() == digest
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(record)
        rows.append({'day': day, 'trigger': trigger, 'state': record['state'],
                     'mock_signups_cumulative': record['measurement']['new_attributed_signups'],
                     'next_action': record['next_action']['kind'], 'run_id': record['run_id']})
        previous, last_inputs = record, payloads
    assert [r['state'] for r in records] == ['awaiting_approval', 'measured', 'awaiting_approval',
                                             'measured', 'publication_uncertain', 'measured', 'measured', 'measured']
    assert [r['measurement']['new_attributed_signups'] for r in records] == [None, 0, 2, 3, 3, 3, 3, 3]
    assert publisher.send_calls == 3
    assert records[2]['publication']['url'] is None  # Changed draft waits for new approval.
    assert records[-1]['measurement']['unknown_source_signups'] == 1
    assert records[-1]['measurement']['excluded'] == {'existing': 1, 'duplicate': 1, 'test': 1, 'spam': 1}
    assert all(r['next_execution']['scheduled'] is False for r in records)
    # Confirm core itself rejects forged/mismatched receipts, not just the mock publisher.
    rejected = []
    for name in ('unapproved_receipt', 'changed_draft', 'wrong_account', 'missing_baseline'):
        bad_cfg, bad_inputs = copy.deepcopy(cfg), copy.deepcopy(last_inputs)
        if name == 'unapproved_receipt':
            bad_inputs['approval'] = {'status': 'pending'}
        elif name == 'changed_draft':
            bad_cfg['draft']['body'] += ' changed after approval'
        elif name == 'wrong_account':
            bad_inputs['publication']['account_ref'] = 'another-mock-account'
        else:
            bad_inputs['measurement']['baseline_verified'] = False
        try:
            build_run(bad_cfg, bad_inputs, now=START + timedelta(days=7))
        except ValueError:
            rejected.append(name)
        else:
            raise AssertionError('Unsafe mock receipt accepted: ' + name)
    assert (ROOT / 'config/loop.json').read_bytes() == original_config
    report = {'simulation_only': True, 'campaign_id': CAMPAIGN, 'result': 'PASS',
              'manual_bootstrap_count': 1, 'virtual_daily_ticks': 7,
              'mock_publish_send_calls': publisher.send_calls, 'mock_final_signups': 3,
              'negative_cases_rejected': rejected, 'rows': rows,
              'external_calls': 0, 'real_credentials_read': False,
              'real_scheduler_registered': False, 'production_config_unchanged': True}
    write_json(output / 'summary.json', report)
    table = '\n'.join(f"| {r['day']} | {r['trigger']} | {r['state']} | {r['mock_signups_cumulative']} | {r['next_action']} |" for r in rows)
    doc = f'''# Mock GTM 루프 검증 결과

결과: PASS. 모든 고객·승인·게시·신청·시간은 합성 또는 가상 데이터다. 실제 Threads·메일·인증정보·스케줄러를 호출하지 않았다.

| 가상 일차 | 호출 | 상태 | 모의 누적 신청 | 다음 판단 |
| --- | --- | --- | --- | --- |
{table}

처음 1회 수동 시작을 모의한 뒤 가상 시계를 24시간씩 전진해 7번 반복했다. 실제 시간을 기다리거나 스케줄러를 등록한 것은 아니다. 7일 종료 뒤 추가 실행은 없다.

확인: 승인 전 게시 대기, 이전 결과 기반 문안 변경 및 새 승인, 승인 대기 중 측정 지속, 모의 기존/중복/테스트/스팸 각 1건 제외, 출처 불명 1건 별도 처리, 캠페인 누적 최종 3건 유지, 불확실 게시의 재전송 없이 영수증 확인, 이전 기록 보존. 승인 없음·승인 후 문안 변경·계정 불일치·기존 기준 미확인은 모두 코어에서 거부했다.

모의 게시 호출은 총 3회이며 가상 날짜가 지나도 같은 콘텐츠를 다시 보내지 않았다. Mock Publisher의 idempotency와 합성 신청 집계 로직은 테스트 더블이며 실서비스 Adapter 구현/보장을 뜻하지 않는다. 실제 승인 기록이나 실제 트랙션으로 사용하지 않는다.

운영 설정은 변경하지 않았고 실제 계정 비밀번호를 읽지 않았다. 입력과 각 실행 JSON은 이 폴더의 inputs/와 records/에서 재검토할 수 있다.
'''
    (output / 'report.md').write_text(doc)
    assert (output / 'report.md').read_text() == doc
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / 'runs/mock' / ('DEMO-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6])
    report = run_demo(output.resolve())
    print(json.dumps({'result': report['result'], 'simulation_only': True,
                      'virtual_daily_ticks': report['virtual_daily_ticks'],
                      'mock_final_signups': report['mock_final_signups'],
                      'report': str(output.resolve() / 'report.md')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
