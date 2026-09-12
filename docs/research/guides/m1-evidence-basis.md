# 질문별 근거 묶음 등록 · B1

Pilot 연구 질문에 사용할 주장과 Atlas 근거를 묶어 보관한다. 각 주장에는 QA의 정확한 인용 구간, 사용 판단, 허용 용도와 한계가 연결된다. **등록은 과학적 검증이나 M1 완료가 아니다.**

## 현재 사용할 수 있는 기능

1. `research inspect ROOT --json`으로 질문 개정·외부 답변·사용 판단의 정확한 참조를 조회한다.
2. 실제 질문 하나를 선택하고, 주장별로 어떤 QA 구간을 어떤 용도로 사용할지 작성한다.
3. `research apply`로 묶음을 등록하고 `m1_evidence_bases`에서 결과와 주장별 원본 참조를 확인한다.

```sh
researchclaw-codex research apply ROOT \
  --operation m1.evidence_basis.register --payload basis.json \
  --expected-head CURRENT_HEAD --command-id UNIQUE_COMMAND --json
researchclaw-codex research inspect ROOT --json
```

`basis.json`의 입력 계약:

| 항목 | 입력 |
| --- | --- |
| question_ref | 현재 questions 개정의 ref 객체 전체 |
| question_text | 해당 개정에 실제 있는 질문 문장 |
| review_refs | 이번 주장에 사용하는 외부 사용 판단 ref 목록 |
| claims | 아래 주장 항목을 하나 이상 |
| coverage | covered, missing, decision_impact에 다룬 범위·빠진 범위·판단 영향을 각각 작성 |
| limitations | 묶음 전체의 한계 문장 목록 |
| previous_ref | 첫 등록은 null, 수정은 최신 묶음의 ref 전체 |
| revision_reason | 첫 등록은 null, 수정은 변경 이유 |
| producer_id | 실제 작성자 식별자 |

각 주장에는 `claim_id`, `statement`, `evidence_ref`, `review_ref`, `basis_kind`, `qa_excerpt`, `rationale`, `intended_use`, `limitations`를 입력한다. `basis_kind`는 Atlas 답변에 근거한 `atlas_answer` 또는 Pilot의 추론인 `pilot_inference`다. `qa_excerpt`는 해당 QA answer에 실제 포함된 구간이어야 하며, `intended_use`는 검토의 allowed_uses 중 하나와 일치해야 한다.

use/limited 판단만 지지 근거로 쓸 수 있다. 보류·제외 판단, 답변에 없는 인용, 다른 연구의 참조, 이전 QA를 새 묶음에 채택하는 요청은 거절된다. 출처 구간과 주장 사이의 논리적 타당성은 후속 에이전트 검토 대상이다.

## 변경과 조회의 의미

- 새 QA나 연구 질문 개정이 생기면 이전 묶음은 그대로 남고 `current: false`와 이유가 표시된다.
- `current: true`는 선택한 입력이 현재 버전이라는 뜻이다. 충분한 근거나 검토 완료라는 뜻이 아니다.
- `superseded: true`는 후속 묶음이 있다는 뜻이다. 실제 채택할 묶음은 현재 입력과 후속 개정 여부를 함께 확인한다.
- `review_candidates`는 같은 QA에 대한 다른 사용 판단이다. 자동 선택하거나 의견 충돌을 해결한 것으로 처리하지 않는다.
- 주장 객체는 묶음 ID와 0부터 시작하는 순번으로 저장한다. 사용자가 정한 claim_id는 객체 내용에 보존한다. 각 `claims[].ref`로 정확한 버전을 참조할 수 있다.
- 과거 HEAD를 조회하면 그 당시의 현재성·개정 상태가 보인다. 이전 답변·검토·주장 객체는 덮어쓰지 않는다.

## 남은 연결 작업

이번 B1은 등록 명령과 공개 조회까지다. 종합·가설 노드의 외부 입력 연결(B2), 실제 협의(B3), UI 작성 양식(B4), 실험 준비·인계 조건(B5), 실제 사례 적용(B6)은 별도 작업이다.

현재 복합재 연구의 세 질문에는 ‘동일 배합의 제조 두 조건 비교’가 아직 없다. 이 구현을 시험하기 위해 실제 질문을 변경하거나 기존 QA를 다른 질문에 임의로 묶지 않았다. 사례 적용 시 질문 추가·검토를 먼저 진행한다.

## 구현 확인 · 2026-09-12

관련 Python 검사 61개와 기존 UI 검사 49개가 통과했다. 실제 서버의 조회 항목을 확인했고 연구 HEAD·질문·쟁점·승인은 바꾸지 않았다. 신규 UI 양식은 아직 없으며 위 CLI와 JSON 조회로 사용할 수 있다.
