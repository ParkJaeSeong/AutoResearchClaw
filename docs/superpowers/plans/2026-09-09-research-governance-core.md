# 공통 연구 운영 기반 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공통 연구 운영 기반를 독립 검토 가능한 작은 작업으로 구현한다.

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

## Task A01: 공통 기록·참조 계약

**선행:** 없음. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/contracts.py`
- Create: `researchclaw/core/research_graph/__init__.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_contracts.py`.

**Interfaces:** `validate_record(kind: str, payload: dict) -> tuple[dict, ...]`

**산출물·구현 범위:** Issue/IssueEvent/Verification/Result/Position/Decision/Handoff/Dependency 닫힌 필드와 enum, 버전·참조 계약을 고정한다. 객체별 필수·선택 필드를 spec 표에서 명시적으로 분리한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: IssueEvent transferred에서 수신 수락 참조 누락 → transfer_acceptance_missing; confidence=90만으로 ready를 표시하는 필드는 거부
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_contracts.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: Issue/IssueEvent/Verification/Result/Position/Decision/Handoff/Dependency 닫힌 필드와 enum, 버전·참조 계약을 고정한다. 객체별 필수·선택 필드를 spec 표에서 명시적으로 분리한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_contracts.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A01 공통 기록·참조 계약` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 어떤 기록으로 쟁점·검증·결정을 연결할지 JSON 예제를 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task A02: 저장 공통부와 신규 버전 격리

**선행:** A01. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/store.py`
- Create: `researchclaw/core/immutable_records.py`
- Create: `researchclaw/core/research_graph/commands.py`
- Create: `researchclaw/codex/research_cli.py`
- Modify: researchclaw/core/m1/store.py, researchclaw/codex/cli.py.
- Test: `tests/codex_native/research_graph/test_store.py`.

**Interfaces:** `read_head(root: Path) -> dict; commit_record(root: Path, *, expected_head: str, command_id: str, state: dict, event: dict, objects: dict[str, bytes]) -> dict`

**산출물·구현 범위:** m1/store.py의 바이트·atomic 저장 공통부만 core/immutable_records.py로 추출한다. 기존 m1 경로/버전 래퍼 유지; 새 root의 research_graph 저장소와 단일 HEAD를 추가한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 동일 command_id의 다른 payload·stale HEAD·공개 전 종료 → 충돌/이전 HEAD; M1 root에 신규 버전 쓰기 거부
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_store.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: m1/store.py의 바이트·atomic 저장 공통부만 core/immutable_records.py로 추출한다. 기존 m1 경로/버전 래퍼 유지; 새 root의 research_graph 저장소와 단일 HEAD를 추가한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_store.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A02 저장 공통부와 신규 버전 격리` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 기존 M1 기록이 그대로 열리고 신규 기록은 다른 root에서만 생성된다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task A03: M1 기록의 명시적 가져오기

**선행:** A02. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/migration.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_migration.py`.

**Interfaces:** `import_m1(source: Path, target: Path, *, source_head: str, command_id: str) -> dict`

**산출물·구현 범위:** reachable 이력과 객체를 검증 복사하고 source ID→global ID 대응표 및 provenance 한계를 기록한다. 활성 과거 council은 재해석하지 않고 읽기 전용 이력으로 보존한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: r1 열린6개+r2 새0개 → 6개 유지; 복사 중 오류 → 완료 HEAD 없음; 원본 bytes/mtime 불변
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_migration.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: reachable 이력과 객체를 검증 복사하고 source ID→global ID 대응표 및 provenance 한계를 기록한다. 활성 과거 council은 재해석하지 않고 읽기 전용 이력으로 보존한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_migration.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A03 M1 기록의 명시적 가져오기` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 현재 실제 검토 사례를 새 프로젝트에서 동일하게 조회한다. 기존 심사/승인 완료를 새 정책 통과로 간주하지 않는다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task A04: 쟁점 전이·이관·재개

