# M1 A — Reviewable Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 사용자가 화면·정책을 먼저 검토하고 실제 독립 에이전트 연결 가능성을 확인한다.

**Architecture:** 고정 조회 JSON과 읽기 전용 UI 시안을 먼저 만들고, 호스트 실행 확인을 통해 이후 협의 레코드의 보증 범위를 정한다. 엔진 변경은 순수 그래프·역할 계약까지 제한한다.

**Tech Stack:** Python >=3.11, pytest, HTML/CSS/JavaScript, 현재 호스트 에이전트 도구.

**Spec:** [총괄 계획](2026-09-08-m1-transition.md), [설계](../specs/2026-09-08-three-milestone-research-graph-design.md).

## Global Constraints

총괄 계획의 모든 제약을 적용한다. 예시를 실제 대화로 표시하지 않는다. 이 묶음에서 기존 프로젝트를 수정하지 않는다. 실제 에이전트 검사는 구현 실행 시 수행하며 계획 작성 턴에 실행하지 않는다.

## Task 01: 범위·정책·개발 기준선

**Files:** Create `docs/superpowers/specs/2026-09-08-m1-contracts-design.md`, `docs/superpowers/plans/2026-09-08-m1-a-verification.md`. 환경 설치는 소스 변경 없이 격리 환경에 한다.

**Interfaces:** Consumes 총괄 제안 정책. Produces 아래 네 정책의 사용자 검토 결과와 실행 환경·검사 기준선.

- [x] 신규 프로젝트만 지원하고 기존 프로젝트를 유지하는 적용 정책을 명시한다.
- [x] 세 판단 역할의 진행 동의와 차단 쟁점 해소 조건을 구체적 예로 보여준다. 불일치를 다수결로 덮지 않는 기본값을 확인한다.
- [x] 기본 추가 복귀 2회·한 응답 라운드의 의미와 사용자 조정 방식을 확인한다. 임의 예산을 승인된 값으로 기록하지 않는다.
- [x] 첫 UI는 읽기 전용이며 승인은 현재 대화+CLI에서 수행한다는 범위를 확인한다.
- [x] `command -v python3 python3.11 python3.12 python3.13 uv node`와 각 실제 버전을 확인한다. 이전 문서의 `/opt/homebrew/bin/python3.11`을 존재 확인 없이 사용하지 않는다.
- [x] Python >=3.11을 확인한 인터프리터로 격리 환경을 만들고 `.[dev]`를 설치한다. 이후 명령의 `python`은 그 환경을 뜻한다.
- [x] 아래 기준선 검사를 실행하고 counts·skip·warning을 그대로 기록한다.

```sh
python -m pytest tests/codex_native/test_foundation_e2e.py tests/codex_native/test_knowledge_extraction.py tests/codex_native/test_synthesis.py tests/codex_native/test_hypothesis_generation.py tests/codex_native/test_approval.py tests/codex_native/test_plugin_package.py -q
```

- [ ] 전체 기본 회귀 `python -m pytest -q`도 변경 전 실행한다. 기존 실패는 새 기능 실패와 분리한다. **실행은 했으나 75% SSL 대기로 중단; 부분 결과와 환경 실패 재검사는 기준선 기록 참조.** 새 환경에서 이전 4,797 통과 수치를 그대로 기대값으로 사용하지 않는다.
- [x] 기준선과 정책 결정을 문서로 묶어 검토한다. 제품 코드를 수정하지 않는다.

**User check:** 네 정책이 본인의 의도와 맞는지, 개발 전 기존 기능의 검사 상태가 무엇인지 확인한다.

## Task 02: 결정 과정 UI 시안

**Files:** Create `researchclaw/codex/m1_ui/index.html`, `styles.css`, `app.js`, `graph.js`, `detail.js`; `tests/ui/m1/demo.json`, `view.test.mjs`.

**Interfaces:** Consumes 총괄의 View JSON. Produces `selectDecision(view, id)`와 `renderResearchView(root, view)`(app.js named exports). 전자는 결정 또는 null을 반환하며 후자는 DOM에 화면을 렌더링한다. `data_origin`은 `demo`/`registered`만 허용한다.

