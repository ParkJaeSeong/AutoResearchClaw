# Pilot 근거 검토 한 단계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 격리 프로젝트에서 근거 한 건 검토의 시작·종료 검사, 실시간 공개 기록, 보완·재개를 같은 원장과 UI로 검증한다.

**Architecture:** 기존 research_graph의 atomic commit/CAS/멱등 명령을 재사용한다. 계약/판정은 순수 함수, 실행·외부 입력은 adapter, UI는 같은 원장의 읽기 전용 투영으로 분리한다. 기존 episode는 과거 표시 호환용이며 새 검토 완료 권한으로 사용하지 않는다.

**Tech Stack:** Python, 기존 pytest와 research_graph 저장소, 브라우저 ES modules, Node test runner, 기존 Playwright 검수 환경.

**Spec:** `docs/superpowers/specs/2026-09-18-pilot-execution-lifecycle.md`

## Global Constraints

- 기존 연구·원형·대화·외부 영수증을 보존한다. 기존 API 계약과 인증을 유지한다.
- 새 구현을 보관된 실제 연구에 자동 적용하거나 완료 상태를 소급 생성하지 않는다.
- 독립 첫 의견 작성 중 사용자에게 역할별 진행은 보이되 동료 입력으로는 비공개를 유지한다.
- 구조 검사를 과학적 타당성 보증으로 표시하지 않는다.
- 첫 단위 성공을 M1 완료나 모든 감사 항목 완료로 확장하지 않는다.
- 원격 신규 접수·운영 서비스 교체는 이 단위의 범위가 아니다. 실제 모델 시험은 합성 동작 시험과 구분한다.
- 작업 트리의 기존 변경을 보존한다. 커밋할 경우 새 작업 소유 파일/변경만 선택하고 git add -A를 사용하지 않는다.

## 공통 인터페이스와 파일 책임

새 모듈 위치는 `researchclaw/core/research_graph/` 아래다.

- `execution_contracts.py`: `validate_contract(contract: dict) -> dict`, `check_input(contract: dict, packet: dict) -> dict`, `check_output(contract: dict, packet: dict, result: dict) -> dict`. 파일/네트워크 I/O 없는 검사. 반환은 `{'status':'pass'|'needs_work'|'blocked','checks':list[dict]}`. 접근·hash 확인은 adapter가 수행하고 검증된 object bytes를 packet에 전달한다. caller가 보낸 boolean만 신뢰하지 않는다.
- `execution_lifecycle.py`: `begin(snapshot,payload)`, `record(snapshot,payload)`, `finish(snapshot,payload)`, `revise(snapshot,payload)`. 기존 dispatcher handler 규격인 state_patch/event/object_inputs 반환. 각각 `execution.begin`, `.record`, `.finish`, `.revise`로 등록한다.
- `execution_view.py`: `public_execution(snapshot: dict) -> list[dict]`. 공개 가능한 event, 상태, 발언, 검사, 이전 시도 연결을 반환한다. 원시 credential/path 비노출.
- `researchclaw/codex/execution_review_runner.py`: `run_review(root, work_id, reviewer)`와 `resume_review(root, work_id, reviewer)`. reviewer는 `(role, phase, packet, run_dir) -> dict`로 기존 호스트 adapter와 동일한 의존성을 주입한다. runner가 원장 검사와 결과 연결을 책임진다.
- `researchclaw/codex/research_ui/execution.js`: `renderExecution(root, rows, uiState)`; 화면 상태는 work/attempt/event ID에 연결한다.

첫 계약은 step_id=`evidence_review`, purpose_kind=`research`, milestone=`M1`, 필수 입력=`source`, 역할=`domain,methodology,critical,coordinator`다. 결과는 `claims:[{text,evidence_refs,scope}]`, `unresolved:[{question,impact,next_action}]`, `recommendation:use|limited|hold`, `rationale`를 갖는다. 모든 claim에 입력에 존재하는 evidence_ref가 필요하다. initial→response→final 전문 역할 장벽 후 coordinator 결과를 검사한다. 이 계약의 종료는 자료 사용 범위 채택이며 가설/M1 승인 아님.

payload:

