# Mu GTM Loop

사용자 반응으로 가설을 만들고 **높은·낮은·새 가설을 같은 기회로 병렬 비교**하는 사전 신청 모집 루프다. 음식 예약으로 시작해 배송·장바구니·메일 등 모바일 앱 작업으로 확장한다.

## 빠르게 보기

- [발표 자료](PRESENTATION.md): 제품·목표·루프·현재 검증 범위
- [실행 계획](PLAN.md): 완료한 일과 남은 연결
- [병렬 비교 설계](docs/gtm/portfolio-loop.md): 역할·Rubric·계정·가설 계보
- [아키텍처](docs/architecture.md) · [용어](GLOSSARY.md)

## 실행과 검증

Python 3 표준 라이브러리만 사용한다. 저장소 루트에서 실행한다.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/mock_portfolio.py
```

테스트 44개 통과. Mock은 3가설·3합성 계정의 7일 관측, 높은·낮은 비교, 개선안·확장 가설 생성을 검증한다. [저장된 Mock 결과](runs/mock/PORTFOLIO-20261024T082539-545f71/report.md).

추가 검증: `python3 scripts/mock_loop.py`는 반응 기반 단일 루프, `python3 scripts/mock_refinement.py`는 보조 콘텐츠 검토를 재현한다. 결과는 runs/mock/의 새 디렉터리에 저장한다. 실제 계정·신청·모델 평가 성과가 아니다.

## 구성

| 경로 | 역할 |
| --- | --- |
| config/portfolio.json, config/rubrics/ | 계정·슬롯·관측 조건과 교체 가능한 역할별 Rubric |
| src/portfolio.py | 가설 등록·검토·병렬 슬롯·완료 관측 비교·다음 가설 요청 |
| src/feedback.py | 댓글·커뮤니티 반응 정제와 병목 판단 |
| src/loop.py | 개별 게시 승인·영수증·집계·실행 이력 |
| prompts/run-portfolio.md | 실제 에이전트 런타임이 따라야 할 역할 흐름 |
| docs/ref/, runs/ | 제품·조사 근거와 실제 로컬/합성 실행 증거 |

실제 모델·댓글 수집·다계정 게시·신청 접수·스케줄러는 미연결이다. 현재 실제 계정은 사용자 확인 @mu.agent 하나이고 실제 게시·성과 측정은 시작하지 않았다. 각 게시 최종본은 사용자 명시 승인 후 실행한다.

운영 계약: [반응 수집](docs/gtm/reaction-collection.md), [판단 기준](docs/gtm/rubric.md), [측정·귀속](docs/gtm/measurement.md), [게시 검토본](docs/gtm/publish-packet.md), [반복 운영](docs/plan/operation-loop.md).

개인정보·인증정보·원문 신청 자료는 Git에서 제외되는 private/에 둔다. Git에는 정제된 근거와 집계만 기록한다. 미측정은 0이 아니며 누적 신청을 일별로 더하지 않는다. 계획·변경·검증 이력은 [활동 기록](docs/plan/activity-log.md)과 Git에서 확인한다.
