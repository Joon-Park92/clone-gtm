# 아키텍처

반응 수집 → 가설 생성·독립 검토 → 콘텐츠·사용자 승인 → 높은·낮은·새 가설 병렬 계획 → 게시 영수증 → 같은 기간의 접수·반응 → 비교·다음 가설.

[병렬 비교 설계](gtm/portfolio-loop.md)가 현재 상위 계약이다. [용어](../GLOSSARY.md)는 가설·콘텐츠·계정별 배포·관측 구간을 구분한다.

| 모듈 | 입력과 책임 | 출력 |
| --- | --- | --- |
| feedback.py | 이전 게시물 댓글·커뮤니티 반응, 누락·중복·적합성 검사 | 근거 이력·전환 병목 후보 |
| portfolio.py | 역할별 Rubric, 가설·콘텐츠, 계정·배포·완료 접수 | 높은·낮은·새 슬롯, 비교, 새 가설 요청 |
| loop.py | 정제된 JSON 조사·승인·게시·측정·반응 | 개별 실행 기록·잠금·이전 실행 연결 |
| refinement.py | 콘텐츠 주장·명료성의 근거 있는 평가 | 게시 전 보조 검토 |

## 교체할 연결부

AgentAdapter는 task·rubric·evidence를 받아 결과를 반환한다. 역할별 기준은 config/rubrics/, 역할과 계정 설정은 config/portfolio.json에서 선택한다. 평가에는 대상·Rubric 해시와 증거·이유를 남긴다. 생성자와 최종 가설 검토자는 분리한다.

Research/Feedback/Measurement/Approval/Publish/Scheduler Adapter는 원문 조사, 반응, 실제 접수, 사람 승인, 게시 영수증, 반복 실행을 연결한다. 현재 unconnected/manual_json과 Mock만 구현했다. 실제 모델·외부 API·배치 실행·영속 스케줄러는 미연결이다.

## 불변 조건

- campaign → arm → asset → deployment → 실제 접수의 연결을 보존한다. 모호한 귀속은 실험군 성과로 쓰지 않는다.
- 정확한 내용·계정·범위의 사람 승인 후에만 게시한다. uncertain은 조회부터 하며 재게시하지 않는다.
- 미측정·관측 대기를 0으로 처리하지 않는다. 동일 신청의 여러 배포 귀속을 막고 누적 스냅샷을 더하지 않는다.
- 원문 개인정보·인증정보는 private 영역, 공개 이력은 정제된 근거와 집계다.
- 새 가설은 부모 성과를 물려받지 않는다. 낮은 가설도 자동 삭제하지 않는다.
- 기존 실행 기록은 보존한다. 실배치 동시성·재시도·등록 영수증 처리는 런타임 연결 시 구현해야 한다.

설계 결정은 [파일 기반 기록](adr/0001-file-based-loop.md)과 [실험군·배포 귀속](adr/0002-arm-attribution-and-evolving-portfolio.md)에 남겼다.
