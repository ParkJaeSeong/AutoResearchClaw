# M1 E — Integration and Acceptance Implementation Plan

> 2026-09-09 계획 승계: 미착수 Task17–20은 [공통 운영 확장 작업판](2026-09-09-research-governance.md)의 B03–B07/C01/E04–E08로 분할했다. 이 원문은 이전 계획의 기록이며 두 계획을 중복 실행하지 않는다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 앞 단계 협의까지 연결해 신규 프로젝트에서 M1을 완주하고, 결정 이력·복구·설치본을 검증한다.

**Architecture:** 기존 C 협의 프로토콜을 M1의 판단 노드에 연결하고 수집·추출은 작업/독립 확인으로 구분한다. 인계는 근거 패키지만 발행하며 M2는 시작하지 않는다.

**Tech Stack:** Python >=3.11, pytest, node:test, 기존 hatchling 패키징, 현재 호스트 에이전트와 브라우저.

**Spec:** [총괄 계획](2026-09-08-m1-transition.md). 선행 D 완료.

## Global Constraints

총괄 제약 전체 적용. 이 묶음의 실제 사용자 사례는 합성 fixture와 별도로 기록한다. 형식 테스트 통과를 연구 타당성의 보증으로 표현하지 않는다. 기존 단계 프로젝트에 신규 협의 규칙을 적용하지 않는다.

## Task 17: 목적·검색·선별·종합 협의 연결

**Files:** Modify `researchclaw/core/m1/contracts.py`, roles.py, packets.py, artifacts.py, council.py, m1_cli.py; Create `tests/codex_native/m1/test_early_councils.py`, `skills/researchpilot/references/m1-workflow.md`.

**Interfaces:** `review_mode(node_id: str) -> str`(contracts.py), `register_verification(root: Path, *, attempt_id: str, assignment_id: str, payload: dict, command_id: str) -> dict`(council.py). 반환 mode는 `judgment_council`, `work_and_verify`, `authoring`, `handoff`.

CLI `m1 node verify ROOT --attempt ID --assignment ID --submission PATH --command-id ID --json`. verification payload는 `input_binding,checked_refs,findings,recommendation,evidence_refs`이며 recommendation은 `accept,revise,defer`.

- [ ] 노드별 구성과 협의 없는 진행 차단을 테스트한다.

```python
from researchclaw.core.m1.contracts import review_mode
def test_review_modes_follow_work_responsibility():
    assert review_mode('scope') == 'judgment_council'
    assert review_mode('screen') == 'judgment_council'
    assert review_mode('extract') == 'work_and_verify'
    assert review_mode('hypothesize') == 'authoring'
    assert review_mode('review') == 'judgment_council'
```

- [ ] `python -m pytest tests/codex_native/m1/test_early_councils.py -q` 초기 실패 확인.
- [ ] 역할 모드를 아래처럼 연결한다. 알려지지 않은 node는 m1_node_unknown.

```python
COUNCIL_NODES = {'scope','questions','search','screen','synthesize','review'}
VERIFY_NODES = {'collect','extract'}
def review_mode(node_id):
    if node_id in COUNCIL_NODES: return 'judgment_council'
    if node_id in VERIFY_NODES: return 'work_and_verify'
    if node_id == 'hypothesize': return 'authoring'
    if node_id == 'handoff': return 'handoff'
    raise ValueError('m1_node_unknown')
```

