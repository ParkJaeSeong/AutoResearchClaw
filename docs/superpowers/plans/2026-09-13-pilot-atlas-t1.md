# Pilot Atlas T1 구현 계획

> 실행: executing-plans와 test-driven-development를 적용해 현재 격리 worktree에서 순차 구현한다. 사용자가 Atlas와 협의하여 기능 구현을 지시했다.

**Goal:** 기존 연구 UI에서 Atlas 프로젝트 연결, 질문 전송·재조회, 원형 수신·등록, 후속 질문을 수행한다.
**Architecture:** 신뢰된 연결 파일을 읽는 HTTP 클라이언트, 연구별 연결/요청 journal, 기존 graph import, UI 제어를 분리한다. journal은 통신 상태이며 연구 판단은 기존 commands만 변경한다.
**Tech Stack:** Python stdlib urllib/SQLite, 기존 연구 graph, JavaScript DOM, pytest.
**Spec:** ../../integrations/researchatlas/contracts.md 및 Atlas 확정 v1 계약.

## Global Constraints

토큰은 서버 메모리에서만 사용한다. loopback HTTP만, 프록시·redirect 사용 금지. QA 10,485,760 decoded bytes 검증. 매 작업 instance를 확인한다. 연결 변경은 이전 요청에 소급하지 않는다. 전송 전 키/내용 저장, 동일 키 충돌 거절, polling은 재실행하지 않는다. 원형 수신 실패는 연구 상태를 바꾸지 않는다. 네트워크 I/O 중 graph lock을 점유하지 않는다. UI는 기존 Atlas 패널과 스타일을 재사용한다. T1 성공은 M1 완료가 아니다.

## Task 1: HTTP 연결·원형

Files: researchclaw/codex/atlas_client.py, tests/codex_native/research_graph/test_atlas_service.py.
Interfaces: AtlasClient(connection_file).request(method,path,payload=None,params=None); identity(expected=None); raw(envelope,expected).
- [x] 권한/loopback/instance/원형 오류 및 실제 합성 HTTP 서버 테스트를 작성하고 실패 확인.
- [x] urllib 클라이언트와 크기 제한·safe 오류를 구현.
- [x] pytest 대상 테스트 통과 확인.

## Task 2: 바인딩·요청·수신 journal

Files: researchclaw/codex/atlas_session.py, 위 테스트.
Interfaces: AtlasSession(root,client).status(), bind(project,reason), ask(key,question,question_id,previous=None), poll(key), receive(key,expected_head).
- [x] 재시작·응답 유실·키 충돌·바인딩 변경·원형 오류·수신 등록 재시도 테스트 작성/실패 확인.
- [x] SQLite transaction으로 전송 전 기록; 외부 응답과 raw는 복구 가능한 journal에 보존. 기존 import_qa 호출.
- [x] 같은 질문 재전송에서 새 job/새 근거가 생기지 않는지 검증.

## Task 3: UI와 실행 진입점

Files: atlas_http.py, research_viewer.py, research_ui/atlas_service.js, research_ui/atlas.js, atlas_session.py CLI.
- [x] origin 검증과 요청 schema, UI 진행/답변/재조회 동작 테스트 작성/실패 확인.
- [x] 서버 환경 PILOT_ATLAS_CONNECTION_FILE로 연결 경로 지정. UI는 토큰·경로를 받지 않는다.
- [x] 기존 파일 import·판단 UI를 유지하며 연결/질문/상태/수신 버튼 추가.

## Task 4: 실제 왕복·회신

- [x] 관련 Python/JS 회귀와 diff 검사.
- [x] 실제 Atlas 기존 프로젝트에 T1 질문 전송. 첫 시험 Pilot root는 분리된 통합 시험 연구로 표시해 기존 연구를 오염시키지 않는다.
- [x] raw/page/source 확인, 실제 import·사용 판단·후속 질문, 재시작 후 상태 확인.
- [x] Atlas 담당에게 결과·제약을 회신하고 docs/integrations/researchatlas에 사용법/실제 검증 기록 작성.

검증 기록: [실제 T1·사용법](../../integrations/researchatlas/pilot-t1-implementation.md). 기존 작업의 미커밋 변경을 보존하며 이번 변경도 현재 worktree에 유지했다.
