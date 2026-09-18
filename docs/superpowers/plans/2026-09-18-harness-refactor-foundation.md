# 하네스 리팩토링 기반 정리

사용자 승인: 2026-09-18 그래프·루프·하네스·시작/종료 훅·중간 UI 기록 합의 후 관련 없는 코드/UI 아카이브 및 리팩토링 요청.

목표: 혼재된 이전 화면과 일회성 연구 실행기를 활성 경로에서 분리한다. 이번 정리는 새 하네스 구현 완료가 아니다.

- [x] 기존 research_ui와 일회성 사례 실행 스크립트를 해시 목록과 함께 아카이브. 원장·공유 API·연구 원형·개발 중 변경 보존.
- [x] 기존 9단계 상세 렌더링을 legacy_records.js로 추출. 실제 native revisions가 없으면 표시하지 않음. 기존 revisions가 있으면 이전 기록 펼침에서 접근. 에피소드만으로 native 단계/완료를 합성하지 않음.
- [x] 하드코딩된 실행 중/확인 시각 자리표시자 제거. 실제 실행 데이터가 없는 상태에서 라이브 상태를 추정하지 않음.
- [x] 빈 레거시 지도 미표시 및 이전 기록 접근 회귀 검사. JS 전체 관련 검사·HTTP 모듈 제공·브라우저 확인.

유지: research_graph store/commands, Atlas·Documents adapter/session/journal, ServiceInbox, source/raw 검증, 프로젝트 카탈로그, 공통 스타일·접근성·테마. 이들은 하네스 기반으로 재사용한다.
호환 격리: 기존 native graph 저장 계약·detail/timeline은 기존 기록에서 사용 중이므로 삭제/이동하지 않는다. 새 하네스에서 무관한 API 제거는 참조 대조 후 별도 수행한다.
후속 개발: event→projection 단일 기록, 훅 판정/재작업, 도구 완료→배정→반환, 발언별 기록, 무인 복구 시나리오. 현재 완료 상태와 혼동하지 않는다.

검증: UI Node tests 71, Python project/viewer 11 통과. 8771 운영 재기동 PID83074. CF/PP 빈 legacy 지도 미표시 브라우저 확인. 이전 상세 렌더링은 회귀 테스트로 확인; 기존 POC 브라우저 접근은 별도 확인 필요. 아카이브 manifest는 archive/legacy/2026-09-18-harness-reset/manifest.json. 새 하네스는 미구현이며 단계 완료를 합성하지 않았다.