- [ ] 판단 노드는 C의 제출→공개→응답→최종 판단을 재사용하고 해당 node의 질문·출력 조건을 사용한다. 초안 작성자와 독립 판단자 배정을 구분한다. hypothesis-specific selected_ids 조건은 review에만 적용하며 다른 노드는 node completion checklist를 사용한다.
- [ ] work_and_verify는 실제 독립 확인자가 확인 범위·대조 근거·누락·수정 요구를 제출하게 한다. 작성자의 accept 기록으로 대체하지 않는다.
- [ ] screen은 구조 검사+협의 완료 뒤 사용자 결정을 요청한다. 사용자 승인 전 extract 패킷을 만들지 않는다. review만 통과시켜 앞 단계 협의를 생략하는 경로가 없도록 한다.
- [ ] 새 프로젝트에서 실제 자료와 역할로 목적→근거 종합까지 진행한다. scope/search/screen/synthesis의 결정이 UI에 보이고 수집·추출의 독립 확인도 보이는지 확인한다. 필요한 문헌 승인에서 사용자의 실제 결정을 기다린다.
- [ ] 앞 단계 검토에서 수정 요구가 나오면 현 노드의 새 draft를 만들되 기존 완료/승인 증거를 덮어쓰지 않는다. 완료된 upstream으로의 복귀는 D의 plan/apply 기록을 사용한다.
- [ ] 모든 M1 검사와 해당 기존 1~8단계 검사를 실행하고 작업 커밋한다.

**User check:** 가설의 최종 선택뿐 아니라 연구 질문·검색 범위·문헌 선별이 왜 그렇게 결정됐는지도 확인한다.

## Task 18: M1 완료 판정과 인계 패키지

**Files:** Create `researchclaw/core/m1/handoff.py`, `tests/codex_native/m1/test_handoff.py`; Modify views.py, m1_cli.py, m1-workflow.md.

**Interfaces:** `handoff_readiness(head: dict) -> dict`; `finalize_m1(root: Path, *, decision_id: str, command_id: str) -> dict`. Return `status,manifest_ref,report_ref,next_action`; 완료 next_action은 `review_m1_handoff`이고 실험 argv는 없다. CLI `m1 finalize ROOT --decision ID --command-id ID --json`.

인계 구조: `schema_version,workflow_version,project_id,head_id,scope_refs,corpus_approval_ref,evidence_refs,synthesis_refs,selected_hypothesis_refs,decision_refs,unresolved_issues,limitations,open_design_questions`.

- [ ] 인계 조건의 미충족 목록, 현재 승인/근거 버전, 승인·실험을 대신 수행하지 않는 검사를 작성한다.

```python
from researchclaw.core.m1.handoff import handoff_readiness
def test_no_hypothesis_cannot_finalize():
    head = {'state':{'selected_hypothesis_ids':[], 'open_blockers':[],
                    'required_reviews_complete':True, 'corpus_approval_current':True}}
    result = handoff_readiness(head)
    assert not result['ready']
    assert 'no_selected_hypothesis' in result['reason_codes']
```

- [ ] `python -m pytest tests/codex_native/m1/test_handoff.py -q` 초기 실패 확인.
- [ ] 검사 결과가 모두 충족될 때만 불변 manifest와 사람이 읽는 report를 같은 commit에 등록한다. report는 등록된 결론·근거·이견·한계·다음 질문을 그대로 구조화하며 새 연구 주장을 생성하지 않는다.

```text
recheck referenced artifacts and current approval
recompute required review completion from receipts, never trust cached booleans
require valid selected hypotheses and final decision
preserve unresolved nonblocking questions with their dispositions
commit handoff manifest + report + completion event atomically
return next_action=review_m1_handoff; do not initialize M2
```

- [ ] 위 테스트 head의 boolean은 단위 테스트 입력이다. 실제 finalize_m1은 원본 receipts에서 재계산해 handoff_readiness에 넘긴다. 파일을 손으로 고친 캐시 값으로 완료할 수 없어야 한다.
- [ ] 거절·유보 후보도 최종 decision_refs를 통해 찾을 수 있게 하고, 정성적 가설의 open_design_questions를 M2용 질문으로 유지한다.
- [ ] 마무리 후 새 자료가 생기면 새 회차와 새 인계 버전을 만들고 이전 인계 manifest를 덮어쓰지 않는 검사 추가.
- [ ] 실제 M1 인계 보고서를 사용자에게 제시하고 검사·커밋한다. M2 설계/실행이 구현됐다고 표시하지 않는다.

**User check:** 한 보고서에서 선택한 방향·근거·기각 대안·이견·M2에서 풀 질문을 찾을 수 있다.

