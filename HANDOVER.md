# Mu GTM Loop — 다음 세션 인계

기준일: 2026-10-24, Asia/Seoul. 작업 폴더: `/home/sean/personal/clone-project`.
최신 방향: 사용자 반응·신청 전환 중심으로 수정. git log에서 최신 커밋을 확인한다. 콘텐츠 평가 중심의 af59f12 설계는 보조 검토로 변경됐다.

## 바로 시작할 일

설명을 처음부터 반복하거나 인프라 연결 질문으로 시간을 쓰지 말고 다음 순서로 진행한다.

1. 이 문서, `PLAN.md`, `docs/gtm/rubric.md`, `config/loop.json`을 읽고 Git 상태를 확인한다.
2. 사용자의 최우선은 **루프 안에서 스스로 개선하는 판단 구조**다. 구체 MCP·게시·메일·스케줄러 구현은 Adapter로 추상화하고 미룬다.
3. 이전 게시글의 댓글·답글과 관련 커뮤니티 반응을 수집할 대상을 만든다. 현재 실제 posted URL은 없다. docs/gtm/reaction-collection.md를 읽고 실제 반응·신청에서 병목을 선택한다. 콘텐츠 점수를 이유로 CTA를 먼저 고치지 않는다.
4. 원본과 후보, 전후 평가, 수정 변수 하나, 예측, 다음 관측, 중단 조건을 실행 artifact로 남긴다. `prompts/review-and-refine.md`를 따른다.
5. 필요 시 Mock으로 검증하고 활동 이력·발표 문서를 갱신한다. 실제 게시 전 최종본을 사용자에게 보여주고 명시 승인을 받는다.

현재 외부 실행을 기다릴 필요 없이 가능한 일은 게시 이력·커뮤니티 관측 대상 준비와 반응 수집·학습 기록 정교화다. 외부 연결·수신 확인·게시·반복 등록은 별도 미완료 작업이다.

## 사용자 결정과 권한

- 제품: Pairful Mu. 카카오톡 요청으로 모바일 앱을 직접 조작하는 개인 비서. 현재 사전 사용 신청 단계이며 실제 기능 데모는 미확인.
- 첫 ICP 가설: 인기 식당 예약을 위해 모바일 앱에서 날짜·시간·인원을 확인하는 사람.
- 첫 메시지: 식당 예약 가능 여부 확인 → 모바일 앱 작업을 메신저로 위임 → 범용 Mu 소개 → 사전 신청.
- 예약 성공·좌석 선점·즉시 이용·모든 앱에서의 성공을 약속하지 않는다. ‘모바일 앱 자동화’와 ‘예약은 모바일에서만 가능’이라는 미검증 주장을 구분한다.
- 첫 채널: Threads. 공개 계정 `@mu.agent`. 계정 생성과 아이디는 사용자 확인, 프로필·로그인·게시 연결 검증 전.
- 최초 한 번 수동 시작, 이후 하루 한 번 반복하도록 설계. 실제 런타임·스케줄러 등록은 아직 없다.
- **실제 게시마다 제목·본문·첨부물·링크·채널·계정 최종 검토 및 명시 승인 필요.** 변경 시 재검토. 일반 진행 지시는 게시 승인이 아니다.
- 로컬 파일 작성·코드·Mock·Git 기록은 승인됨. 외부 게시·DM·메일 발송·유료 집행·원격 공개는 승인되지 않음.
- 메일함은 MCP로 접근 가능하다고 설계상 가정한다. 실제 연결 완료로 표현하지 않는다.
- 발표 문서는 주요 결정·실행·검증마다 계속 업데이트한다.

## 저장된 주요 문서

- 진입점: `PLAN.md`, `README.md`
- 전략·측정: `docs/gtm/strategy.md`, `experiment.md`, `measurement.md`, `attribution-setup.md`
- 자기개선: `docs/gtm/rubric.md`, `prompts/review-and-refine.md`, `prompts/run-loop.md`
- 게시 검토본: `docs/gtm/publish-packet.md`
- Threads 배포: `docs/gtm/zero-audience-distribution.md`
- 외부 청중용 루트 발표 문서: `PRESENTATION.md` (단계별 기준·Rubric·개선 구조). 주요 변경 시 함께 갱신.
- 상세 발표·현황 문서: `docs/gtm/presentation.md`
- 운영·이력: `docs/plan/operation-loop.md`, `first-loop.md`, `activity-log.md` (최신 E013)
- 아키텍처: `docs/architecture.md`, `docs/adr/0001-file-based-loop.md`
- 근거: `docs/ref/product.md`, `hackathon-requirements.md`, `customer-channel-research.md`, `evidence/`
- 실행 템플릿: `runs/TEMPLATE.md`

