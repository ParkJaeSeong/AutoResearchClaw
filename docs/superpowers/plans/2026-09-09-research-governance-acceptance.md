# 전 과정 UI·평가·수용 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전 과정 UI·평가·수용를 독립 검토 가능한 작은 작업으로 구현한다.

**Architecture:** 공통 append-only 기록 위에 마일스톤별 adapter를 연결한다. 기존 엔진의 경로·승인을 유지하고 신규 프로젝트에서만 확장 정책을 적용한다.

**Tech Stack:** Python >=3.11, pytest, node:test, vanilla JS, 기존 wheel 패키징.

**Spec:** [공통 설계](../specs/2026-09-09-research-governance-design.md). [총괄 작업판](2026-09-09-research-governance.md).

## Global Constraints

- Python >=3.11, 기존 pytest·node:test·vanilla JS 사용. 새 프레임워크/외부 서비스 추가 없음.
- 신규 workflow_version=research-graph-v1, schema_version=1. 기존 M1·숫자 단계 root·승인·기록 불변.
- 신규 root의 .researchclaw/research_graph에 단일 authoritative HEAD. atomic write, expected_head, command_id replay 필수.
- 조정자 대필·자기 승인 금지. transferred≠resolved. 부정 결과·불확실·실패·예산 중단 구분.
- 기존 실행/비용/사용자 승인 유지. 외부 게시·실험 자동 실행·실사용 설치는 이 계획으로 승인하지 않음.
- 모든 입력·판단은 정확한 버전 참조. confidence 합의 임계값 없음. 실제 관측과 synthetic fixture 분리.

## 파일·인터페이스 규칙

아래 Create 경로는 계획상 신규 파일이다. 기존 구현으로 오해하지 않는다. 일반 core 함수는 순수 검증/전이 계획을 반환하고 파일·호스트·네트워크를 직접 변경하지 않는다. 반환 구조는 `{state_patch: dict, event: dict, object_inputs: dict[str, bytes]}`; 조회/검증 함수의 별도 반환은 아래 명시한다. 저장은 A02와 공통 CLI registry만 수행한다.

A01에서 `validate_record`는 `{code,path,message}` 오류 tuple을 반환한다. gate/예산/audit는 `{ready,reason_codes,required_actions}`, 일반 plan 함수는 위 전이 구조를 반환한다. commands.py의 `apply_command(root: Path, *, operation: str, payload: dict, expected_head: str, command_id: str) -> dict`가 등록된 handler를 호출하고 원본 snapshot binding을 재검사한 후 A02로 원자적 저장한다. A02가 registry와 CLI research init 기반을 만들고 각 기능 작업이 자신의 operation을 등록한다. 초기 지원하지 않는 operation은 unknown_operation으로 거부한다.

각 테스트 파일은 아래 수용 사례를 실제 public 함수/CLI 호출과 fixture로 구현한다. 예시 case 표는 실행할 테스트의 입력 상황과 oracle이며 이미 구현된 test helper가 아니다. fixtures는 해당 작업이 필요한 최소 유효 객체를 테스트 파일에 만들고 레코드 계약을 통과시킨다. 누락 필드 때문에 엉뚱한 검증에서 실패하는 검사를 금지한다.

각 작업은 아래5개 체크를 순서대로 수행한다. 하나의 체크가 커지면 테스트 사례 단위로 나누되 해당 작업의 완료·검토를 먼저 끝낸다. 선행 ID가 모두 완료되기 전 dependent 구현을 시작하지 않는다. 공유 파일 mutation은 직렬화한다.

## Task E01: 전 과정 읽기 전용 조회·CLI 서버

**선행:** B07,C06,D05. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/views.py`
- Create: `researchclaw/codex/research_viewer.py`
- Modify: researchclaw/codex/research_cli.py.
- Test: `tests/codex_native/research_graph/test_views.py`.

**Interfaces:** `build_view(root: Path, *, head_id: str | None = None) -> dict`

**산출물·구현 범위:** 마일스톤·쟁점·검증·결정·의존·인계·실제 이동을 단일 snapshot에서 투영한다. research_cli/research_viewer로 inspect/view 제공, 기존 m1 경로는 유지.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: orphan HEAD·비공개 최초 의견·가짜 projection raw링크 → 거부; GET 파일 불변
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_views.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 마일스톤·쟁점·검증·결정·의존·인계·실제 이동을 단일 snapshot에서 투영한다. research_cli/research_viewer로 inspect/view 제공, 기존 m1 경로는 유지.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_views.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): E01 전 과정 읽기 전용 조회·CLI 서버` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 명령으로 현재·과거 연구 전체 기록을 조회한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task E02: 마일스톤 지도와 공통 쟁점 타임라인

**선행:** E01. **상태:** 미착수.