```python
# begin: 각 참조는 graph object hash; root/project는 dispatcher snapshot에서 유도
{'work_id': 'review-1', 'attempt_id': 'review-1:a1', 'contract_ref': contract_hash,
 'input_ref': packet_hash, 'policy_revision': policy_hash,
 'assignment_revision': assignment_hash, 'generation': 1}
# record: event_id를 command_id에도 사용, kind별 payload whitelist 검사
{'work_id':'review-1', 'attempt_id':'review-1:a1', 'generation':1,
 'kind':'role_started', 'actor':'domain', 'payload':{'phase':'initial'}}
# finish: 저장된 result와 검사 결과/현재 revision을 재대조; pass boolean 접수 금지
{'work_id':'review-1','attempt_id':'review-1:a1','generation':1,'result_ref':result_hash}
# revise: needs_work 결과를 고친 새 입력/시도, 이전 이력 보존
{'work_id':'review-1','previous_attempt_id':'review-1:a1','attempt_id':'review-1:a2',
 'input_ref':new_packet_hash,'reason':'근거 위치 보완','generation':2}
```

계약·입력·역할 배정은 기존 불변 objects 저장 경로로 생성한다. 외부 입력 import와 같은 방식으로 bytes를 검증하고 object_inputs에 포함한다. 위 hash 참조가 존재하지 않으면 실행하지 않는다. 신규 공통 mutation이나 임의 state patch API를 추가하지 않는다.

## Task 1: 시작·종료 검사와 기준 fixture

**Files:** Create `researchclaw/core/research_graph/execution_contracts.py`; Create `tests/codex_native/research_graph/test_execution_contracts.py`.

- [x] 첫 테스트에 아래 최소 schema 검사와 필수 입력/출력 참조 반례를 작성한다. missing input, 모르는 evidence_ref, 빈 claim, hold와 use의 구분을 각각 확인한다.

```python
def test_empty_contract_rejected():
    import pytest
    from researchclaw.core.research_graph.execution_contracts import validate_contract
    with pytest.raises(ValueError, match='execution_contract_invalid'):
        validate_contract({})
```

- [x] `.venv/bin/python -m pytest tests/codex_native/research_graph/test_execution_contracts.py -q`로 모듈 부재에 따른 실패를 확인한다.
- [x] 선언 schema의 필수/허용 키, enum, hash 참조 형식과 check_id가 고정된 검사를 구현한다. `return {'status':'blocked','checks':[{'check_id':'required_input','reason':'source_missing'}]}`처럼 원인 코드를 분리하고 사용자 문구는 UI에서 변환한다. unknown 근거를 silently drop하지 않는다.
- [x] 동일 명령으로 통과를 확인하고 claim 검사를 숫자 점수/다수결로 대신하지 않는지 검토한다. 격리 fixture는 synthetic임을 metadata에 표시한다.

## Task 2: 원자적 단계 기록·완료 우회 거부·새 시도

**Files:** Create `execution_lifecycle.py`; Modify `commands.py`, `work_episodes.py`, `work_execution.py`; Create `tests/codex_native/research_graph/test_execution_lifecycle.py`.

- [x] 기존 `commands.init_project(tmp_path,topic='lifecycle fixture',content_origin='synthetic')`로 격리 root를 만든 테스트에 시작/기록/종료 시나리오를 작성한다. 참조 objects는 Task1 fixture를 canonical bytes로 저장한다.
- [x] `.venv/bin/python -m pytest tests/codex_native/research_graph/test_execution_lifecycle.py -q`로 신규 operation 부재 실패를 확인한다.
- [x] 4개 handler를 dispatcher에 등록하고 기존 commit 함수만 사용한다. 핵심 상태 전이:

```python
# finish 내부: check_output 후 현재 input/policy/assignment/generation 일치 재검사
status = 'accepted' if report['status'] == 'pass' else 'needs_work'
# event와 report/result_ref/next action은 하나의 state_patch + event로 commit
# revise는 previous_attempt_id를 보존하고 새 generation으로 분리
```

- [x] `episode.conclude`는 실행 사실 기록으로 유지하되 lifecycle-managed work의 accepted를 변경하지 못하게 한다. 첫 단위의 policy completed 요청은 `execution_milestone_gate_required`로 거부한다. 전체 M1 gate 구현 전 임시 허용 경로를 두지 않는다. 옛 snapshot은 읽을 수 있고 자동 이관하지 않는다.
- [x] 같은 command_id 재전송 1개 기록, 다른 payload 충돌, stale generation 거부, 종료 검사 실패 시 accepted 부재, revise 후 과거 결과 불변, 실패 후 새 프로세스 read 재현을 시험한다.
- [x] 관련 기존 episode/command 테스트와 신규 테스트를 실행한다. 기존 완료 테스트의 기대값 변경은 실제 의미 변경과 함께 기록하며 검사 제거로 통과시키지 않는다.

