# 공통 연구 운영 A01–A03 구현 검증

상태: A01–A03 첫 구현 묶음 완료·독립 검토 승인. 전체35개 작업 완료가 아니다.
개발 위치: `.worktrees/m1-research-graph`, `feature/m1-research-graph`. 기준 커밋 `df36f08`.

## 범위

A01 공통 기록 계약, A02 기존 M1 보존을 전제로 한 저장 공통부/신규 버전, A03 별도 root로 명시적인 M1 기록 가져오기. 실험 실행·M2/M3 UI·과거 council 재개·A04 이후 쟁점 처리 기능은 이번 묶음에 포함하지 않는다.

## 기준선과 실제 원본

`.venv/bin/python -m pytest tests/codex_native/m1/test_store.py tests/codex_native/m1/test_project.py -q`: **60 passed, 0.67초**. 이전 전체 저장소 기준선의 중단 한계는 유지하며 전체 통과라고 주장하지 않는다.

실제 M1 검토 사례는 합성 자료를 사용한 실제 호스트 발언이다. source HEAD는 `9706b83262c13267ed212bf7dcf5e2fa1e4caff175541fb760b7cd73d8d75755`. 회차11개·자료 객체40개·검토 session2개·열린 쟁점6개가 있다. r1은 결정됨, r2는 최초 의견3개를 공개하고 의견 교환을 기다린다. r2의 새 쟁점0개는 r1의6개 해소가 아니다.

가져오기 전에 모든 원본 파일의 SHA256·mtime·mode와 HEAD를 저장했다. 완료 후 동일성을 대조한다. 원문을 수정해 신규 schema에 맞추지 않으며, 새 ID 매핑과 변환 한계를 별도 기록한다.

## 판정 원칙

순수 schema 통과는 실제 출처 확인·쟁점 해소·M1 완료가 아니다. 가져오기는 과거 기록 보존이며 새 운영 정책 승인이나 심사 통과를 생성하지 않는다. 저장/복구 검사와 실제 자료 복사 확인을 구분해 결과를 추가한다.

## A01 기록 계약 구현

구현 커밋 `d82bce2`. Issue, IssueEvent, Verification, VerificationResult, Position, Decision, Handoff, Dependency, SnapshotRef, ApprovalBinding 총10종의 닫힌 계약과 합성 예제를 추가했다. 필수 버전·정확한 참조·출처 관측·이관 수락 필드를 검사한다. 미배정 쟁점은 owner=null로 명시하며 소유자를 추정하지 않는다. attempt는 회차 표시 번호가 아닌 정확한 UUID 참조다.

신규90개 검사와 기존 계약 검사를 합쳐 구현자 **107 passed**. 조정자가 신규 계약 검사 **90 passed, 0.04초**를 재확인했다. 원본 M1 파일85개와 HEAD 동일성도 확인했다. 독립 검토 승인. 검토자가 신규90개 검사를 재실행하고 예제 경로에 잘못된 값4,864개를 대입해 예외 없이 오류 tuple을 반환함을 확인했다.

## A02 저장 기반 구현·검토 승인

구현 `599dcd3`. 공유 모듈은 바이트·경로·fsync 기반만 추출하고 기존 M1 경로·버전·오류·검사 지점을 유지했다. 신규 저장소는 별도 root의 `.researchclaw/research_graph`에 기록한다. `initialize_record`는 준비된 전체 state/event/objects를 하나의 genesis로 공개하며 실패 staging은 완료로 취급하지 않는다. 동일 요청은 원래 receipt, 다른 payload는 conflict다.

공통 registry는 등록되지 않은 operation을 거부한다. `research init/inspect`를 추가했으며 실행 기능이나 임의 state 수정 CLI는 없다. init 기본 예산은 max_returns3/max_verification_runs10, 명시 옵션으로 변경 가능하며 비용 미관측은 null이다.

신규·기존 M1 저장/프로젝트/CLI·기존 Codex CLI 관련 **299 passed, 86.95초**. 별도 CLI 프로세스에서 신규 init·inspect·동일 init 재시도 결과가 일치함을 조정자가 확인했다. 원본 M1 파일85개·HEAD 보존도 확인했다. 독립 검토 승인. 검토자가 신규 저장/CLI17개 검사를 재실행해 통과했다.