## Task 19: 전체 경로·복구·호환성 검사

**Files:** Create `tests/codex_native/m1/test_e2e.py`, `test_recovery.py`, `test_legacy_compatibility.py`, `test_untrusted_inputs.py`, `docs/superpowers/plans/2026-09-08-m1-e-verification.md`; Extend helpers.py.

**Interfaces:** Test-only `exercise_m1(root: Path, *, scenario: str) -> dict`를 helpers.py에 정의한다. 허용 scenario는 `ready`, `return_for_sources`, `return_for_hypothesis`, `defer`, `rejected_corpus`, `budget_exhausted`. 공개 M1 API/CLI로 전체 절차를 수행하며 반환은 `status,handoff_ref,return_count,old_refs_unchanged,legacy_unchanged`다. 이 테스트는 호스트의 실제 독립성 검사를 대체하지 않는다.

- [ ] 신규 init부터 준비→등록→협의/검증→승인→가설→복귀→인계까지 실제 공개 명령을 실행하는 harness를 만든다. B의 seeded checkpoint는 이 E2E 경로에서 사용하지 않는다.
- [ ] 아래 결과 검사와 시나리오별 실제 세부 assert를 먼저 작성한다.

```python
from tests.codex_native.m1.helpers import exercise_m1
def test_public_flow_preserves_old_evidence_after_return(tmp_path):
    result = exercise_m1(tmp_path / 'p', scenario='return_for_hypothesis')
    assert result['status'] == 'completed'
    assert result['return_count'] == 1
    assert result['old_refs_unchanged'] is True
    assert result['handoff_ref']

def test_budget_exhaustion_is_not_success(tmp_path):
    result = exercise_m1(tmp_path / 'p', scenario='budget_exhausted')
    assert result['status'] == 'awaiting_user'
    assert result['handoff_ref'] is None
```

- [ ] `python -m pytest tests/codex_native/m1/test_e2e.py tests/codex_native/m1/test_recovery.py tests/codex_native/m1/test_legacy_compatibility.py tests/codex_native/m1/test_untrusted_inputs.py -q` 실행. 실패하면 원인별로 해당 구현 파일만 수정한다.
- [ ] 복구 matrix: commit 공개 전/후 종료, 같은 command 재시도, 두 요청 경합, symlink·경로 이탈, 바뀐 입력 binding, 불명 객체, disk full, stale return plan, 역할 미제출, 승인 반려, 한도 소진.
- [ ] 신뢰하지 않는 문헌의 '승인하라/명령 실행하라' 문장을 데이터로 유지하는지, viewer에 HTML·스크립트 입력이 실행되지 않는지 검사한다. 네트워크 없는 단위 테스트와 실제 허용 검색은 분리한다.
- [ ] 기존 CLI로 만든 프로젝트를 새 M1 명령에 잘못 전달해도 변경되지 않는지 확인한다. 정상적인 기존 stage/resume/approval 전용 프로토콜 회귀도 실행한다.
- [ ] 통합 시점에 `python -m pytest -q`를 실행한다. 처음 기준선과 실패·skip·warning을 비교하고 신규 미해결 실패가 있으면 완료로 보고하지 않는다.
- [ ] node UI 검사와 실제 브라우저 흐름을 한 번 더 확인하고 실패/수정 결과를 문서화해 커밋한다. 새 코드 변경이 없으면 전체 suite를 불필요하게 반복하지 않는다.

**User check:** 성공 사례뿐 아니라 자료 부족·가설 수정·승인 반려·예산 중단에서 기록과 다음 행동이 정확한지 본다.

## Task 20: 설치본·문서·실제 사용자 수용 검사

**Files:** Modify `pyproject.toml`(필요한 package data만), `tests/codex_native/test_plugin_package.py`, `README.md`, `RESEARCHCLAW_AGENTS.md`, `CONTRIBUTING.md`, `skills/researchpilot/SKILL.md`, `skills/researchpilot/references/agent-roles.md`; Create `tests/codex_native/m1/test_installed_package.py`, `docs/M1_USER_GUIDE_KO.md`.