## Task 3: 검토 실행·발언 기록·복구

**Files:** Create `researchclaw/codex/execution_review_runner.py`; Modify `researchclaw/codex/import_council.py`(기존 호출 호환 callback만); Create `tests/codex_native/test_execution_review_runner.py`.

- [x] fake reviewer 호출 목록을 저장하고 두 번째 역할 반환 직후 예외를 주입하는 테스트를 만든다. 아래처럼 완료 역할 재실행 여부를 검증한다.

```python
calls = []
def reviewer(role, phase, packet, run_dir):
    calls.append((role, phase))
    return {'rationale':'합성 검토', 'recommendation':'hold'}
# run_review/resume_review 뒤 동일 attempt의 저장 완료 역할 호출 수는 1이어야 함
```

- [x] `.venv/bin/python -m pytest tests/codex_native/test_execution_review_runner.py -q`로 runner 부재 실패를 확인한다.
- [x] 호스트 실행 전 role_started, 반환 후 role_submitted를 영속화한다. 공개 장벽 전 동료 packet/공개 view에 본문을 넣지 않는다. 기존 import_council에 optional callback을 추가해 기존 기본 호출 행동을 보존한다. 콜백 실패는 조용히 무시하지 않고 결과를 보관한 채 recovery_required로 반환한다.
- [x] saved verified 결과→원장 게시 실패에서 resume 시 결과만 재게시한다. 실행 여부 불명확하면 자동 모델 재호출을 금지한다. stop/generation 변경 이후 도착 결과는 저장하지만 채택하지 않는다.
- [x] initial 장벽, 모든 phase 발언 공개, 역할 오류/heartbeat 끊김, 저장 후 게시 전 종료, 채택 직전 입력 변경 반례를 통과시킨다. 즉시 반환 fake뿐 아니라 제어 가능한 pending reviewer를 써 실행 중 이벤트 존재를 검증한다.

## Task 4: 같은 기록을 보여주는 UI

**Files:** Create `execution_view.py`, `research_ui/execution.js`; Modify `views.py`, `research_ui/app.js`, `research_ui/styles.css`, `research_viewer.py`; Create `tests/codex_native/research_graph/test_execution_view.py`, `tests/codex_native/test_execution_ui.mjs`.

- [x] 실행 중·검사 실패·재작업·과거 HEAD fixture의 공개 view 테스트를 먼저 작성한다. 비공개 발언/토큰/로컬 파일 경로가 응답에 없어야 한다.
- [x] `.venv/bin/python -m pytest tests/codex_native/research_graph/test_execution_view.py -q`로 실패를 확인한다.
- [x] `view['executions']=public_execution(snapshot)`을 추가한다. 도구 외부 원장을 직접 결합해 미래 상태를 과거 HEAD에 표시하지 않는다. 모든 새 실행 이벤트가 graph HEAD를 변경하므로 기존 feed의 갱신 계약을 이용한다.
- [x] UI에는 현재 행동·대기 이유·초기/상호/최종 대화 탭·검사·결과를 전체 폭 접힘 행으로 렌더링한다. stage/work/attempt를 구분하고 같은 내용의 제목/상태를 반복하지 않는다. 초기 비공개는 ‘의견 작성 중/제출됨’으로 표시한다.
- [x] `node --test tests/codex_native/test_execution_ui.mjs`에서 렌더 전 실패를 확인한 뒤 DOM 구현을 완료한다. 정적 asset 등록과 실제 HTTP 제공 검사를 추가한다.
- [x] 실제 브라우저에서 running→needs_work→새 attempt→accepted를 관찰하고 5초 이내 갱신, 펼침/스크롤 보존, heartbeat 확인 필요 표시, 과거 HEAD 잠금을 확인한다. docs/ui 가이드의 2테마·1280/1920/2560 및 메뉴 두 상태, 320/390/768 넘침 검수를 기록한다.

