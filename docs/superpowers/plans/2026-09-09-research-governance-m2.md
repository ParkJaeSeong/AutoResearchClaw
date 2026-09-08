# M2 실험·해석·방향 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** M2 실험·해석·방향를 독립 검토 가능한 작은 작업으로 구현한다.

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

## Task C01: M2 인계 수락과 설계 질문 배정

**선행:** B07. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m2/intake.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m2_intake.py`.

**Interfaces:** `prepare_intake(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 수신 패키지 hashes/approval/질문 담당을 확인한 뒤 M2 설계 회차 생성. 하나의 project HEAD에 이관 수락·회차 등록.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 누락된 열린 질문·미수락 담당 → intake_incomplete; 이전 issue_id 유지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_intake.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 수신 패키지 hashes/approval/질문 담당을 확인한 뒤 M2 설계 회차 생성. 하나의 project HEAD에 이관 수락·회차 등록.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_intake.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): C01 M2 인계 수락과 설계 질문 배정` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** M1 쟁점이 M2의 어떤 설계 질문이 되었는지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task C02: 설계·판정 기준 고정과 독립 심사

**선행:** C01,B02. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m2/design.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m2_design.py`.

**Interfaces:** `prepare_design_review(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 대조·지표·분할·불확실성·중단 기준·예산·대안 판별 조건을 고정한다. 설계자와 심사자 분리, 기존 설계 승인 receipt 연결.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 결과를 본 뒤 원래 기준 덮어쓰기 → 거부; 새 설계 revision+탐색적 분석 표시 허용
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_design.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 대조·지표·분할·불확실성·중단 기준·예산·대안 판별 조건을 고정한다. 설계자와 심사자 분리, 기존 설계 승인 receipt 연결.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_design.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): C02 설계·판정 기준 고정과 독립 심사` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 실험 전에 무엇을 성공·실패·판정 불가로 볼지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task C03: 기존 구현·실행 준비 계약 연결

**선행:** C02. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m2/execution_bridge.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m2_execution_bridge.py`.

**Interfaces:** `prepare_execution_handoff(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 기존 research_execution/execution_gate/experiment_package_contract의 검증된 receipt를 adapter로 연결한다. 계산형 범위만 지원하고 준비·실행을 분리한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 승인 없는 실행·설계와 다른 코드 binding → gate 차단; prepare가 subprocess 본 실험을 시작하면 실패
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_execution_bridge.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 기존 research_execution/execution_gate/experiment_package_contract의 검증된 receipt를 adapter로 연결한다. 계산형 범위만 지원하고 준비·실행을 분리한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_execution_bridge.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): C03 기존 구현·실행 준비 계약 연결` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 실행할 코드·환경·예산과 아직 실행하지 않았다는 상태를 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task C04: 실행 성공·실패와 결과 무결성 등록

**선행:** C03,A05. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m2/results.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m2_results.py`.

**Interfaces:** `register_run_result(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 기존 evidence_registration 검증을 활용해 input/code/environment/log/result refs를 동결한다. 실행 실패와 유효한 부정 결과를 구분한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 로그 성공문구만 있고 결과 불명 → unverified; 파일 변경·누락 → 거부; 실패 기록도 보존
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_results.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 기존 evidence_registration 검증을 활용해 input/code/environment/log/result refs를 동결한다. 실행 실패와 유효한 부정 결과를 구분한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_results.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): C04 실행 성공·실패와 결과 무결성 등록` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 어떤 실행에서 나온 결과인지와 실패 원인을 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task C05: 독립 분석·대안 설명·쟁점 판정

**선행:** C04,B02. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m2/analysis.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m2_analysis.py`.

**Interfaces:** `prepare_analysis_council(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 관측 사실과 해석을 분리하고 불확실성·데이터 누출·평가셋 적응·경쟁 설명을 검토한다. VerificationResult와 issue disposition 연결.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 실행자는 자기 결과 독립 확인 불가; inconclusive를 supported로 요약하면 거부
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_analysis.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 관측 사실과 해석을 분리하고 불확실성·데이터 누출·평가셋 적응·경쟁 설명을 검토한다. VerificationResult와 issue disposition 연결.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_analysis.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): C05 독립 분석·대안 설명·쟁점 판정` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 결과가 가설을 지지·반박·판정 불가 중 어디까지 말하는지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task C06: 연구 방향·복귀·M3 인계

**선행:** C05,A08,A09. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m2/direction.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m2_direction.py`.

**Interfaces:** `propose_direction(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** reanalyze/redesign/rerun/return_m1/handoff_m3/defer/stop을 정확한 node와 작업·예산에 연결한다. 기존 refinement는 승인된 선택 작업으로만 재사용.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 유효한 부정 결과 → M3 인계 가능; 새 실험 비용 승인 없음 → 대기; 전체 단계 초기화 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_direction.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: reanalyze/redesign/rerun/return_m1/handoff_m3/defer/stop을 정확한 node와 작업·예산에 연결한다. 기존 refinement는 승인된 선택 작업으로만 재사용.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m2_direction.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): C06 연구 방향·복귀·M3 인계` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 더 실험할 이유와 멈출 이유, M1으로 돌아갈 근거를 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.