- [x] UI 제작 전 Sites 스킬에 따라 작업공간·제작 경로를 확인한다. 최종 패키지 파일은 위 경로로 유지하고 외부 연구 데이터 배포는 하지 않는다.
- [x] 아래 데이터는 예시임을 표시하고 demo.json을 만든다. 최상위 View 필드를 모두 포함하고 아래 식별자를 사용한다: `H1`, `H1-r1`, `H1-r2`, `I1`, `R1`, `D1`, `A1`. 내용은 '집계 평균 개선' 가설이 집단 혼합 지적을 받고 '집단별 차이 확인'으로 바뀌는 합성 예시다. 실제 논문·수치·에이전트 실행 ID를 꾸미지 않는다.
- [x] `nodes`에는 M1 작업 열 개, `edges`에는 정상 경로와 가설/자료 복귀선, `decisions`에는 `D1`, `selected_hypothesis_ids:[]` (복귀 결정이므로 수정 가설은 아직 미선택), `issue_ids:["I1"]`, 근거·응답 참조를 넣는다. 모든 UI 참조가 같은 JSON 안에서 해석되게 한다.
- [x] 행위 검사를 먼저 작성한다.

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import {selectDecision} from '../../../researchclaw/codex/m1_ui/app.js';
test('선택한 결정만 반환하고 없는 ID는 null', () => {
  const decision = {id:'D1', issue_ids:['I1']};
  const view = {decisions:[decision]};
  assert.deepEqual(selectDecision(view, 'D1'), decision);
  assert.equal(selectDecision(view, 'missing'), null);
});
```

- [x] `node --test tests/ui/m1/view.test.mjs`로 초기 실패를 확인한다. ES module 해석을 위해 UI 디렉터리에 `package.json`의 `{"type":"module","private":true}`를 추가한다. 런타임 라이브러리 설치는 필요 없다.
- [x] 최소 조회 로직을 작성하고 그래프·작업 상세·쟁점 상세·버전 비교를 연결한다.

```js
export function selectDecision(view, id) {
  return view.decisions.find(item => item.id === id) ?? null;
}
```

- [x] 모든 연구 텍스트는 `textContent`로 렌더링한다. DOM 선택 이벤트로 I1→R1→D1과 H1-r1→H1-r2를 이동하게 한다. 연구 텍스트를 `innerHTML`에 넣지 않는다.
- [x] 브라우저에서 360px·736px 폭, 키보드 이동, 밝은/어두운 모드, 빈 데이터·긴 반론·존재하지 않는 참조를 확인한다.
- [x] 시안을 사용자에게 보여주고 '왜 수정됐는지', '왜 다른 후보를 버렸는지'를 찾아보게 한다. 검사와 시안 결과를 기록하고 작업 커밋으로 묶는다.

**User check:** D1을 선택해 최초 가설·반론·수정·결정 이유까지 이동할 수 있다. 화면 상단의 '예시 데이터'가 명확하다.

## Task 03: 실제 독립 에이전트 연결 확인

**Files:** Create `docs/superpowers/plans/2026-09-08-m1-host-verification.md`, `skills/researchclaw/references/m1-host-contract.md`. 실제 발언 원문은 task-owned acceptance project에 보존하며 fixture와 분리한다.

**Interfaces:** Consumes 현재 호스트 배정·메시지·결과 도구. Produces `Assignment.provenance_status`의 `host_observed`, `declared_only`, `unavailable` 의미와 호스트 테스트 기록. 과학적 독립성 인증이라고 부르지 않는다.

- [x] 격리된 합성 문헌 두 개와 가설 하나를 만든다. 자료 표지에 워크플로 검사용 합성 자료임을 명시한다.
- [x] 조정자와 실제 세 판단 에이전트를 배정한다. 현재 슬롯이 충분하지 않으면 독립 배정을 순차 수행한다. 작성자와 검토자를 구분한다.
- [x] 최초 입력에 타인의 의견을 넣지 않는다. 역할별 입력 목록과 실제 호스트 작업 ID를 기록한다.
- [x] 세 최초 제출 후 같은 이전 라운드 스냅샷을 전달해 쟁점 응답을 받는다. 재개 실패 시 새 작업으로의 대체 관계와 전달 문맥을 명시한다.
- [x] 다음 구조로 호스트 관측 사실을 기록한다. 원문은 실제 반환값을 사용한다.

```json
{"schema_version":1,"host_support":{"task_id":true,"separate_initial_inputs":true,"resume_assignment":false},"verification_scope":"host_observed_only","observed_assignments":[],"limitations":[]}
```

위 JSON의 boolean·배열은 실제 도구 결과로 채운다. 실행 식별자를 관측할 수 없으면 false/미확인으로 바꾸고 인증된 실행으로 승격하지 않는다.

- [x] 사용자가 제출·응답의 출처를 열어보고 시안 대화와 실제 대화 차이를 확인할 수 있게 한다.
- [x] 호스트 기록을 얻을 수 없다면 UI의 독립 실행 확인 범위를 줄이거나 구현 경로를 재검토한다. fixture를 사용해 이 작업을 통과시킨 것으로 보고하지 않는다.
- [x] 네트워크/LLM 프로세스를 Python CLI에서 실행하지 않았는지 확인하고 실제 제약과 후속 기록 계약을 문서화한다.

**User check:** 세 실제 역할의 서로 다른 제출과 응답을 본다. 여기서는 새 M1 엔진 등록이 아직 없다는 점을 표시한다.

## Task 04: 그래프·역할·스키마 순수 계약

**Files:** Create `researchclaw/core/m1/__init__.py`, `contracts.py`, `roles.py`; `tests/codex_native/m1/__init__.py`, `test_contracts.py`, `test_roles.py`.

**Interfaces:** Produces `describe_graph() -> dict[str, object]`, `allowed_return_targets(node_id: str) -> tuple[str, ...]`, `describe_roles(node_id: str) -> dict[str, object]`. 입력이 알려진 노드가 아니면 `m1_node_unknown`.

- [x] 총괄 노드·연결과 task 01 정책을 계약 문서에 고정한다. ID를 UI 제목과 분리한다.
- [x] 먼저 금지 경로와 신규 버전의 순수 검사를 작성한다.

```python
import pytest
from researchclaw.core.m1.contracts import describe_graph, allowed_return_targets

