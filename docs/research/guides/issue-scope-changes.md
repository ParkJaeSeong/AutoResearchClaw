# 검토를 거친 쟁점 차단 범위 변경

현재 지원 범위는 **M1 questions 차단만 제거하고 review·M1→M2 인계 차단을 보존하는 변경**이다. 쟁점 본문·중요도·해소 조건·상태를 수정하지 않는다. corpus 승인이나 실행 권한을 생성하지 않는다.

1. `issue.impact.record`로 현재 쟁점과 정식 단계 버전에 연결한 영향 분류를 등록한다.
2. `issue.scope.propose`에 `impact_refs`, `producer_id`, `rationale`을 제공한다. 런타임이 원래 범위와 보호할 범위를 계산한다. 호출자가 임의의 제거 범위를 지정할 수 없다.
3. 변경안 참조를 `input_binding`으로 고정하고 `node=issue_scope`, `attempt=변경안 ID`인 native council을 준비한다. 작성자는 변경안 작성자와 같고, domain·methodology·critical 검토자는 작성자와 서로 다른 actor다. 해당 변경의 모든 쟁점을 협의 입력에 포함한다.
4. 독립 initial → 공개 response → final을 모두 제출한다. 최종 의견은 모두 `ready`여야 한다. `ready_with_limits`, `revise`, `defer`, 미완료 라운드, 신규 쟁점 제안 또는 최종 반대 입장은 적용을 막는다. 추가 조건을 텍스트에서 임의로 충족 처리하지 않는다.
5. `issue.scope.apply`에 `proposal_ref`, `council_id`를 제공한다. 정확한 현재 입력, native 생성 기록, 배정·라운드·최종 결과를 검증한 뒤 변경을 기록한다.

모든 변경 명령은 기존 `research apply --expected-head … --command-id … --payload …` 경로를 사용한다. 같은 요청의 재시도는 같은 command-id를 유지한다.

진행 판단은 원래 범위를 보존한 채 유효한 변경을 적용한다. 해당 쟁점의 상태·영향 분류 또는 질문 개정이 바뀌면 원래 범위로 돌아간다. 과거 HEAD에서는 당시 범위를 보여준다. 새 검색·선정 개정 자체는 기존 질문 변경을 무효화하지 않는다.

native 기록은 저장된 책임·검토 절차를 검증하는 장치다. actor·호스트·모델의 선언만으로 외부 신원을 인증하거나 과학적 사실을 증명하지 않는다. 실제 연구에서는 원응답과 공개 순서를 별도로 대조한다.
