# Pilot 문서 인계 영속 기록 구현 계획

> **For agentic workers:** 실행은 현재 격리된 worktree에서 순서대로 진행한다. `superpowers:executing-plans` 기준으로 각 작업을 검증한다.

**Goal:** Documents 접수와 Atlas 접수 사이 장애, 이벤트 중복과 ACK 유실에도 인계 기록을 잃지 않는 저장 기반을 만든다.

**Architecture:** 프로젝트별 SQLite journal에 고정 요청, 서로 분리된 두 outbox, 수신 이벤트 및 처리 결과를 저장한다. 네트워크 호출은 트랜잭션 밖에서 수행할 후속 어댑터 책임이며 이 단위는 실제 서비스나 연구 상태를 변경하지 않는다.

**Tech Stack:** Python 표준 sqlite3/json/hashlib, pytest.

**Spec:** `docs/integrations/documents-atlas/contract-v1.md`

## 제약

- `pilot-documents-atlas/1.0`; 기존 A1 journal과 연구 HEAD는 변경하지 않는다.
- 동일 operation/key의 요청 내용 변경을 거절하고 고정된 요청을 재사용한다.
- Documents 영수증 저장과 Atlas outbox 생성을 원자적으로 처리한다.
- 이벤트는 instance/consumer/import를 검증하며 처리 결과 저장 후에만 ACK 대상이 된다.
- 이번 단위는 저장 기반이다. HTTP/MCP 어댑터, 주기 조회기, UI, 실제 논문 연동은 완료로 표시하지 않는다.

## Task 1 — 두 단계 outbox

Files: `researchclaw/codex/document_handoff.py`, `tests/codex_native/test_document_handoff.py`.

- [x] 테스트 작성: `enqueue(operation,key,documents_request,atlas_request)` 재호출 및 변경 충돌, 재시작 후 요청 복원.
- [x] 테스트 실패 확인: `.venv/bin/python -m pytest tests/codex_native/test_document_handoff.py -q`.
- [x] 구현: `accept_documents(operation,key,receipt)`가 영수증과 Atlas 전송 입력을 함께 커밋한다. `pending()`은 현재 전송할 outbox만 반환한다.
- [x] Atlas 접수 영수증 저장 후 재시작해도 Documents 요청이 다시 pending으로 나오지 않는지 확인한다.

## Task 2 — 수신/처리/ACK 분리

- [x] 테스트 작성: `receive(event)` 중복, 역순, 다른 소비자 거절; `processed(event_id,result)` 이전에는 ACK 금지.
- [x] 구현: 이벤트 원형을 고정하고 `pending_events()`와 `pending_acks()`를 구분한다. `acknowledged(event_ids)`는 확인된 ACK만 기록한다.
- [x] 순서가 뒤바뀐 이벤트도 원형은 남기되 `latest(import_id)`는 sequence가 큰 이벤트를 유지하는지 검증한다.

## Task 3 — 검증 및 연결 경계 기록

- [x] 동시 동일 키 제출과 영수증 충돌 시 원자적 롤백을 테스트한다.
- [x] 신규 테스트와 기존 Atlas 관련 회귀 테스트를 실행한다.
- [x] 결과와 후속 HTTP/주기 조회/UI 연결 범위를 통합 README에 기록한다.
