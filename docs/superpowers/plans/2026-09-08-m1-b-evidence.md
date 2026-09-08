# M1 B — Evidence and Durable State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 신규 M1 프로젝트와 버전별 자료·승인·근거를 지속적으로 보존한다.

**Architecture:** 새 저장소가 HEAD로 연결된 불변 커밋을 읽고, 패킷이 지정한 작업 원고만 검증·등록한다. 기존 내용 검증기는 상태 전환 없이 사용한다.

**Tech Stack:** Python >=3.11, pathlib/hashlib/json, 기존 경로 검증·잠금·원자 저장, pytest/PyYAML.

**Spec:** [총괄 계획](2026-09-08-m1-transition.md). 선행: A의 UI·호스트·계약 완료와 기존 기준선 분석 확보. 중단된 전체 회귀는 후속 통합 검증에서 다시 확인한다.

## Global Constraints

총괄 제약 전체 적용. 기존 `ProjectState`와 단계 승인 경로는 변경하지 않는다. 조회 중 정상화·복구를 하지 않는다. 실패한 등록은 가시적인 반쪽 커밋을 남기지 않는다.

## Task 05: 새 프로젝트·불변 저장

**Files:** Create `researchclaw/core/m1/store.py`, `researchclaw/core/m1/project.py`, `researchclaw/codex/m1_cli.py`, `tests/codex_native/m1/test_store.py`, `tests/codex_native/m1/test_project.py`; Modify `researchclaw/codex/cli.py`의 parser/dispatch 진입 연결.

**Interfaces:** `init_project(root: Path, *, topic: str, profile: str, max_returns: int, content_origin: str = 'research') -> dict`; `read_head(root: Path) -> dict`; `commit_record(root: Path, *, expected_head: str, command_id: str, state: dict, event: dict, objects: dict[str, bytes]) -> dict`. 반환 HEAD는 `id,state,events,objects`를 가진다. `m1 init ROOT --topic ... --profile materials_ai --max-returns 2 --json`, `m1 status ROOT --json`. 합성 검사 프로젝트는 선택 인자 `--content-origin synthetic`으로 명시한다.

- [x] 실제 초기화의 legacy 거부·빈 루트·정상 재열기·조회 무변경 검사를 작성한다.

```python
import pytest
from researchclaw.core.m1.project import init_project
from researchclaw.core.m1.store import read_head

def test_legacy_state_is_not_migrated(tmp_path):
    meta = tmp_path / '.researchclaw'
    meta.mkdir()
    old = meta / 'state.json'
    old.write_text('{"legacy":true}')
    before = old.read_bytes()
    with pytest.raises(ValueError, match='m1_legacy_project_requires_explicit_migration'):
        init_project(tmp_path, topic='fixture', profile='materials_ai', max_returns=2)
    assert old.read_bytes() == before
    assert not (meta / 'm1').exists()
```

- [x] `python -m pytest tests/codex_native/m1/test_store.py tests/codex_native/m1/test_project.py -q`로 기능 부재에 따른 실패를 확인한다.
- [x] M1 초기화와 커밋 발행을 다음 순서로 구현한다.

```text
validate root and closed record schemas
acquire existing project_transaction(root) after creating owned metadata
reload HEAD
if command_id already committed: verify identical payload; sync publication; return original receipt
reject stale expected_head
write immutable objects; verify size/hash
write complete new commit in unpublished owned temporary directory
fsync files; publish complete commit directory; fsync parent
atomic-write HEAD referencing the complete commit; fsync store and publication parent directories
return committed receipt
```

- [x] 같은 command_id·같은 내용은 같은 결과를 반환한다. 같은 ID·다른 내용은 `m1_command_conflict`, 다른 HEAD는 `m1_head_conflict`로 거부한다. 미발행 임시 파일은 UI에서 읽지 않는다. 원문 위치가 symlink로 대체된 입력은 거부한다.
- [x] HEAD 교체 전후 장애, 동시 쓰기, 상대 루트·symlink 부모 루트, 디스크 부족을 검사한다. 손상된 HEAD를 임의로 복구하지 않고 `m1_store_corrupt`로 멈춘다.
- [x] 기존 `tests/codex_native/test_project.py`, `test_state.py`, `test_cli.py`를 실행한다. 신·구 상태가 섞이지 않는 결과를 기록하고 커밋한다.

**User check:** 신규 M1을 닫았다 열어도 같은 기록이 나오고 기존 연구는 바뀌지 않는다.

## Task 06: 작업 패킷·산출물 등록·재개

