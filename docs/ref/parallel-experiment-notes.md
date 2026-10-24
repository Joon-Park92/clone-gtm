# 병렬 비교 설계 참고

최종 구현은 사용자 결정에 따라 균등 슬롯과 높은·낮은 비교를 사용한다. 확률 배분·Thompson Sampling은 구현에서 제거했다.

설계 시 참고한 원문:

- [Bubeck et al., Pure Exploration in Multi-Armed Bandits Problems](https://www.microsoft.com/en-us/research/publication/pure-exploration-multi-armed-bandits-problems/): 좋은 선택지를 찾는 것과 실행 중 누적 성과를 높이는 목표의 차이를 다룬다. 이 프로젝트에서는 둘을 하나의 문안 점수로 표현하지 않는다.
- [Wu & Wager, Thompson Sampling with Unrestricted Delays](https://arxiv.org/abs/2202.12431): 관측 지연을 명시적으로 다루는 연구다. 이 프로젝트는 그 알고리즘을 채택하지 않고, 관측 구간이 끝나기 전 결과를 0으로 처리하지 않는 단순 운영 규칙을 사용한다.

문헌의 이론적 보장을 이 프로젝트의 유기적 게시 실험·생성형 가설·소표본에 적용하지 않는다. 계정별 독자, 시간, 중복 노출, 자기보고 귀속의 한계가 남는다.
