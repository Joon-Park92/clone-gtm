# Mu GTM Loop

Pairful Mu를 위한 7일 GTM 실험 기록 및 파일 기반 실행기. 인기 식당 예약을 위한 모바일 앱 조회·조작을 첫 고객 가설로 삼는다. 현재 제품은 사전 신청만 가능하다.

[GTM 전략·ICP](docs/gtm/strategy.md) → [PLAN](PLAN.md) → [첫 루프 설계](docs/plan/first-loop.md) → [아키텍처](docs/architecture.md) → [실험](docs/gtm/experiment.md) → [측정](docs/gtm/measurement.md) 순서로 읽는다.

사용자와 에이전트 하나가 운영한다. 외부 시스템은 Adapter 계약으로 분리한다. 실환경 연결·게시·메일 발송·스케줄러 활성화는 완료되지 않았다. 로컬 코어 실행 방법은 아래와 같다.

개인정보와 원본 신청 자료는 Git 밖의 private/에 둔다. 공개 기록에는 집계와 정제된 증거만 둔다. 미측정은 null이며 0과 다르다. 합성 테스트는 실적이 아니다.

## 로컬 실행

Python 3 표준 라이브러리만 사용한다. 저장소 루트에서 `python3 src/loop.py`를 실행하면 config/loop.json을 읽고 runs/RUN-*.json에 새 기록을 만든다. 이전 캠페인 실행을 읽으며 외부 게시·메일 발송은 수행하지 않는다. 현재 미연결 Adapter는 unconnected로 남고 신청 수는 null이다.

검증 명령: `python3 -m unittest discover -s tests -v`. 현재 11개 테스트는 합성 입력으로 승인 일치·누적 집계·이력·잠금을 검증하며 실제 전환 증거가 아니다.

Adapter driver는 unconnected 또는 manual_json이다. manual_json.path는 설정 파일 디렉터리 기준으로 해석한다. 실제 MCP 구현은 아직 없으며, 입력에는 정제된 조사/승인/게시 영수증/집계만 전달한다. 실행 중단 후 .loop.lock이 남으면 실행 중인 프로세스가 없는지 먼저 확인한다. 기록을 덮어쓰거나 잠금을 무조건 삭제하지 않는다.

계획 변경·실행 이력은 [활동 기록](docs/plan/activity-log.md), 개별 결과는 runs/에 보존한다. 실제 게시 전에는 최종본과 계정·채널에 대한 사용자 검토·승인이 필수다.

현재 첫 채널은 Threads다. 운영 목표는 최초 1회 수동 시작 후 매일 자동 반복이며 SchedulerAdapter·에이전트 런타임은 미연결이다. [발표 문서](docs/gtm/presentation.md)는 매 실행·주요 결정 후 갱신한다. 코드 실행만으로 자동 스케줄이 등록되지는 않는다.

Threads 계정은 사용자 제공 @mu.agent다. 인증정보는 사용자 요청에 따라 Git에서 제외되는 private/credentials/threads.json에 저장하며 파일 권한은 0600, 상위 credentials 디렉터리는 0700이다. 설정에는 경로와 공개 계정 참조만 둔다. 인증정보를 출력·커밋하지 않으며 실제 로그인·게시 Adapter는 아직 미연결이다.

## 외부 연결 없는 전체 루프 확인

`python3 scripts/mock_loop.py` 한 번으로 최초 시작과 가상 7일의 반복을 재현한다. 조사·승인·게시·신청 Adapter는 모두 Mock이며 운영 설정과 실제 인증정보를 사용하지 않는다. 결과는 runs/mock/DEMO-*/report.md와 summary.json, 단계별 inputs/·records/에 저장한다.

모의 신청 수는 실제 성과가 아니다. Mock 캠페인은 MOCK- 접두사와 mock_simulation 상태를 사용하고 운영 실행 폴더의 기록과 분리한다. 실제 자동 스케줄러 등록도 수행하지 않는다.

자기개선 판단 기준: [Rubric](docs/gtm/rubric.md). `python3 scripts/mock_refinement.py`로 근거 기반 평가 → 단일 수정 → 재평가를 검증한다. `python3 -m unittest discover -s tests -v`는 7일 루프 및 판단 코어를 함께 검증한다. 합성 점수·신청을 실제 전환 성과로 사용하지 않는다.

발표용 설명은 루트 [PRESENTATION.md](PRESENTATION.md)에 있다. 제품·목표·단계별 기준·Rubric·실제 성과에 따른 개선과 검증 범위를 순서대로 설명한다.

최신 주 루프는 [댓글·커뮤니티 반응 수집](docs/gtm/reaction-collection.md) → [전환 병목 Rubric](docs/gtm/rubric.md) → 변경 하나 → 재관측이다. `src/feedback.py`가 반응 근거로 다음 행동을 선택하고 콘텐츠 검토는 보조로 남긴다. 최신 Mock: [반응 기반 7일 실행](runs/mock/DEMO-20261024T081424-142339/report.md).

최신 설계는 [높은·낮은·새 가설 병렬 비교](docs/gtm/portfolio-loop.md)다. `python3 scripts/mock_portfolio.py`로 다계정 슬롯·Rubric·관측·가설 확장을 재현한다. 확률 모델은 사용하지 않는다. 설정은 `config/portfolio.json`, 역할별 Rubric은 `config/rubrics/`, 코어는 `src/portfolio.py`다. 실제 모델·다계정 게시 연결은 미구현이다.