**Files:** Create `researchclaw/core/m1/packets.py`, `artifacts.py`, `tests/codex_native/m1/test_packets.py`, `test_artifacts.py`; Modify `m1_cli.py`.

**Interfaces:** `prepare_node(root: Path, node_id: str, *, command_id: str) -> dict`; `validate_outputs(packet: dict, files: dict[str, bytes]) -> tuple[dict, ...]`; `register_outputs(root: Path, *, packet_id: str, submission: dict, command_id: str) -> dict`; `resume_project(root: Path) -> dict`(project.py에 추가, 읽기 전용). CLI: `m1 node prepare ROOT --node NODE --command-id ID --json`, `m1 node register ROOT --packet ID --submission PATH --command-id ID --json`, `m1 resume ROOT --json`.

- [x] 패킷에는 attempt ID, 입력 객체, 입력 결합, 출력 allowlist, 역할·도구 범위, 구조 검사·협의 필요 조건을 포함한다.
- [x] 외부·절대·미선언 출력, 입력 변경, 과거 패킷 재사용을 거부하는 검사를 먼저 쓴다.

```python
from researchclaw.core.m1.artifacts import validate_outputs
def test_undeclared_output_is_rejected():
    packet = {'schema_version':1, 'node_id':'scope',
              'allowed_outputs':['scope/goal.md']}
    issues = validate_outputs(packet, {'../escape.txt':b'x'})
    assert any(x['code'] == 'm1_undeclared_output' for x in issues)
```

- [x] `python -m pytest tests/codex_native/m1/test_packets.py tests/codex_native/m1/test_artifacts.py -q`로 실패 확인.
- [x] 출력 allowlist와 입력 결합 확인 후 task 05 commit_record로 한 번 등록한다. 등록 뒤 상태는 협의/확인 필요 시 `review_pending`; 단순 파일 유효성으로 다음 노드를 완료하지 않는다.

```python
def validate_outputs(packet, files):
    allowed = set(packet['allowed_outputs'])
    unexpected = set(files) - allowed
    if unexpected:
        return ({'code':'m1_undeclared_output', 'paths':sorted(unexpected)},)
    return validate_declared_contents(packet, files)
```

`validate_declared_contents(packet, files) -> tuple[dict,...]`는 같은 artifacts.py에 정의한다. 알려진 node에 대해 필수 파일·UTF-8·JSON/YAML 형식 검사를 수행하고 unknown node는 거부한다. 문헌·종합·가설 내용 검사는 각각 task 07~09가 연결한다.

- [x] `resume_project`는 현재 수행 가능 작업·대기 이유·최신 attempt를 반환한다. head와 모든 파일의 바이트/mtime 전후 대조로 조회 무변경 확인.
- [x] 두 번 등록·프로세스 중단 후 동일 명령 재시도 검사와 기존 `test_task_packets.py`를 실행하고 커밋한다.

**User check:** “현재 할 일·왜 대기 중인지·어떤 자료를 읽어야 하는지”가 CLI에 표시된다.

## Task 07: 문헌 승인과 추출

**Files:** Create `researchclaw/core/m1/literature.py`, `approvals.py`, `tests/codex_native/m1/test_literature.py`, `test_approvals.py`, `helpers.py`; Modify artifacts.py와 m1_cli.py.

**Interfaces:** `validate_literature(node_id: str, files: dict[str, bytes], inputs: dict[str, bytes]) -> tuple[dict,...]`; `record_corpus_approval(root: Path, *, corpus_binding: str, decision: str, note: str, command_id: str) -> dict`; `approval_covers(record: dict, corpus_binding: str) -> bool`. CLI `m1 corpus decide ROOT --binding HASH --decision approve|reject --note TEXT --command-id ID --json`.

- [x] 검색 기록, 후보·선별 목록의 출처와 사유, 승인 결합·추출 조건을 검사한다.

```python
from researchclaw.core.m1.approvals import approval_covers
def test_old_approval_does_not_cover_changed_corpus():
    record = {'decision':'approve','corpus_binding':'a'*64}
    assert approval_covers(record, 'a'*64)
    assert not approval_covers(record, 'b'*64)
    assert not approval_covers({'decision':'reject','corpus_binding':'a'*64}, 'a'*64)
```

- [x] `python -m pytest tests/codex_native/m1/test_literature.py tests/codex_native/m1/test_approvals.py -q` 초기 실패 확인.
- [x] 핵심 결합 비교는 아래처럼 만들고 상위 등록 계층에서 사용자 결정·등록 스키마·현재 corpus를 확인한다.

