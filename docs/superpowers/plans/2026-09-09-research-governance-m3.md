# M3 주장·심사·최종화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** M3 주장·심사·최종화를 독립 검토 가능한 작은 작업으로 구현한다.

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

## Task D01: 최종 주장과 근거 범위 연결

**선행:** C06. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m3/claims.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m3_claims.py`.

**Interfaces:** `build_claim_map(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** M3 claim_id/revision→M2 분석·실행→M1 가설·출처를 연결한다. unsupported/deferred 주장과 부정 결과도 명시한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 평균 결과만으로 모든 하위집단 효과 주장 → claim_scope_issue; source없는 주장 → 차단
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_claims.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: M3 claim_id/revision→M2 분석·실행→M1 가설·출처를 연결한다. unsupported/deferred 주장과 부정 결과도 명시한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_claims.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): D01 최종 주장과 근거 범위 연결` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 보고서 각 주장에 어떤 근거와 한계가 있는지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task D02: 본문·도표·재현 안내 버전 등록

**선행:** D01. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m3/drafts.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m3_drafts.py`.

**Interfaces:** `register_draft(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 본문·도표·방법·실패 및 부정 결과·재현 안내를 manifest로 묶고 각각 claim/result refs를 고정한다. 문서 형식은 Markdown+정적 assets부터 지원.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 도표가 다른 run/result 버전 참조 → mismatch; 근거 없는 문장 변경 → 새 claim 심사 필요
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_drafts.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 본문·도표·방법·실패 및 부정 결과·재현 안내를 manifest로 묶고 각각 claim/result refs를 고정한다. 문서 형식은 Markdown+정적 assets부터 지원.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_drafts.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): D02 본문·도표·재현 안내 버전 등록` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 본문·그림과 실제 결과가 같은 버전인지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task D03: 독립 심사와 쟁점별 수정·역방향 복귀

**선행:** D02,B02,A08. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m3/review.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m3_review.py`.

**Interfaces:** `prepare_manuscript_review(snapshot: dict) -> dict; propose_review_action(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 표현 수정은 M3, 추가 분석은 M2, 문헌/가설 문제는 M1으로 배정한다. 심사 응답과 확인자가 별도 제출한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 작성자가 resolved 선언만 함 → 거부; 분석 오류 발견 → M2 특정 node로 복귀+영향 목록
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_review.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 표현 수정은 M3, 추가 분석은 M2, 문헌/가설 문제는 M1으로 배정한다. 심사 응답과 확인자가 별도 제출한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_review.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): D03 독립 심사와 쟁점별 수정·역방향 복귀` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 심사 의견이 문장 수정인지 새 연구가 필요한 문제인지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task D04: 최종 출처·무결성·재현 감사

**선행:** D03. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m3/audit.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m3_audit.py`.

**Interfaces:** `assess_final_audit(snapshot: dict) -> dict`

**산출물·구현 범위:** 모든 주장·도표·실행·문헌 참조와 공개 범위·누락·승인 binding·열린 차단을 검증한다. 독립 감사 receipt 필요.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: stale 분석/최종 승인 또는 핵심 열린 쟁점 → finalization_blocked; 한계 기록만으로 차단 해소 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_audit.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 모든 주장·도표·실행·문헌 참조와 공개 범위·누락·승인 binding·열린 차단을 검증한다. 독립 감사 receipt 필요.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_audit.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): D04 최종 출처·무결성·재현 감사` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 최종 패키지에서 빠진 근거와 재검토할 항목을 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task D05: 사용자 최종 결정과 로컬 보관

**선행:** D04. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m3/archive.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m3_archive.py`.

**Interfaces:** `finalize_package(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 정확한 manifest hash에 대한 사용자 최종 결정과 로컬 패키지·checksum·이력 저장. 외부 게시/제출/공유 호출 없음.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 승인 후 원고 변경 → 재감사/승인 필요; finalize에서 네트워크 전송 발생 → 실패
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_archive.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 정확한 manifest hash에 대한 사용자 최종 결정과 로컬 패키지·checksum·이력 저장. 외부 게시/제출/공유 호출 없음.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m3_archive.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): D05 사용자 최종 결정과 로컬 보관` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 승인한 버전과 전달 파일이 일치하는지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.