## Task 5: 한 단계 통합 수락과 증거 보존

**Files:** Create `tests/codex_native/test_execution_vertical_slice.py`; Create `docs/evaluations/2026-09-18-pilot-lifecycle-first-slice.md`(실행할 때 작성); Modify 감사 README의 해당 항목 증거 링크만.

- [x] 공개 명령으로 계약 고정→입력 미확보→보완→실행→근거 위치 없는 결과→needs_work→새 입력/시도→원형 검증된 결과→accepted 경로를 만든다. accepted를 seed하거나 script로 policy completed를 직접 설정하지 않는다.
- [x] 종료 지점은 자료 사용 범위 채택이다. M1 completed가 없어야 한다. 다른 마일스톤 배정 0, 실제 Documents/Atlas 신규 요청 0을 검증한다.
- [x] `.venv/bin/python -m pytest tests/codex_native/test_execution_vertical_slice.py -q` 및 위 4개 작업의 관련 회귀를 실행한다. 프로세스 재시작 전후 이벤트/hash/호스트 호출 수를 비교한다.
- [x] UI 관찰 결과와 원장 이벤트를 대조해 저장/화면 시간을 기록한다. evidence manifest에 코드 revision, 테스트 명령, 합성/실제 구분, 알려진 한계를 남긴다.
- [ ] 실제 모델 소규모 확인은 별도 승인된 개발 검증 범위에서만 실행하고 모델 설정/입력/발언/판정을 보존한다. 미실행이면 합성 한 단계 동작 수락이라고만 보고한다.
- [x] 첫 단계가 통과해도 아래 후속 단위는 미완료로 유지한다. 실행 코드·배포·브라우저·연구 품질 검증 결과를 분리해 보고한다.

## 전체 누락 방지 추적과 다음 구현 단위

| 단위 | 감사 연결 | 산출물/수락 기준 |
| --- | --- | --- |
| A: 위 Task1–5 | G01, G02, G03, G09, G10 일부; DOC03–06/09–10/17–20/25–27 일부 | 한 단계 훅·실패·재개·UI. 전체 완료 우회 폐쇄는 C의 모든 진입점 검수까지 열어둠 |
| B: 외부 adapter 공통 연결 | G05, G07, G08; DOC17–24 | Documents import/A1/E 각각 인증·receipt 유지, 소비자 이벤트 선보존/미배정/분배, 지연·중복·유실·partial·stop 수락 |
| C: 그래프/루프와 M1 전체 gate | G01, G04, G05, G06, G07, G08, G11, G15, G16; DOC01–08/11–13/20–23/29–30 | 의존 영향·후속 배정·필수 단계/적용 제외·마일스톤 경계; 원본 재사용 시 실패/재개 결함 제거 |
| D: 모델·목적별 결과 패키지 | G12, G13; DOC02/14–16 | 작업별 모델/추론 snapshot, 연구·조사·계획 목적별 검사, JSON/Markdown·Presentation 역추적 |
| E: 종단·품질·운영 수락 | G14 및 나머지 전체; DOC26–30 | 새 프로젝트 무인 M1, 실패/되돌림/재시작 UI, 실제 모델/근거 품질, 단일/다중 비교, 운영 활성화 별도 |

B–E는 독립된 후속 구현 단위이며 이 문서가 세부 구현까지 작성/완료했다고 보지 않는다. 각 단위 착수 전에 별도 작은 계획에 실제 파일·테스트·계약을 고정한다. 감사 요구를 삭제하거나 생략하지 않고 이 표의 열린 항목으로 추적한다.

## 2026-09-18 실행 결과

첫 단계 구현과 합성 통합/UI 수락을 수행했다. [검증 기록](../../evaluations/2026-09-18-pilot-lifecycle-first-slice.md)을 따른다. 실모델 시험·운영 연결은 미실행이며 B–E는 아직 미완료다. begin의 inline object 고정과 별도 structured host adapter 추가 등 구현 판단도 해당 기록에 남겼다.

추가 판단: 기존 UI의 새 정적 파일404를 해소하기 위해8771 읽기 UI 프로세스만 재시작했다. 외부 서비스·연구 실행·기존 상태는 변경하지 않았다. 기존 UI의 코드/파일 불일치를 방치하지 않기 위한 예외이며 실제 새 연구 배포 수락은 아니다.
