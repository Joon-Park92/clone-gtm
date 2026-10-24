# 아키텍처

최신 상위 설계: [높은·낮은·새 가설 병렬 비교](gtm/portfolio-loop.md). `src/portfolio.py`가 여러 가설·콘텐츠·계정별 배포를 관리하고 역할별 Rubric을 교체한다. 초기의 단일 에이전트·단일 실험 제약은 이 요구로 확장됐다. 아래 단일 게시·반응 코어는 하위 실행 계약으로 유지한다. 확률 배분은 사용하지 않으며 실제 병렬 실행 런타임은 미연결이다.

전체 이전 게시 이력 → 댓글·답글과 커뮤니티 반응 수집 + 실제 신청 집계 → 전환 병목 판단 → 변경 하나 → 보조 콘텐츠 검토·사람 승인 → 실행 → 반응·신청 재관측.

2026-10-24 검토 결론: 세 모듈을 파일과 안정적인 ID로 연결한다. 최초 한 번 수동 시작한 뒤 에이전트 런타임이 하루 한 번 반복하도록 설계한다. 실제 게시에는 사람의 최종 검토가 필요하다. DB·대시보드·Plugin은 도입하지 않는다. 생성·검토 등 역할별 에이전트는 최신 병렬 설계에서 Adapter로 분리한다. 실제 MCP·배포 서비스 구현은 연기하고 Adapter 입출력 계약과 상태 전이를 먼저 완성한다.

## 모듈

| 모듈 | 입력 | 출력 |
| --- | --- | --- |
| 실험 실행 | 제품 설명, 설정, 이전 실행, ResearchAdapter | 원문 근거, 가설, 콘텐츠 초안 |
| 배포 기록 | 초안, 사람 승인, PublishAdapter | asset_id, 승인 범위, 실제 URL·시각 또는 대기 상태 |
| 성과·학습 | MeasurementAdapter, 기존 신청자 기준, 기간 | 캠페인 누적 중복 제거 집계, 근거, 다음 변경 |

## 경계

- ResearchAdapter: 원문 URL·게시 시각·불편·제품 적합성·선정 이유를 반환한다. 없으면 unconnected이다. 초안 작성 자체는 가능하나 고객 검증이라고 부르지 않는다.
- DraftAdapter: 콘텐츠와 CTA를 반환한다. 정적 초안을 기본 제공하고 추후 모델/MCP 연결을 허용한다.
- ApprovalAdapter: 사람이 검토한 정확한 본문, asset_id, 채널, 계정, 범위의 승인 기록을 반환한다. 기본 pending.
- PublishAdapter: posted, pending, failed, uncertain 중 상태와 영수증을 반환한다. 기본 미연결. 불확실하면 자동 재게시 금지.
- MeasurementAdapter: 기간·기존 신청자 기준·귀속·접수 증거를 확인한 캠페인 누적 스냅샷을 반환한다. 실메일 조회와 중복 제거는 Adapter 책임이며 코어는 계약을 검사한다.
- SchedulerAdapter: 최초 수동 시작 후 24시간 간격으로 에이전트 런타임을 호출한다. 현재 미연결이며 다음 실행 제안과 실제 등록을 구분한다.

## ID와 상태

campaign_id는 7일 실험 전체에 고정한다. experiment_id는 한 가설의 버전, run_id는 한 실행, asset_id는 한 콘텐츠를 식별한다. 같은 콘텐츠의 재시도에 새 asset_id를 붙여 중복 게시하지 않는다.

실행은 research_pending/draft_ready → awaiting_approval → awaiting_publication/ publication_uncertain → awaiting_measurement → measured로 진행한다. 게시 승인과 성과 수집은 독립 조건이며, 과거 게시 성과는 오늘 게시 여부와 관계없이 수집할 수 있다.

실행 기록은 덮어쓰지 않는다. 코어는 잠금을 통해 동시 실행을 막는다. 외부 게시를 호출하지 않는 첫 버전은 사람이 받은 게시 영수증을 입력으로 기록한다. 향후 게시 Adapter는 asset_id를 idempotency key로 사용하고 uncertain 상태를 먼저 조회한다.

