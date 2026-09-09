# 데이터 계약과 호환성

[설계 목차](../2026-09-09-research-governance-design.md) · 이 문서의 해당 기준만 읽고, 다른 항목은 필요한 경우에만 참조한다.

## 4. 공통 데이터 계약

모든 기록은 schema_version=1, workflow_version=research-graph-v1, project_id, id, event/producer 식별자와 content_origin(real|synthetic|mixed)을 가진다. content_origin과 provenance_status(declared_only|host_observed)는 별개다. host_observed는 관측 증거 참조가 있을 때만 사용하며 서명 인증을 뜻하지 않는다.

| 객체 | 필수 내용 | 불변 조건 |
|---|---|---|
| SnapshotRef | project_id, head_id, artifact_id, sha256 | 같은 id의 다른 bytes를 수락하지 않음 |
| Issue | origin(milestone,node,attempt,local_issue_id), question, category, target_refs, severity, blocking_scope, resolution_condition, owner_assignment_id | 동일 프로젝트 전역 ID; blocking_scope는 노드/인계/최종화 대상 목록 |
| IssueEvent | issue_id, from_status, to_status, actor_assignment_id, rationale, verification_refs, successor_ids | 전이 순서·독립 확인·현재 binding 검사 |
| Verification | issue_ids, method, question, input_refs, acceptance_rule, owner_assignment_id, budget_ref | 수행 전 기준 고정, 새 기준은 새 revision |
| VerificationResult | verification_id, output_refs, outcome(supported|refuted|inconclusive|failed), checked_scope, limitations | 작업 완료와 과학적 지지를 분리 |
| Position | assignment_id, session_id, input_binding, issue_id, stance, rationale, evidence_refs, changed_from, change_kind | 공개된 동일 snapshot, 변경 원인과 실제 참조 |
| Decision | issue_ids, position_refs, claim_dispositions, rationale_links, dissent, next_action, gate_result | 각 결론이 발언·검증에 연결; 조정자 대필 금지 |
| Handoff | from/to_milestone, source_head, artifact_refs, unresolved_issue_ids, transfer_proposals, limitations, acceptance_ref | 발행과 수신 수락 분리; 자동 실행 없음 |
| Dependency | from_ref, to_ref, relation(supports|derived_from|tests|reports), origin_group_id | 순환·불명 대상 거부; unknown 원천을 독립으로 계산하지 않음 |
| ApprovalBinding | existing_receipt_ref, scope_refs, binding, validity | 기존 승인 권한 유지; 변경 영향 발생 시 재검토 |

모든 dict payload는 객체별 닫힌 필드 계약과 enum을 A01에서 고정한다. ID는 UUID 기반이며 가져온 M1 issue는 source_project/head/session/local_id 매핑표로 안정적으로 대응한다. 역사적 참조는 현재 최신 객체로 자동 치환하지 않는다.

## 8. 호환성과 파일 경계

신규 코드: researchclaw/core/research_graph/ (공통), m2/ 및 m3/ 어댑터는 이 패키지 아래에 둔다. CLI는 researchclaw-codex research … 하위로 분리한다. 기존 m1 … 명령과 숫자 단계 명령을 재해석하지 않는다.

신규 프로젝트 저장 경로는 별도 root의 .researchclaw/research_graph이며 research-graph-v1만 허용한다. M1 가져오기는 source_root/source_head→비어 있는 target_root로 복사·검증한다. 현재 M1 store는 경로·버전 상수에 결합돼 있으므로 그대로 호출해 새 상태를 쓰지 않는다. 순수 저장 공통부 추출은 기존 회귀를 먼저 고정한 별도 작업 A02에서만 한다. 신규 프로젝트는 단일 authoritative HEAD를 사용한다.

가져오기는 모든 reachable commit과 참조 객체를 검증하고 복사한 뒤 한 번 공개한다. source는 불변, 실패 target은 완료로 공개하지 않는다. 과거 M1 r1의 open 쟁점을 r2의 새 쟁점 없음으로 해소하지 않는다. 과거 실행 출처는 관측되지 않은 내용을 추정하지 않는다. legacy 숫자 단계는 상태 이전 없이 명시된 증거 manifest 어댑터로만 연결한다.

CLI 공통 규칙: 순수 projection은 JSON만 반환한다. 변경 명령은 --submission, --expected-head, --command-id를 받고 하나의 atomic receipt를 반환한다. 추가 네트워크·실험 실행·게시 side effect는 없다. 개별 작업의 함수 호출 계약을 계획에 고정한다.
