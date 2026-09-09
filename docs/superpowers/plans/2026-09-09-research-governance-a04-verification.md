# A04 쟁점 상태 전이 검증

상태: 완료 · 구현9b634d3, 검토 보완d03c7c3. 범위는 A04 하나이며 A05 검증 작업 생성·B02 배정 생성·UI는 포함하지 않는다.

## 기준선

`pytest tests/codex_native/research_graph/test_contracts.py tests/codex_native/research_graph/test_store.py -q`: 108 passed, 0.35초. 기준12560a6의 기존 격리 worktree를 사용한다.

## 수용 기준

- 이관은 해소가 아니며 수신 담당·검증 작업·수락 기록이 일치해야 한다.
- 이미 등록된 검증 결과와 독립 확인자 없이 해소할 수 없다.
- 새 충돌 근거로 재개하고 과거 쟁점/이벤트/원문을 보존한다.
- 임의 ID·다른 쟁점/프로젝트·미공개/불명 HEAD·오래된 근거는 진행 근거가 되지 않는다.
- 가져온 과거 상태와 새 정책의 재검토 상태를 구분한다.

실제 연구 판단을 수행하거나 쟁점을 해소했다고 주장하지 않는다. 이번에는 상태 전이 정책과 등록 기록의 연결을 검증한다.

## 결과

- 순수 `propose_issue_event`와 고정 `issue.event` dispatcher 구현. Issue 원문은 불변이며 IssueEvent를 추가하고 현재 상태를 별도로 투영한다.
- 합성 fixture에서 M1→M2 이관 후 `transferred` 유지, 검증 없는 해소 거부와 HEAD 보존을 확인했다. 등록된 수신 수락·담당·검증 작업이 모두 일치해야 이관된다.
- 독립 확인자와 해당 판정 조건을 확인한 supported 결과가 있어야 해소된다. 해소 후 새 반박 결과/출력 내용으로 재개한다.
- 독립 검토가 찾은 기존 반박의 ID만 바꿔 재개하는 문제를 수정했다. 결과 ID 변경 및 출력 메타데이터 ID 변경 두 거부 회귀와 정상 재개를 재검토했다. 남은 지적 없음(재검토3 passed,24 deselected).
- RED: 최초13개 기능 부재 실패. 검토 보완 RED는2 failed,25 passed. 보완 후 집중 검사27 passed,1.81초.
- 최종 영향 범위 검사: `.venv/bin/python -m pytest tests/codex_native/research_graph -q` → **179 passed in 2.89s**.
- 가져온 실제 프로젝트76개 파일의 SHA256·mtime와 HEAD `1196a857f7dff7f5ecbeca51d91011a5ef81445a56ce8eb101faacfc54592cac` 불변 확인.

## 범위와 후속

A04는 등록 기록의 상태 전이 정책 검사다. 입력 생성 API는 A05/B02에서 구현하며 누락 입력은 거부한다. 새 출력 내용 검사는 의미적·과학적 새로움을 인증하지 않는다. 같은 옛 자료의 재해석만으로 재개하는 확장 계약은 아직 없으므로 거부한다. 구조 검사 통과를 실제 연구 검증 완료로 표시하지 않는다.

다음 작업은 [A05 검증 작업과 결과 등록](research-governance/tasks/A05.md)이다. 이번 범위에는 신규 CLI/UI와 실제 연구·실험 수행이 없다.
