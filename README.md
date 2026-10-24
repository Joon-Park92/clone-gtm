# Mu GTM Loop

Pairful Mu를 위한 7일 GTM 실험 기록 및 파일 기반 실행기. 인기 식당 예약을 위한 모바일 앱 조회·조작을 첫 고객 가설로 삼는다. 현재 제품은 사전 신청만 가능하다.

[GTM 전략·ICP](docs/gtm/strategy.md) → [PLAN](PLAN.md) → [첫 루프 설계](docs/plan/first-loop.md) → [아키텍처](docs/architecture.md) → [실험](docs/gtm/experiment.md) → [측정](docs/gtm/measurement.md) 순서로 읽는다.

사용자와 에이전트 하나가 운영한다. 외부 시스템은 Adapter 계약으로 분리한다. 실환경 연결·게시·메일 발송·스케줄러 활성화는 완료되지 않았다. 실행 방법은 구현 후 아래에 추가한다.

개인정보와 원본 신청 자료는 Git 밖의 private/에 둔다. 공개 기록에는 집계와 정제된 증거만 둔다. 미측정은 null이며 0과 다르다. 합성 테스트는 실적이 아니다.