## 검토한 위험과 결정

- UTM만으로 완료 측정 불가: 실제 접수·기존 신청자 기준·기간이 확인된 스냅샷만 인정한다.
- 신청자 개인정보 노출: 코어 출력은 허용된 집계 필드만 저장한다. 원문 메일/개인 식별자는 private/ 및 MCP 경계 안에 둔다.
- 누적 집계 중복: 최신 캠페인 스냅샷을 사용하고 일별 누적값을 합하지 않는다.
- 접근 가정과 연결 검증 혼동: configured/assumed와 connected/verified를 구분한다.
- 승인 없이 외부 실행: 첫 구현은 외부 실행 자체를 포함하지 않는다. 실환경 Adapter 구현 때 동일 승인 계약을 적용한다.
- 작은 표본의 과잉 해석: 관측과 해석을 분리하고 다음 실험에서 주요 조건 하나만 바꾼다.

## 설계와 구현 경계

[첫 루프 실행 계약](plan/first-loop.md)이 단계별 완료 조건의 기준이다. 현재 src/loop.py는 unconnected/manual_json 입력을 기록하는 로컬 코어 초안이다. DraftAdapter와 SchedulerAdapter는 각각 설정 문안과 수동 일정 제안으로만 표현되며 별도 호출 구현이 없다. 실메일 접수·중복 제거, 외부 게시, 모델을 통한 초안 개선은 미구현이다. research_pending/draft_ready는 개념상 단계이고 코어에서는 research.status 및 asset으로 표현한다. 게시 전 지원 범위·신청 경로 등의 종합 검토는 현재 에이전트/사람이 수행하며 코어가 모두 강제하지는 않는다.

현재 운영 기준은 [반복 운영](plan/operation-loop.md)이다. 이전 수동 운영 제안은 사용자 요청으로 변경됐다. 구체 런타임·스케줄러 연결은 여전히 유보 상태이며 게시 전 최종 검토는 계속 필요하다.

## 보조 콘텐츠 검토 단계 (주 학습 루프에서 분리)

[Rubric](gtm/rubric.md)을 기준으로 초안 평가 → 약점 하나 → 수정 → 같은 기준 재평가를 게시 검토 앞에 둔다. EvaluationAdapter는 버전·본문 해시·근거·항목별 판단을 반환한다. src/refinement.py가 계약과 후보 선택을 검사하고 src/loop.py는 content_review를 실행 기록에 남긴다. 비교 artifact에는 평가 원문과 수정 가설을 보존한다. 모델 호출은 추상화 상태이고 Mock으로 판단 코어를 검증했다.

성과 진단은 누적 신청의 증가 여부를 확인한다. 같은 양수 누적값을 매일 새로운 성공으로 취급하지 않고, 감소 시 집계 감사로 보낸다. 실제 결과와 편집 평가를 별도 기록하며 세부 계약은 Rubric 문서와 prompts/review-and-refine.md에 있다.

## 사용자 반응으로 다음 행동 선택

FeedbackAdapter는 모든 과거 게시 URL과 설정한 커뮤니티 대상을 받아 정제된 반응·수집 범위·누락 이유를 반환한다. 코어는 캠페인의 모든 기록에서 published_posts를 구성해 최신 문안과 무관하게 과거 글의 반응을 연결한다. feedback 이벤트 이력과 새 event_id를 보존한다.

next_action은 src/feedback.py의 반응 기반 학습으로 결정한다. 기존 노출·방문·신청 집계만의 추천은 metric_diagnostic으로 분리한다. 콘텐츠 점수는 실험 선택을 주도하지 않는다. src/refinement.py는 선택된 실험의 표현을 검토하는 보조다. 상세 판단 축·조건은 docs/gtm/rubric.md에 있다.

실제 조회·분류는 Adapter/에이전트 책임이며 현재 미연결이다. 원문 진실성과 분류 타당성, 전후 조건을 고려한 인과 판단까지 코어가 보증하지 않는다. 합성 반응으로 계약·반복·수정 흐름을 검증했다.