```python
def approval_covers(record, corpus_binding):
    return (record.get('decision') == 'approve'
            and record.get('corpus_binding') == corpus_binding)
```

- [x] 기존 `validate_extraction_shortlist`/`validate_knowledge_extraction`의 실제 signature를 확인해 내용 검사만 호출한다. 기존 stage validate/approve 호출로 새 프로젝트를 전진시키지 않는다. 접근 수준·원문 locator·원문 미접근 제한을 유지한다.
- [x] 테스트 helpers.py에 `build_evidence_case(root: Path) -> dict`를 정의한다. 테스트 전용으로 init_project(content_origin='synthetic')/commit_record를 이용해 scope~screen의 합성 checkpoint를 주입한 뒤 문헌 승인·추출 공개 API를 실행한다. `root,head_id,artifact_refs,corpus_binding`를 반환한다. 앞 단계 협의는 작업 17에서 연결되므로 이 helper를 전체 공개 경로 검사라고 부르지 않는다. 제품에 seed 또는 승인 우회 명령을 추가하지 않는다.
- [x] 합성 checkpoint의 실행 출처는 declared_only로 두고 자료에 '합성 검사 자료'를 표시한다. 실사용 품질 증거에 합산하지 않는다.
- [x] 미승인 추출, 반려 후 수동적 재개, 문헌 집합 변경, 같은 집합의 승인 재사용 범위를 검사한다. 새로운 binding에는 명시적 사용자 판단이 필요하다.
- [x] 기존 knowledge/approval 회귀를 실행하고 문헌 선택→사용자 결정→추출 연결을 보여준 뒤 커밋한다.

**User check:** 선별 사유와 승인한 자료 집합이 보이며, 자료를 바꾸면 새 승인 필요 상태가 표시된다.

## Task 08: 근거 종합과 계보

**Files:** Create `researchclaw/core/m1/synthesis.py`, `tests/codex_native/m1/test_synthesis.py`; Modify artifacts.py, helpers.py.

**Interfaces:** `validate_synthesis_record(record: dict, *, known_claim_ids: set[str]) -> tuple[dict,...]`; `trace_claim(head: dict, claim_id: str) -> dict`. M1 synthesis 구조는 `claims,agreements,conflicts,gaps,limitations`; gap은 `id,question,claim_refs`, conflict는 `id,claim_refs,interpretations,open_questions`를 가진다.

- [x] 모순 근거를 없애지 않아도 유효한 기록, 모르는 주장 참조는 거부, 공백을 임의로 두 개 만들지 않는 검사를 먼저 작성한다.

```python
from researchclaw.core.m1.synthesis import validate_synthesis_record
def test_unknown_claim_in_gap_is_rejected():
    record = {'claims':[], 'agreements':[], 'conflicts':[],
              'gaps':[{'id':'G1','question':'condition?', 'claim_refs':['missing']}],
              'limitations':[]}
    issues = validate_synthesis_record(record, known_claim_ids={'C1'})
    assert any(i['code'] == 'm1_unknown_claim' for i in issues)
```

- [x] `python -m pytest tests/codex_native/m1/test_synthesis.py -q`로 기능 부재 확인.
- [x] 각 gap/conflict의 claim_refs를 등록 claim 집합에 대조한다. 참조가 없으면 그 이유가 있는 `unverified_question`으로 기록하되 이미 입증된 공백으로 표시하지 않는다. 구조상 gap 0개를 허용하고 downstream 가설·handoff가 불가능한 이유를 별도 상태로 보고한다.
- [x] `trace_claim`은 extraction 객체→선별 corpus→승인→원문 locator를 따라간다. 원문 파일이 없으면 URL·접근 수준만 제공하고 전문 확인으로 표시하지 않는다.
- [x] 기존 synthesis의 유용한 참조 검사 원리는 재사용하되 고정 섹션·공백 두 개 규칙을 신규 M1에 강제하지 않는다. 기존 함수와 테스트는 그대로 둔다.
- [x] helpers.py의 `build_evidence_case`를 합성 synthesis checkpoint까지 확장한다. 결과 artifact_refs에 synthesis를 추가하고 과거 반환 키를 유지한다. 앞 단계의 실제 완료를 조작한 사용자 프로젝트로 내보내지 않는다.
- [x] 검사·B 결과 보고·작업 커밋. 자료와 근거 계보를 CLI JSON으로 보여준다.

**User check:** 결론을 선택해 실제 근거·원문 위치로 따라가며 충돌과 접근 한계를 볼 수 있다.