**Files:**
- Create: `researchclaw/codex/research_ui/index.html`
- Create: `researchclaw/codex/research_ui/app.js`
- Create: `researchclaw/codex/research_ui/graph.js`
- Create: `researchclaw/codex/research_ui/timeline.js`
- Create: `researchclaw/codex/research_ui/styles.css`
- Modify: researchclaw/codex/research_viewer.py (정적 allowlist), researchclaw/codex/research_ui/app.js (E03 연결).
- Test: `tests/ui/research_graph/timeline.test.mjs`.

**Interfaces:** `renderResearchGraph(root, view, selection); traceIssue(view, issueId)`

**산출물·구현 범위:** research_ui에 milestone/issue 선택, 이관·검증·해소·재개 표시. 허용 경로와 실제 event의 이동을 구분한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 이관을 해소 색상으로 표시하면 실패; HEAD 갱신 중 선택한 과거 쟁점 유지; unknown 상태를 완료로 표시 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `node --test tests/ui/research_graph/timeline.test.mjs`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: research_ui에 milestone/issue 선택, 이관·검증·해소·재개 표시. 허용 경로와 실제 event의 이동을 구분한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `node --test tests/ui/research_graph/timeline.test.mjs`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): E02 마일스톤 지도와 공통 쟁점 타임라인` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 하나의 쟁점을 M1→M2→M3까지 따라간다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task E03: 결정·입장 변화·주장과 원천 탐색

**선행:** E02. **상태:** 미착수.

**Files:**
- Create: `researchclaw/codex/research_ui/detail.js`
- Create: `researchclaw/codex/research_ui/trace.js`
- Modify: researchclaw/codex/research_viewer.py (정적 allowlist), researchclaw/codex/research_ui/app.js (E03 연결).
- Test: `tests/ui/research_graph/trace.test.mjs`.

**Interfaces:** `traceClaim(view, claimId); renderVerification(root, view, verificationId)`

**산출물·구현 범위:** M3 주장→분석→실행→M1 가설과 출처, 공통 원천, 실제 확인 결과, 요약 확인·이견을 연결한다. 기존 단일 후보 가정 반복 금지.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 다른 가설 revision을 비교하면 실패; 누락 참조를 최신 버전으로 대체 금지; script 문자열 inert
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `node --test tests/ui/research_graph/trace.test.mjs`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: M3 주장→분석→실행→M1 가설과 출처, 공통 원천, 실제 확인 결과, 요약 확인·이견을 연결한다. 기존 단일 후보 가정 반복 금지.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `node --test tests/ui/research_graph/trace.test.mjs`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): E03 결정·입장 변화·주장과 원천 탐색` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 왜 이 결론인지와 독립 근거가 얼마나 있는지 원문으로 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task E04: 신규 프로젝트 전체 연구 경로

**선행:** E03. **상태:** 미착수.

**Files:**
- Create: `tests/codex_native/research_graph/test_e2e.py`
- Create: `docs/superpowers/plans/2026-09-09-research-governance-verification.md`
- Modify: 실패를 재현한 구현 파일만.
- Test: `tests/codex_native/research_graph/test_e2e.py`.

**Interfaces:** `공개 research CLI로 S01–S05/S07/S09 시나리오 실행`

**산출물·구현 범위:** 신규 init부터 M1 전체 판단·원문 확인·승인·인계, M2 부정/불확실 결과, M3 심사 복귀를 public API로 검증한다. seed checkpoint 우회 금지.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: r1 쟁점 누락·M1 필수 협의 생략·부정 결과 인계 차단 → 실패; 정상 부정 결과 경로는 M3 가능
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_e2e.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 신규 init부터 M1 전체 판단·원문 확인·승인·인계, M2 부정/불확실 결과, M3 심사 복귀를 public API로 검증한다. seed checkpoint 우회 금지.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_e2e.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): E04 신규 프로젝트 전체 연구 경로` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 성공·부정 결과·역방향 복귀가 원문 기록으로 이어지는지 본다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task E05: 동시성·중단 복구·기존 프로젝트 보존

**선행:** E04. **상태:** 미착수.

**Files:**
- Create: `tests/codex_native/research_graph/test_recovery.py`
- Create: `tests/codex_native/research_graph/test_compatibility.py`
- Modify: 실패를 재현한 구현 파일만.
- Test: `tests/codex_native/research_graph/test_recovery.py`.

**Interfaces:** `공개 CLI의 S06/S08/S10/S11 실패 matrix와 파일 snapshot 비교`

**산출물·구현 범위:** HEAD 공개 전후 종료, 동일/충돌 command 재시도, 동시 mutation, symlink/path escape, 승인 반려·예산 소진을 검사한다. legacy/M1 bytes와 명령 회귀를 확인한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 중단/경합 이후 하나의 HEAD; 동시 실패 mutation은 무변경; unknown source instruction을 실행하면 실패
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_recovery.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: HEAD 공개 전후 종료, 동일/충돌 command 재시도, 동시 mutation, symlink/path escape, 승인 반려·예산 소진을 검사한다. legacy/M1 bytes와 명령 회귀를 확인한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_recovery.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): E05 동시성·중단 복구·기존 프로젝트 보존` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 실패한 작업과 재개 지점, 기존 프로젝트가 그대로인지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task E06: 실제 역할·브라우저 수용