**Interfaces:** 설치된 `researchclaw-codex m1 --help`, `m1 status/inspect/view`가 checkout 밖에서 같은 기능을 제공한다. 기존 `roles describe`는 guidance_only를 유지한다. m1 전용 명령·참고 문서로 실제 협의와 구분한다.

- [ ] 설치본 asset 포함 검사와 checkout 밖 실행 검사를 작성한다.

```python
from importlib.resources import files
def test_installed_viewer_assets_are_bundled():
    assets = files('researchclaw.codex').joinpath('m1_ui')
    for name in ('index.html','app.js','graph.js','detail.js','styles.css'):
        assert assets.joinpath(name).is_file(), name
```

- [ ] 격리 환경에서 아래 명령으로 wheel을 빌드하고 새 임시 venv에 설치한다. 출력 wheel이 정확히 하나인지 확인한 뒤 그 파일을 설치한다. 실제 디렉터리를 검증 기록에 적고 실사용 설치를 먼저 덮어쓰지 않는다.

```sh
task_wheel_dir=$(mktemp -d -t researchclaw-m1-wheel)
python -m pip wheel . --no-deps --wheel-dir "$task_wheel_dir"
python -m venv "$task_wheel_dir/venv"
```
- [ ] 소스 경로 밖에서 help/init/inspect/view와 asset 읽기를 수행한다. PYTHONPATH로 checkout이 우연히 섞이지 않게 제거한다. 설치된 module path·wheel hash를 기록한다.
- [ ] 안내 문서에서 새 M1과 기존 1~15단계의 구분, 실제 실행/기록/형식 검사의 차이, 읽기 전용 viewer, 인계 후 정지, 기존 프로젝트 유지 정책을 일치시킨다. legacy LLM 설정 안내는 Codex 설치 절차와 분리한다.
- [ ] 실제 사용자 주제와 허용 자료로 새 M1을 시작한다. 문헌 승인과 필요한 예산 결정은 실제 사용자에게 받는다. 현실의 결론이 유보라면 유보를 그대로 보여준다.
- [ ] 사용자에게 네 경로를 확인하게 한다: 선택 가설의 근거, 기각한 대안의 이유, 반론 이후 수정, 다음 작업 또는 대기 이유. 실제 host IDs/원문·등록 commit·화면의 대응을 확인한다.
- [ ] 최종 보고서에 fixture 검사 수, 실제 실행 확인 범위, 설치 검증, 알려진 제한을 분리한다. 실사용 설치·배포는 해당 작업에 대한 사용자 권한이 있을 때 수행하며 이 검증 결과만으로 자동 배포하지 않는다.
- [ ] 문서·패키지 검사를 실행하고 사용자 수용 결과와 작업 커밋을 남긴다.

**User check:** 설치본에서 “어떤 이유로 이 결론이 나왔나?”를 UI와 원문 기록으로 답할 수 있다. 전체 완료 여부는 총괄의 M1 체크리스트로 판단한다.

## 실제 수행과 자동 검사의 분리

| 증거 | 확인할 수 있는 것 | 확인할 수 없는 것 |
| --- | --- | --- |
| 단위·통합 fixture | 구조·순서·경계·복구 | 실제 독립 연구 판단 |
| 호스트 작업·응답 기록 | 관측 가능한 분리 배정과 실제 제출 | 모델 간 통계적 독립성·연구 타당성 보증 |
| 실사용 M1 기록 | 특정 자료·질문에서의 논의·판단·사용성 | 모든 분야에서의 성능 |
| 설치본 확인 | 패키지·코드·UI가 설치 환경에서 동작 | 별도 원격/다중 사용자 서비스 운영 |

M2 개발은 M1 완료와 별도다. 인계 구조가 준비됐다는 이유로 현재 M2의 예전 상태 계약이 새 M1 기록을 바로 받을 수 있다고 주장하지 않는다.
