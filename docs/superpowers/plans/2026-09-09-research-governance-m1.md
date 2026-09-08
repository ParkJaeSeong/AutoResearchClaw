# M1 보완과 인계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** M1 보완과 인계를 독립 검토 가능한 작은 작업으로 구현한다.

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

## Task B01: 공통 원천과 근거 의존성

**선행:** A08. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/evidence_origins.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_evidence_origins.py`.

**Interfaces:** `group_origins(snapshot: dict) -> dict`

**산출물·구현 범위:** M1 인용·데이터셋 원천을 origin_group_id로 연결한다. unknown을 남기고 출처 개수·원천 집합을 별도 표시한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 논문3개가 같은 데이터셋 → source_count3/origin_groups1; 원천 불명 → unknown, 독립으로 자동 분류 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_evidence_origins.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: M1 인용·데이터셋 원천을 origin_group_id로 연결한다. unknown을 남기고 출처 개수·원천 집합을 별도 표시한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_evidence_origins.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): B01 공통 원천과 근거 의존성` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 근거가 많아 보이는 이유가 실제 다양성인지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task B02: 독립 패킷·공개·호스트 관측

**선행:** A06. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/councils.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_councils.py`.

**Interfaces:** `reviewer_packet(snapshot: dict, assignment_id: str) -> dict; register_submission(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** M1 council 최초/응답/최종 계약을 노드 중립 형태로 연결한다. 공개 전 본문·해시 접근 권한 검사, 모델/host 관측과 isolation_level 명시.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 첫2개 제출은 본문 비공개;3개 뒤 공개; 다른 배정 결과 경로 읽기 거부 가능 여부를 실제 호스트별 기록
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_councils.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: M1 council 최초/응답/최종 계약을 노드 중립 형태로 연결한다. 공개 전 본문·해시 접근 권한 검사, 모델/host 관측과 isolation_level 명시.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_councils.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): B02 독립 패킷·공개·호스트 관측` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 공유 자료와 비공개 최초 의견을 구분하고 실제 실행 확인 범위를 본다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task B03: 목적·질문 협의 연결

**선행:** B02,A07. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m1_scope.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m1_scope.py`.

**Interfaces:** `prepare_scope_council(snapshot: dict, *, node_id: str) -> dict`

**산출물·구현 범위:** scope/questions 노드에 실제 작성·독립 검토·응답·최종 판정을 연결한다. 사용자 목적과 에이전트 가정 분리.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 작성자 자기 승인·scope 미검토 상태에서 search 진행 → 거부; 모호성 수정은 새 회차
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_scope.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: scope/questions 노드에 실제 작성·독립 검토·응답·최종 판정을 연결한다. 사용자 목적과 에이전트 가정 분리.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_scope.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): B03 목적·질문 협의 연결` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 연구 질문이 왜 선택됐는지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task B04: 검색·선별 협의와 문헌 승인

**선행:** B03. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m1_search.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m1_search.py`.

**Interfaces:** `prepare_search_council(snapshot: dict, *, node_id: str) -> dict`

**산출물·구현 범위:** search/screen 검토와 승인된 문헌 집합 binding을 연결한다. 반대 근거 누락을 쟁점으로 기록한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: screen 합의만 있고 사용자 문헌 승인 없음 → extract 대기; corpus 변경 → 기존 승인 재사용 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_search.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: search/screen 검토와 승인된 문헌 집합 binding을 연결한다. 반대 근거 누락을 쟁점으로 기록한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_search.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): B04 검색·선별 협의와 문헌 승인` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 검색 범위·문헌 제외 이유·사용자 승인 경계를 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task B05: 수집·추출의 독립 원문 대조

**선행:** B04,A05. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m1_evidence.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m1_evidence.py`.

**Interfaces:** `prepare_evidence_check(snapshot: dict, *, node_id: str) -> dict`

**산출물·구현 범위:** collect/extract에는 투표 대신 독립 원문 확인을 연결한다. 문헌 위치·접근 수준·원문 관측과 추론을 구분한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 추출 수치와 원문 다름 → source_check 쟁점; 초록만 접근한 기록을 fulltext 확인으로 표시하면 거부
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_evidence.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: collect/extract에는 투표 대신 독립 원문 확인을 연결한다. 문헌 위치·접근 수준·원문 관측과 추론을 구분한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_evidence.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): B05 수집·추출의 독립 원문 대조` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 에이전트 대화 외에 실제 원문 대조가 수행됐는지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task B06: 종합·가설과 이전 쟁점 재검토

**선행:** B05,B01. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/m1_review.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_m1_review.py`.