**선행:** A03. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/issues.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_issues.py`.

**Interfaces:** `propose_issue_event(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** global issue와 상태 전이를 추가한다. independent resolver·수신 수락·대체 쟁점 연결을 검증하고 새 event만 생성한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: transferred→resolved를 검증 없이 요청 → resolution_evidence_missing; resolved에 새 충돌 → reopened 가능
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_issues.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: global issue와 상태 전이를 추가한다. independent resolver·수신 수락·대체 쟁점 연결을 검증하고 새 event만 생성한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_issues.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A04 쟁점 전이·이관·재개` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 한 쟁점이 M1→M2로 옮겨도 열린 문제로 남는 것을 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task A05: 검증 작업과 결과 등록

**선행:** A04. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/verification.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_verification.py`.

**Interfaces:** `prepare_verification(snapshot: dict, payload: dict) -> dict; register_verification_result(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** method를 source_check/logic_check/calculation/experiment/human_decision으로 구분한다. 입력·판정 조건 고정; 결과 supported/refuted/inconclusive/failed와 확인 범위 저장.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 실행 로그만 있고 판정 기준 없음 → acceptance_rule_missing; failed/inconclusive → 자동 issue resolved 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_verification.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: method를 source_check/logic_check/calculation/experiment/human_decision으로 구분한다. 입력·판정 조건 고정; 결과 supported/refuted/inconclusive/failed와 확인 범위 저장.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_verification.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A05 검증 작업과 결과 등록` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 토론에서 실제로 수행한 확인과 아직 안 한 확인을 구분한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task A06: 입장 변화·요약 근거 연결

**선행:** A05. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/positions.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_positions.py`.

**Interfaces:** `validate_position_change(snapshot: dict, payload: dict) -> tuple[dict, ...]; validate_rationale_links(snapshot: dict, decision: dict) -> tuple[dict, ...]`

**산출물·구현 범위:** 기존 입장 ID와 evidence_added/reinterpretation/logic_correction/scope_changed 사유 연결. 결정 문장에 실제 발언·검증 참조 및 해당 역할의 요약 확인을 요구한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 검토자의 조건부 찬성을 무조건 찬성으로 요약하고 확인 없음 → position_ack_missing; 없는 근거 ID → ref_unknown
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_positions.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 기존 입장 ID와 evidence_added/reinterpretation/logic_correction/scope_changed 사유 연결. 결정 문장에 실제 발언·검증 참조 및 해당 역할의 요약 확인을 요구한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_positions.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A06 입장 변화·요약 근거 연결` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 누가 어떤 이유로 판단을 바꿨는지 원문까지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task A07: 마일스톤별 차단·인계 판정

**선행:** A06. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/gates.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_gates.py`.

**Interfaces:** `assess_gate(snapshot: dict, *, milestone: str, gate_id: str) -> dict`

**산출물·구현 범위:** ready/reason_codes/required_actions/unresolved_issue_ids 반환. 필수 제출·출처·현재 승인·blocking_scope를 검증하고 optional 개선은 남긴다. revise의 기준 연결 누락은 보정 대기다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: M1 empirical 질문만 미해결이고 M2 수락 있음 → 인계 가능; M2 실행 무결성 차단 미해소 → 인계 불가
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_gates.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: ready/reason_codes/required_actions/unresolved_issue_ids 반환. 필수 제출·출처·현재 승인·blocking_scope를 검증하고 optional 개선은 남긴다. revise의 기준 연결 누락은 보정 대기다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_gates.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A07 마일스톤별 차단·인계 판정` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 단순 반대와 실제 진행 차단, M2에서 확인할 질문을 구분한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task A08: 의존 관계와 변경 영향

**선행:** A07. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/dependencies.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_dependencies.py`.

**Interfaces:** `plan_revalidation(snapshot: dict, *, changed_refs: list[str]) -> dict`

**산출물·구현 범위:** versioned supports/derived_from/tests/reports DAG로 affected_refs/approval_checks/reusable_refs를 계산한다. 과거 객체 보존, 재검토 대상만 새 event.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 분석 하나 수정 → 연결 도표·주장만 영향; 관련 없는 문헌 승인 재사용; 순환·unknown ref 거부
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_dependencies.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: versioned supports/derived_from/tests/reports DAG로 affected_refs/approval_checks/reusable_refs를 계산한다. 과거 객체 보존, 재검토 대상만 새 event.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_dependencies.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A08 의존 관계와 변경 영향` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 왜 일부 결과만 다시 검토하는지 목록을 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task A09: 반복·비용 예산과 안전한 재개

**선행:** A08. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/budgets.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_budgets.py`.

**Interfaces:** `assess_next_work(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 질문·근거·기준·작업 binding 비교, correction_ref 예외, returns/run/cost 예산을 분리한다. unknown 비용은0이 아니다. resume은 후속 작업과 대기 원인을 반환한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 새 UUID만 다른 동일 작업 → repeated_work; 비용 unknown+필수 비용 제한 → awaiting_input; 한도 소진 → blocked_budget
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_budgets.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 질문·근거·기준·작업 binding 비교, correction_ref 예외, returns/run/cost 예산을 분리한다. unknown 비용은0이 아니다. resume은 후속 작업과 대기 원인을 반환한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_budgets.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): A09 반복·비용 예산과 안전한 재개` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 무한 토론 대신 무엇이 필요해서 멈췄는지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.
