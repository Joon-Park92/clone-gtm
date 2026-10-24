# 이전 게시글 댓글과 커뮤니티 반응 수집 계약

## 매 실행의 수집 순서

1. 같은 campaign_id의 모든 runs에서 posted 영수증을 읽어 URL·asset_id·게시 시각 목록을 만든다. 최신 초안 하나만 읽지 않는다. uncertain 게시의 댓글을 추정하지 않는다.
2. 각 게시 URL의 댓글과 답글을 원문 맥락과 함께 읽는다. 페이지가 나뉘면 이어서 읽고, 호출 한도·로그인·삭제·접근 제한으로 중단되면 partial/unavailable과 누락 이유를 기록한다.
3. config.feedback_collection.community_targets의 관련 커뮤니티 글과 댓글을 읽는다. 초기 URL이 없으면 discovery_queries로 공개 원문을 찾고 적합성·접근 규칙을 확인한 뒤 관측 대상으로 등록한다. 검색 스니펫만으로 직접 경험을 확정하지 않는다.
4. 긍정·부정·무관심·질문을 모두 가져온 뒤, 팀·스팸·중복을 구분한다. 이전 event_id는 다시 세지 않는다. 익명 작성자 키는 private 영역에서 안정적으로 만들어 같은 사람의 반복을 구분한다.
5. 원문과 개인 식별 정보는 private/feedback/에 두고, Git에는 최소 정제 요약·원문 참조·집계·판단 이유만 남긴다. 연락처·로그인·수신 메일·프로필 복사는 제외한다.
6. 실제 신청 집계와 함께 다음 실험을 결정한다. 읽기 권한은 답글·DM·게시 권한을 의미하지 않는다.

## Adapter 출력

- status: unconnected / pending / collected
- campaign_id, observed_at
- coverage[]: target_url, kind(own_post/community), status(complete/partial/unavailable), checked_at, reason
- events[]: event_id(EV- 접두어), source_url, target_url, source_kind, created_at, evidence_summary, classification_reason, category, audience_fit, actor_type, author_key

category: signup_friction / misunderstanding / trust / no_need / need / interest / other.

audience_fit: yes / no / unknown. actor_type: external / team / spam / unknown. author_key: ANON- 접두어의 비식별 키 또는 null. 원문 URL은 출처 확인용이다. 공개 원문에 개인정보가 있으면 요약에 복사하지 않는다.

같은 event_id의 관측·분류를 조용히 덮어쓸 수 없다. 코어는 변경된 입력을 거부하므로 수정·삭제·재분류가 필요하면 이전 증거와 연결된 정정 검토를 먼저 남겨야 한다. 자동 정정 API는 아직 없다.

complete는 checked_at까지 해당 대상의 접근 가능한 댓글·답글을 빠짐없이 읽었다는 Adapter 진술이다. 플랫폼의 모든 사용자나 비공개 반응까지 관측했다는 뜻이 아니다. 설정한 커뮤니티 대상이나 과거 게시 URL이 누락되면 collection_complete=false다. 실제 조회 커서·페이지 수·범위 근거는 private 수집 로그에 보존하며 코어는 API 완전성을 직접 검증하지 못한다.

## 현재 연결 상태

FeedbackAdapter는 unconnected다. 실행 코어가 게시 목록과 커뮤니티 대상을 전달하도록 연결했으며 manual_json 입력이 가능하다. 실제 Threads 댓글 API·브라우저 수집은 구현하지 않았다. 현재 저장된 실제 posted URL이 없어 캠페인 댓글을 수집했다고 주장하지 않는다. 관련 커뮤니티의 기존 조사 원문은 있어도 신규 사용자 반응 수집 완료로 바꾸지 않는다.

재현 가능한 예제는 `scripts/mock_loop.py` 및 최신 `runs/mock/DEMO-20261024T081424-142339/inputs/*/feedback.json`이다. Mock은 `.invalid` 출처, 합성 작성자·반응만 사용한다.