독립 검토의 선택적 보완에 따라 조정자가 두 회귀 검사를 추가했다: 이후 HEAD가 생긴 뒤 dispatcher 재시도에서 handler 재호출 없음, genesis 이름 변경 뒤 부모 디렉터리 fsync 실패의 재시도. 구현 변경 없이 저장 검사18개가 통과했다(0.46초).

## A03 가져오기 구현·검토 승인

구현 `86c3ffa`. `research import-m1 SOURCE TARGET --source-head HASH --command-id ID --json`을 추가했다. 선택한 원본 HEAD의 이력·자료만 검증해 별도 target genesis로 공개한다. 원본과 대상 경로 중첩·비어 있지 않은 대상·불명 원본 HEAD·손상된 자료를 거부한다. 같은 요청 재시도는 동일 receipt를 유지한다.

과거 쟁점은 session별 안정 UUID로 매핑하고 source_status와 pending_policy_revalidation을 별도로 둔다. native IssueEvent나 활성 council을 생성하지 않는다. 원래 검토 회차와 정확한 가설 revision의 JSON 위치를 연결하고 미배정 담당자는 null로 남긴다. 기존 research origin은 real로 대응하고 원래 값도 보관한다. 가져오기/조회 CLI는 원문·비공개 자료 참조가 없는 요약만 출력한다.

대상 연결 보완 전 넓은 관련 회귀 **320 passed, 87.55초**. 마지막 보완 후 집중21개, 신규 그래프+M1 저장/프로젝트/조회 영향 검사 **206 passed, 9.67초**. 검사 범위는 중복되며 합산하지 않는다. 독립 검토에서 아래 P2 보완을 요구했고 수정 뒤 승인했다.

## 실제 자료 수용

[실제 가져오기 결과](../acceptance/research-graph-a03/live-import.json). 원본 HEAD `9706b83262c13267ed212bf7dcf5e2fa1e4caff175541fb760b7cd73d8d75755`에서 새 HEAD `1196a857f7dff7f5ecbeca51d91011a5ef81445a56ce8eb101faacfc54592cac`로 가져왔다.

- 원본 reachable commit33개·자료 객체40개의 bytes가 복사본과 동일하다. 새 객체73개는 원본 자료40개와 원본 commit JSON33개다.
- 열린 쟁점6개가 모두 open/pending_policy_revalidation이며 각 target_ref가 정확한 가설 원문을 가리킨다.
- 새 native council0개·IssueEvent0개. 과거 의견을 새로운 합의나 해소로 생성하지 않았다.
- 별도 CLI import 재시도와 inspect의 head_id 일치. 공개 응답에 raw state/events/objects가 없다.
- 원본 파일85개의 bytes/hash/mtime/mode 및 원본 HEAD 보존.

새 target은 `.superpowers/sdd/2026-09-09-research-governance-core/imported-live-project`이며 개발 수용 자료다. UI 연결은 기존 M1 화면을 유지하고 신규 전체 UI(E01+)는 아직 구현하지 않았다. 합성 자료로 실제 호스트 발언을 검토했던 기록을 가져온 것이며 실제 연구 결과·M1 완료·M2 실행을 의미하지 않는다.

## A03 독립 검토 보완과 최종 검사

검토에서 잘못된 disclosed_responses/disclosed_final_positions를 legacy helper가 빈 목록으로 처리할 수 있는 P2를 발견했다. 실패16개로 재현 후 `663fd12`에서 공개 목록·멤버·내부 쟁점/응답/처리 목록을 먼저 검증하도록 보완했다. 정상 입력의 출력은 그대로다.

수정 후 구현자 신규 그래프152개·migration/CLI/M1 views61개 검사 통과. 조정자가 최종 `.venv/bin/python -m pytest tests/codex_native/research_graph -q`를 실행해 **152 passed, 1.12초**를 재확인했다. 원래 실제 가져오기 요청을 재실행해 target HEAD가 동일하고 source 파일85개와 HEAD가 보존됐음을 재확인했다. 최종 scoped 재검토 승인. 추가 지적 없음.

최종 모듈 간 통합 검토는 새 결함 없이 A03 P2 해소를 조건으로 승인했고, 해당 조건은 독립 재검토로 충족됐다. 도구 thread 수 제한으로 사용 가능한 A02 독립 검토자를 재사용했다. 구현자 자기 검토로 대신하지 않았다. 선택적 저장 회귀2개도 함께 포함했다. 원래 main은 변경하지 않았으며 이 작업은 외부 배포·실험 실행·신규 전체 UI 완료를 포함하지 않는다.