**선행:** E05. **상태:** 미착수.

**Files:**
- Create: `docs/superpowers/plans/2026-09-09-research-governance-browser-verification.md`
- Create: `tests/ui/research_graph/accessibility.test.mjs`
- Modify: researchclaw/codex/research_ui/ (실제 재현된 결함만).
- Test: `tests/ui/research_graph/accessibility.test.mjs`.

**Interfaces:** `실제 호스트 패킷/제출 관측과 허용된 브라우저 UI 조작`

**산출물·구현 범위:** 사람이 승인한 주제·자료 범위에서 역할별 실제 제출을 확인한다. 360/736px·light/dark·키보드·긴/script 발언·polling 선택 유지·단절 복구·쟁점 재개 경로를 검사한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: Chrome 접근 차단이면 visual_pending; 합성 입력은 synthetic 표시; 최초 의견 접근 통제 불가이면 instructions_only
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `node --test tests/ui/research_graph/accessibility.test.mjs`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 사람이 승인한 주제·자료 범위에서 역할별 실제 제출을 확인한다. 360/736px·light/dark·키보드·긴/script 발언·polling 선택 유지·단절 복구·쟁점 재개 경로를 검사한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `node --test tests/ui/research_graph/accessibility.test.mjs`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): E06 실제 역할·브라우저 수용` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 대화 원문과 화면의 결정·쟁점·이동이 일치하는지 직접 확인한다.
**완료 조건:** 실제 호스트 제출과 브라우저 화면을 관측하고, 확인물·거부/정상 사례가 검토를 통과함. 자동 DOM 검사만으로 완료하지 않는다. 접근 차단 시 이 작업은 미완료로 남기며 원인과 사용자 확인 결과를 기록한다. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.


수용 순서: (1) 승인된 주제·허용 자료 snapshot 고정 (2) 실제 역할에 독립 패킷 전달 (3) 첫 제출 전후 비공개 확인 (4) 전체 공개 뒤 UI와 원문 대조 (5) 반환/이관/재개 경로 탐색 (6) 서버 중단·복구 및 선택/스크롤 확인 (7) 두 viewport와 두 theme에서 실제 화면 확인. 실험 수용에는 별도 실행 승인이 필요하며 승인 부재를 mock 실행으로 대신하지 않는다.

## Task E07: 단일·다중 에이전트 품질 평가

**선행:** E04. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/evaluation.py`
- Create: `tests/fixtures/research_graph/evaluation_cases.json`
- Modify: docs/superpowers/plans/2026-09-09-research-governance-verification.md.
- Test: `tests/codex_native/research_graph/test_evaluation.py`.

**Interfaces:** `score_cases(records: list[dict], rubric: dict) -> dict`

**산출물·구현 범위:** 동일 snapshot·같은 도구/예산 조건의 단일/다중 검토와 라벨된 오류 사례 비교. 사전 rubric·누락 비용·blind 판정·관측 시간/비용 저장.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 다중 성능 악화 사례도 그대로 보고; 합의율을 정확도로 계산 금지; 모르는 비용은 null
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_evaluation.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 동일 snapshot·같은 도구/예산 조건의 단일/다중 검토와 라벨된 오류 사례 비교. 사전 rubric·누락 비용·blind 판정·관측 시간/비용 저장.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_evaluation.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): E07 단일·다중 에이전트 품질 평가` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 오류 발견·잘못된 해소·불필요한 반복·비용에 실제 이점이 있었는지 본다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task E08: 설치본·사용 안내·최종 작업판

**선행:** E03,E05. **상태:** 미착수.

**Files:**
- Create: `docs/RESEARCH_GRAPH_USER_GUIDE_KO.md`
- Modify: pyproject.toml, README.md, skills/researchclaw/SKILL.md, tests/codex_native/test_plugin_package.py.
- Test: `tests/codex_native/research_graph/test_installed_package.py`.

**Interfaces:** `설치된 researchclaw-codex research init/import-m1/inspect/view와 기존 m1 --help`

**산출물·구현 범위:** wheel assets·참고 문서 포함, checkout 밖 격리 venv 확인, 사용자 승인/실행 경계와 지원 범위 문서화. 패키지 완성은 외부 배포 아님.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: PYTHONPATH 없이 설치 경로 확인; 누락 live.js/assets → 실패; 실사용 환경 덮어쓰기 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_installed_package.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: wheel assets·참고 문서 포함, checkout 밖 격리 venv 확인, 사용자 승인/실행 경계와 지원 범위 문서화. 패키지 완성은 외부 배포 아님.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_installed_package.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): E08 설치본·사용 안내·최종 작업판` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 설치본에서도 연구 결정과 원문을 확인하고 미완료 검증 목록을 본다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.
