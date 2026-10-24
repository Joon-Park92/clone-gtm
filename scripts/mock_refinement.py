"""One complete synthetic critique/revision/review cycle; no model or external API."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from refinement import VERSION, CRITERIA, compare, digest

BASE = '토요일 두 명 예약 가능 시간, 앱에서 확인하기 번거로운가요?\nMu는 카카오톡으로 모바일 앱 작업을 부탁하는 비서입니다.\n현재 사전 사용 신청 단계입니다.\n제품을 보고, 댓글도 남기고, 신청도 해주세요.'
CANDIDATE = BASE.replace('제품을 보고, 댓글도 남기고, 신청도 해주세요.', 'Mu 사전 사용 신청 안내: https://example.invalid/mock-signup')


def review(body, cta_score):
    evidence = {'DRAFT': {'kind': 'draft_excerpt', 'excerpt': body, 'source_ref': 'mock:draft',
                           'observation': 'Synthetic editorial fixture, not user feedback'},
                'PRODUCT': {'kind': 'mock_product', 'source_ref': 'mock:product-spec',
                            'observation': 'Synthetic spec describes early access and app delegation'}}
    reasons = {'customer_situation': '날짜·인원·앱 조회 행동이 드러남',
               'delegation_value': '카카오톡으로 앱 작업을 부탁하는 방식 명시',
               'product_honesty': '사전 사용 신청 단계 명시',
               'cta_clarity': '여러 행동 요청이 경쟁함' if cta_score == 1 else '신청 행동 하나로 정리됨'}
    return {'status': 'reviewed', 'rubric_version': VERSION, 'content_sha256': digest(body),
            'evidence': evidence,
            'criteria': {key: {'score': cta_score if key == 'cta_clarity' else 2,
                               'reason': reasons[key], 'evidence_refs': ['DRAFT']} for key in CRITERIA},
            'gates': {key: {'status': 'pass', 'reason': 'Synthetic fixture only',
                            'evidence_refs': ['DRAFT', 'PRODUCT']} for key in ('claims_supported', 'early_access_clear')}}


def proposal():
    return {'parent_sha256': digest(BASE), 'candidate_sha256': digest(CANDIDATE),
            'target_criterion': 'cta_clarity', 'changed_variables': ['cta_sentence'], 'attempt': 1,
            'hypothesis': '여러 행동 요청이 신청 행동의 명확성을 낮춘다',
            'prediction': 'CTA 하나로 정리하면 신청으로 이어지는 경로를 더 쉽게 이해할 수 있다',
            'observe_next': '실제 기간·노출·귀속 범위가 비교 가능한 방문과 신규 신청 및 혼동 응답',
            'stop_rule': '새 근거가 없으면 유지; 실제 오해·마찰이 확인되면 수정; 인과적 승자 선언 안 함',
            'fixed_context': {'channel': 'mock_threads', 'audience': 'restaurant-checking', 'offer': 'early_access'}}


def run_demo(output):
    result = compare(review(BASE, 1), review(CANDIDATE, 2), BASE, CANDIDATE, proposal())
    assert result['decision'] == 'candidate_for_human_review'
    assert not result['publication_authorized']
    assert result['market_validation'] == 'pending_real_observation'
    output.mkdir(parents=True, exist_ok=False)
    payload = {'simulation_only': True, 'baseline': BASE, 'candidate': CANDIDATE,
               'baseline_review': review(BASE, 1), 'candidate_review': review(CANDIDATE, 2), 'result': result}
    path = output / 'review.json'; path.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
    assert json.loads(path.read_text()) == payload
    report = '''# Mock 자기개선 판단 검증

콘텐츠 평가 → 가장 약한 CTA 항목 선택 → CTA 문장 하나 수정 → 같은 Rubric으로 재평가 → 사람 검토 후보까지 진행했다.

CTA 점수는 합성 평가에서 1→2, 나머지 세 항목은 2 유지다. 단일 개선 가설·예측·다음 관측·중단 조건을 기록했다. 결과는 candidate_for_human_review이며 게시 승인은 false, 실제 성과 검증은 pending이다.

작성과 평가를 실제 LLM으로 호출한 결과가 아니라 Mock 평가 입력과 판단 코어의 통합 검증이다. 점수 상승을 전환 개선이나 고객 반응으로 해석하지 않는다. 입력·근거·이유·후보·결정은 review.json에 있다.
'''
    (output / 'report.md').write_text(report)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    path=args.output or ROOT/'runs/mock'/('REFINE-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6])
    result=run_demo(path)
    print(json.dumps({'decision':result['decision'],'market_validation':result['market_validation'],
                      'publication_authorized':False,'report':str(path/'report.md')},ensure_ascii=False))
