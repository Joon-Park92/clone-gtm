# Mock GTM 루프 검증 결과

결과: PASS. 모든 고객·승인·게시·신청·시간은 합성 또는 가상 데이터다. 실제 Threads·메일·인증정보·스케줄러를 호출하지 않았다.

| 가상 일차 | 호출 | 상태 | 모의 누적 신청 | 다음 판단 |
| --- | --- | --- | --- | --- |
| 0 | manual_bootstrap_mock | awaiting_approval | None | collect_reactions |
| 1 | automatic_tick_mock | measured | 0 | message |
| 2 | automatic_tick_mock | awaiting_approval | 2 | observe |
| 3 | automatic_tick_mock | measured | 3 | conversion |
| 4 | automatic_tick_mock | publication_uncertain | 3 | observe |
| 5 | automatic_tick_mock | measured | 3 | observe |
| 6 | automatic_tick_mock | measured | 3 | observe |
| 7 | automatic_tick_mock | measured | 3 | observe |

처음 1회 수동 시작을 모의한 뒤 가상 시계를 24시간씩 전진해 7번 반복했다. 실제 시간을 기다리거나 스케줄러를 등록한 것은 아니다. 7일 종료 뒤 추가 실행은 없다.

확인: 게시글별 댓글·답글과 커뮤니티 반대 의견 5건의 합성 수집, 중복 재수집 시 재수정 방지, 오해 반응→설명 변경·신청 마찰→신청 안내 변경, 승인 전 게시 대기 및 새 승인, 승인 대기 중 측정 지속, 모의 기존/중복/테스트/스팸 각 1건 제외, 출처 불명 1건 별도 처리, 캠페인 누적 최종 3건 유지, 불확실 게시의 재전송 없이 영수증 확인, 이전 기록 보존. 승인 없음·승인 후 문안 변경·계정 불일치·기존 기준 미확인은 모두 코어에서 거부했다.

모의 게시 호출은 총 3회이며 가상 날짜가 지나도 같은 콘텐츠를 다시 보내지 않았다. Mock Publisher의 idempotency와 합성 신청 집계 로직은 테스트 더블이며 실서비스 Adapter 구현/보장을 뜻하지 않는다. 실제 승인 기록이나 실제 트랙션으로 사용하지 않는다.

운영 설정은 변경하지 않았고 실제 계정 비밀번호를 읽지 않았다. 입력과 각 실행 JSON은 이 폴더의 inputs/와 records/에서 재검토할 수 있다.