## 구현과 검증 상태

Python 표준 라이브러리 기반이며 별도 설치 없이 실행한다.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/mock_loop.py
python3 scripts/mock_refinement.py
```

최근 검증은 **32개 테스트 PASS**다. 위 Mock 명령은 매번 새 `runs/mock/` 디렉터리를 만든다. 문서만 수정했다면 테스트를 불필요하게 반복할 필요는 없다.

- `src/loop.py`: unconnected/manual_json Adapter, 입력 계약 검증, 사람 승인·본문 해시·게시 영수증 연결, 누적 신청 집계 검증, 이전 실행 참조, 잠금·새 실행 파일 기록.
- `config/loop.json`: 실제 캠페인 `MU-KO-001`, 기간 미확정, 귀속 미검증. research는 정제된 JSON 입력이고 approval/publication/measurement/evaluation은 unconnected.
- `src/refinement.py`: Rubric `mu-content-v1`. 고객 상황·위임 가치·제품 정직성·CTA 명확성 각 0/1/2/null, 근거·인용·본문 해시·버전 검증. 사실 조건 우선, 약점 한 개, 타깃 개선과 다른 항목 비퇴행, 최대 2회, 사람 검토 후보 판정.
- `scripts/mock_refinement.py`: 고정된 합성 평가로 CTA 경쟁 → 단일 CTA → 재평가를 검증. 모델을 실제 호출하는 자율 작성·비평은 아직 아님.
- `scripts/mock_loop.py`: Mock Adapter와 가상 시계로 최초 시작+일별 7회. 승인 대기·재검토·불확실 게시 복구·신청 제외/중복·누적 집계·종료를 검증. 실제 계정·메일·인증파일을 사용하지 않음.
- `next_action`은 진단 후보이지 자동 변경 명령이 아니다. 누적 신청이 그대로이면 관측 유지, 감소하면 집계 감사. 실제 고객 반응과 편집 점수는 별개다.

보존된 증거:

- `runs/mock/DEMO-20261024T075844-295138/report.md`: 가상 7일 흐름. 합성 누적 신청 0→2→3. 실제 성과 아님.
- `runs/mock/REFINE-20261024T080325-90fa7f/report.md`, `review.json`: CTA 합성 평가 1→2, 사람 검토 후보, 게시 승인 false, 실제 성과 검증 pending.
- `runs/RUN-20261024T075232220733Z-587ee4.json`와 `.md`: 최근 실제 로컬 조정 실행. 외부 게시·측정 없음.

현재 구현 한계:

- Rubric은 근거 형식·인용 일치 등을 검사하지만 출처 진실성·판단 타당성을 자동 보증하지 않는다.
- 단일 변경은 선언을 검사한다. 실제 diff 범위와 같은 기준본의 누적 수정 횟수는 런타임/사람 검토 책임이며 영속 강제 구현 전이다.
- 평가 요약은 run에 저장한다. 평가 원문과 수정 제안은 별도 artifact로 보존해야 한다.
- 기준본의 사실 조건 실패는 최적화보다 사실 수정이 먼저다. 수정 후 새 기준본으로 평가한다.
- 게시 이력 복구는 직전 동일 asset 기준이다. 캠페인 전체 영속 중복 방지가 완성됐다고 말하지 않는다.
- 자동 모델 작성·비평, 실제 게시, 실메일 중복 제거, 영속 스케줄러는 미연결이다.

## 측정과 확인된 사실

주 지표는 ‘7일 동안 이번 캠페인에 귀속되는 중복 없는 신규 사전 신청자 수’다. 실제 접수 확인, 기존 신청자·중복·내부 테스트·스팸 제외, 캠페인 전체 중복 제거가 필요하다. 출처 불명은 별도. 클릭·메일 작성창 열기는 신청 완료가 아니다. 미측정은 0이 아니며 누적 스냅샷을 더하지 않는다.

- 실제 `/ko` 신청 CTA는 `/w/go/ko`에서 공개 지원 이메일로 연결된다. 증거: `docs/ref/evidence/mu-cta-20261024.json`.
- CTA URL에 붙인 campaign_id/UTM은 확인한 mailto 제목·본문에 보존되지 않았다. 서버 분석 여부는 미확인.
- 제목 `[MU-KO-001]`은 유입 귀속용 내부 코드 제안이다. 할인 코드가 아니다. 사용자가 의미를 질문했으며 채택·적용·실수신 검증은 미완료.
- 공개 원문 3건·채널 3곳을 조사했다. 반복 조회 행동을 관찰했지만 위임·구매 의사는 검증하지 못했다.
- 첫 채널은 Threads로 확정됐다. 이전 Disquiet 주경로 제안은 최신 결정이 아니다.
- 실제 게시: 미실행. 신규 귀속 신청: 미측정. 실제 반복 등록: 미실행.
- 대회는 7일 실제 GTM 성과와 객관 증거로 평가. 정확한 측정 시작·종료와 최종 제출 방식은 확인 필요. 상세는 요구사항 문서에 보존했다.

## 남은 외부 연결 작업

독립적으로 가능한 문안·판단 구조 작업을 먼저 진행하고 다음은 별도 체크한다.

1. Threads 프로필·로그인·게시 Adapter 연결 검증.
2. 신청 귀속 방법 결정, 실제 수신·기존 신청자 기준·중복 제외·측정 기간 확정.
3. 에이전트 런타임·SchedulerAdapter 연결 및 등록 영수증 확인.
4. 최종 게시물 사용자 검토·명시 승인 후 첫 게시 및 URL·시각 기록.
5. 실제 관측을 이전 예측과 비교해 유지/관측/수정/감사를 결정하고 발표 갱신.

## 인증정보와 환경 주의

사용자가 명시적으로 요청해 로그인 인증정보를 `private/credentials/threads.json`에 로컬 저장했다. 파일 0600, 디렉터리 0700, `private/`는 .gitignore 제외이며 Git에 추가하지 않았다. 이 문서·대화 출력·커밋에 비밀번호를 복사하지 않는다. 인계에 인증파일을 읽을 필요가 없다. 공개 설정에는 파일 경로와 공개 계정만 있다.

이 환경에서는 일반 shell 실행이 `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`로 실패했고, 승인 검토를 거친 `sandbox_permissions: require_escalated`의 로컬 작업은 성공했다. 새 세션에서 환경을 확인하고 파일 작성·재읽기를 실제 수행한다. 오류가 나면 저장했다고 주장하지 않는다. 승인 자동 검토 거부가 발생한 경우 그 사유를 별도로 알린다.

이전 연구·귀속·게시 패킷 subagent 작업은 끝났다. 현재 병렬 작업이 진행 중이라고 가정하지 않는다. 새로운 외부 도구 연결 유무는 필요할 때 실제 도구 목록에서 확인한다.

## 다음 세션에 붙여넣을 메시지

> `/home/sean/personal/clone-project/HANDOVER.md`를 읽고 이어서 실행해줘. 현재 우선순위는 인프라 연결보다 근거 기반 Rubric과 자기개선 루프다. 먼저 이전 게시물 댓글·답글과 관련 커뮤니티 반응의 수집 대상을 확인하고, 실제 반응·신청에 기반한 병목 판단과 다음 실험을 준비해 실행 기록과 발표 문서를 업데이트해줘. 콘텐츠 점수 최적화를 주 루프로 삼지 마라. 구체 연동은 Adapter/Mock으로 유지해도 된다. 실제 게시 전에는 반드시 내 검토와 명시 승인을 받아라. 변경은 실제 파일로 저장하고 Git 이력에 남겨라.

## 최신 변경 — 반응 중심 학습이 우선

- 주 Rubric: docs/gtm/rubric.md. 이전 콘텐츠 기준은 content-checklist.md로 이동했다.
- 수집 계약: docs/gtm/reaction-collection.md. FeedbackAdapter는 unconnected/manual_json. 실제 댓글 API 수집은 아직 없다.
- src/feedback.py: 전체 과거 게시 URL에 연결된 반응, 커뮤니티 구분, 수집 누락·중복·독립 작성자, 병목 선택. next_action은 반응 기반이며 기존 수치 규칙은 metric_diagnostic에만 남긴다.
- 32개 테스트 및 최신 7일 Mock 통과: runs/mock/DEMO-20261024T081424-142339/report.md. 합성 반응 5건으로 제품 오해→설명 수정, 신청 마찰→안내 수정, 재수집→유지를 검증했다.
- 원문 수집·분류·ICP 판정은 Adapter/에이전트 책임이다. 코어는 입력과 선택 규칙을 검사하며 실제 모델 판단이나 인과 효과를 검증하지 않는다.
- 동일 event_id의 관측 변경은 거부한다. 정정·삭제·재분류 자동 처리와 전후 비교의 종합 효과 판단은 미구현이다.
