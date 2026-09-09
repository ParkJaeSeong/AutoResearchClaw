# A05 검증 작업과 결과 등록 — 검증 기록

상태: 완료 · 구현f597809 · 검토 보완4244336. 범위는 A05이며 UI·실험 수행·담당 배정 생성은 후속 작업이다.

## 수용 기준

- 방법·질문·입력·판정 조건·담당·예산 참조를 결과 등록 전에 고정한다.
- 판정 조건이 없는 실행 로그는 `acceptance_rule_missing`으로 거부한다.
- 결과를 supported/refuted/inconclusive/failed로 구분하고 확인 범위·한계를 기록한다.
- 결과 등록만으로 쟁점을 자동 해소하지 않는다. A04의 독립 해소 절차를 유지한다.
- 다른 프로젝트·잘못된 버전·근거 없는 참조와 준비 후 바뀐 입력을 거부하고 HEAD를 보존한다.
- 기존 원문·쟁점·이벤트를 보존한다.

기준선: A04 집중 검사27 passed in 1.78s. 합성 fixture 정책 검증과 실제 연구 확인을 구분한다.

## 결과

- `verification.prepare`로 방법·질문·입력·판정 조건·담당·예산 참조를 고정하고, `verification.result`로 정확한 준비 버전에 결과를 등록한다. 기존 ID를 덮어쓰지 않는다.
- 지원 방법은 source_check/logic_check/calculation/experiment/human_decision이다. 결과 supported/refuted/inconclusive/failed를 각각 저장한다.
- supported/refuted는 비어 있지 않은 출력 내용과 고정 판정 조건을 포함한 확인 범위를 요구한다. failed/inconclusive는 확인하지 못한 범위·출력을 비워둘 수 있지만 한계 설명이 필요하다.
- 합성 fixture의 공개 명령 연결: 쟁점 생성 → 검증 준비 → checking → supported 결과 등록 → 별도 독립 resolver 이벤트로 resolved. 결과 등록 자체는 쟁점 상태를 변경하지 않는다.
- failed/inconclusive 결과의 해소 시도는 거부되며 checking이 유지된다. 잘못된 참조·기존 기록 덮어쓰기·준비 후 입력 변경·담당 역할 변경도 HEAD를 보존하며 거부된다.
- 독립 검토에서 빈 출력 바이트를 지지 근거로 받아들이는 경로를 발견하고 수정했다. supported/refuted 두 회귀가 RED2실패 → GREEN2통과; 최종 A05 집중 검사28 passed in 1.41s. 재검토 spec/quality PASS, 남은 지적 없음.
- 초기 RED18 unknown_operation 실패 → GREEN18통과. 입력/담당 경계 보완 RED2실패 → GREEN26통과.
- 최종 영향 범위 검사: `.venv/bin/python -m pytest tests/codex_native/research_graph -q` → **207 passed in 4.21s**.
- 기존 실제 M1 프로젝트85개 파일과 가져온 프로젝트76개 파일의 SHA256·mtime·HEAD 모두 불변 확인.

## 범위와 후속

등록 정책과 정확한 참조 연결을 구현했다. 결과 내용의 과학적 충분성·실제 수행 여부를 이번 합성 테스트가 인증하지 않는다. 담당·예산·입출력 자료 생성 API, CLI/UI, 실제 원문 대조·계산·실험은 이번 구현에 포함하지 않는다. 기존 등록 입력이 없으면 거부한다.

정확한 호출 계약은 [검증 등록 입력 계약](../specs/research-governance/verification-inputs.md)을 따른다. 다음은 [A06 입장 변화·요약 근거 연결](research-governance/tasks/A06.md)이다.