def test_m1_review_can_return_to_evidence_but_not_execute():
    graph = describe_graph()
    assert graph['workflow_version'] == 'm1-graph-v1'
    targets = allowed_return_targets('review')
    assert 'search' in targets and 'hypothesize' in targets
    assert 'experiment_run' not in targets
    with pytest.raises(ValueError, match='m1_node_unknown'):
        allowed_return_targets('stage-12')
```

- [x] `python -m pytest tests/codex_native/m1/test_contracts.py tests/codex_native/m1/test_roles.py -q`의 실패 이유를 확인한다.
- [x] 노드와 복귀 허용 목록을 닫힌 카탈로그로 정의한다.

```python
NODE_IDS = ('scope','questions','search','collect','screen','extract',
            'synthesize','hypothesize','review','handoff')
RETURN_TARGETS = {
    'scope':('scope',),
    'questions':('scope','questions'),
    'search':('questions','search'),
    'collect':('search','collect'),
    'screen':('search','collect','screen'),
    'extract':('screen','extract'),
    'synthesize':('search','collect','screen','extract','synthesize'),
    'hypothesize':('synthesize','hypothesize'),
    'review':NODE_IDS[:8],
    'handoff':('review',),
}
def allowed_return_targets(node_id: str) -> tuple[str, ...]:
    if node_id not in NODE_IDS:
        raise ValueError('m1_node_unknown')
    return RETURN_TARGETS[node_id]
```

- [x] `describe_graph`는 새 dict를 반환하고 상태 파일을 열지 않는다. 역할별 질문은 해당 노드의 목적·근거·대안을 다루며 조정자 비투표·자기 승인 금지를 명시한다.
- [x] 반환값 변조가 다음 조회에 남지 않는 검사와 역할/권한 검사를 추가해 실행한다. 기존 `test_agent_roles.py`도 실행한다.
- [x] A 확인 결과와 그래프·역할 계약을 기록해 커밋한다.

**User check:** 각 노드의 담당·질문·입출력과 가능한 복귀 목적지를 읽기 전용으로 볼 수 있다.