**Interfaces:** `prepare_hypothesis_review(snapshot: dict) -> dict`

**산출물·구현 범위:** synthesize/hypothesize/review에 공통 쟁점·근거 원천·가설 revision을 연결한다. 모든 이전 active issue에 disposition과 담당을 요구한다.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: r2 new_issues=[]이고 r1 disposition 누락 → prior_issue_unaccounted; 가설 개정만으로 resolved 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_review.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: synthesize/hypothesize/review에 공통 쟁점·근거 원천·가설 revision을 연결한다. 모든 이전 active issue에 disposition과 담당을 요구한다.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_m1_review.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): B06 종합·가설과 이전 쟁점 재검토` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** 이번 실제 사례의 여섯 쟁점이 수정 가설에서 어떻게 처리됐는지 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.

## Task B07: M1 인계 발행과 수신 준비

**선행:** B06,A09. **상태:** 미착수.

**Files:**
- Create: `researchclaw/core/research_graph/handoffs.py`
- Modify: researchclaw/core/research_graph/commands.py (mutation operation인 경우만).
- Test: `tests/codex_native/research_graph/test_handoffs.py`.

**Interfaces:** `issue_handoff(snapshot: dict, payload: dict) -> dict; accept_handoff(snapshot: dict, payload: dict) -> dict`

**산출물·구현 범위:** 고정 manifest/report와 transfer proposals를 발행하고 수신자의 수락을 분리한다. 인계 보고서에는 출처·기각 대안·미해결 질문·한계 포함.

- [ ] **1. 실패 검사 작성:** 아래 입력 상황을 유효 fixture로 만들고 실제 함수/CLI의 결과·HEAD·원문 보존을 assert한다. 테스트 이름에 거부 이유를 포함한다.

```text
case: 새 문헌으로 binding 변경 → stale_handoff; 발행만으로 M2 초기화/실험 실행 금지
assert: 해당 reason_code/상태/참조 수가 정확함
assert on rejected mutation: head_after == head_before
assert on accepted mutation: old_referenced_object_bytes_after == before
```

- [ ] **2. RED 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_handoffs.py -q`. 기대: 해당 기능 부재/정책 불일치로 실패. 다른 fixture 오류는 먼저 보완한다.
- [ ] **3. 최소 구현:** 위 인터페이스를 노출하고 아래 순서로 처리한다. 순수 조회에서는 마지막 저장을 수행하지 않는다.

```text
read one verified snapshot
validate exact record fields, identity and referenced versions
apply this task's rule: 고정 manifest/report와 transfer proposals를 발행하고 수신자의 수락을 분리한다. 인계 보고서에는 출처·기각 대안·미해결 질문·한계 포함.
reject with the specified reason if the case above violates the rule
return projection or a transition plan to commands.apply_command
```

- [ ] **4. GREEN·회귀 확인:** `.venv/bin/python -m pytest tests/codex_native/research_graph/test_handoffs.py -q`. 영향을 받는 선행 기능 검사만 추가 실행한다. 실제 역할/브라우저/실행 확인은 해당 수용 작업에서 별도 기록하며 fixture 통과로 대신하지 않는다.
- [ ] **5. 독립 검토·기록·작업 커밋:** 위 Create/Modify/Test 파일 중 실제 변경 파일만 명시적으로 stage한다. 검토 결과·명령·수용 사례를 총괄 작업판에 기록하고 `feat(research-graph): B07 M1 인계 발행과 수신 준비` 커밋을 남긴다. 전체 계획 완료로 보고하지 않는다.

**사용자 확인물:** M1 종료 상태와 M2에서 담당할 검증 질문을 확인한다.
**완료 조건:** 이 확인물, 거부 사례, 정상 사례 및 영향 범위 회귀가 검토를 통과함. 구조 검사와 실제 연구 검증의 범위를 구분해 표시함.
