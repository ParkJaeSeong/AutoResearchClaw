# Pilot 공통 서비스 요청·응답과 마일스톤 자율 실행

2026-09-18. 사용자 지시: “설계를 구체화해줘. 자동실행은... 마일스톤 끝까지야!”
상태: Atlas 1~11절 검토의 B1~B5 및 단계 결과 요구를 반영한 Pilot 상세 설계안. 현재 계약 매핑과 신규 계약 제안을 구분한다. 사용자 정책 세 가지와 신규 외부 계약은 미확정이며 코드·운영 적용을 뜻하지 않는다.

## 1. 목표와 확정한 경계

외부 요청이 끝나면 원래 연구 작업으로 결과가 돌아와 현재 마일스톤 완료까지 진행한다. 정상 흐름에서 단계별 사용자 승인을 추가하지 않는다. 기존 문서 import와 A1 ask/job/QA는 서로 다른 서비스·인증·완료 통지 방식을 유지한다. Pilot 내부는 공통 요청·전달·작업 상태를 사용한다. Atlas는 서비스별 연결부로 공통 의미를 제공하며 새 프로세스나 서버 분리를 요구하는 것은 아니다.

Pilot: 목적·질문·에이전트 조정·충분성 판단·다음 작업·마일스톤 완료 판단.
Atlas: 자료 관계·지식 보유·통합 분석·확인 범위·근거 공백·결과 보존.
Documents: 이미지 해석을 포함한 문서 변환. 문서 내부 분할 전송은 이번 범위가 아니다.

## 2. 실행 범위

현재 승인된 프로젝트 목적과 마일스톤 안에서 자료 탐색/확보, Documents 의뢰, Atlas 질의/통합 분석, 전문가 검토, 추가 질문, 가설·설계 수정과 채택, 완료 검토를 자동으로 수행한다. 가설 채택은 필요한 교차 검토·근거 대조를 거치며 사용자 승인을 만들어내지 않는다.

M1 끝까지 실행한다는 것은 실제 실험·장비 제어 또는 다음 마일스톤 자동 착수를 의미하지 않는다. M1 종료 시 결과·근거·한계·다음 마일스톤 입력을 정리하고 완료 근거를 기록한 뒤 멈춘다. 종료를 위해 단계 평가를 우회하거나 부족한 필수 근거를 만들어내지 않는다.

대기는 필요한 입력/서비스 결과를 기다리는 상태다. 중단 조건은 사용자 정지, 실제 권한 부족, 사전 승인 자원 범위 초과, 결과 무결성/필수 입력 문제, 다음 마일스톤 경계다. 한 작업의 제약은 무관한 다른 작업을 막지 않는다. 권한이 필요한 부분은 구체적으로 요청하고 무응답을 승인으로 해석하지 않는다. 임의의 10분 제한·문헌 수·토론 횟수로 끝내지 않는다.

## 3. 세 계층

1. 연구 조정 계층: 전문가 요청을 취합하고 근거 공백·결정 의존성·우선순위를 판단한다. 다음 행동을 정하는 유일한 계층이다.
2. 공통 접수·전달 계층: 요청/응답을 영속 저장하고 상관관계 대조, 중복 방지, 상태 확인, 담당 작업 전달과 재시작 복구를 수행한다. 연구 의미를 독자 판정하지 않는다.
3. 서비스 연결부: Atlas import, Atlas ask, 이후 전문 도구의 실제 API/MCP·인증·상태를 다룬다. 원래 상태·오류·영수증을 보존하고 공통 상태로 투영한다.

공통 접수는 논리적으로 한 경로다. 네트워크 호출 전체를 하나씩 기다리는 전역 병목으로 만들지 않는다. 프로젝트별 판단 쓰기는 직렬화하고 외부 처리와 독립 초기 의견 생성은 병행 가능하다.

## 4. 공통 요청 봉투 v1 — Pilot 내부 규격

아래 이름은 설계 필드이며 현재 Atlas가 수용한다고 주장하지 않는다. 서비스 지원에 따라 client_context 등 기존 필드로 전달하고 나머지는 Pilot이 보존한다.

| 필드 | 내용 |
| --- | --- |
| schema_version | 공통 봉투 버전 1 |
| request_id | 재전송에도 불변인 Pilot 요청 ID |
| conversation_id / parent_request_id | 연속 질문 연결; 독립 요청은 parent null |
| project_id / milestone_id | 소속 연구와 실행 경계 |
| stage_id / work_id / attempt_id | 단계 종류, 실제 작업, 실행 시도 구분 |
| question_ref / context_revision | 질문·목적·제약의 고정 버전과 해시 |
| requester | agent_id, role_id/version, council_id/round(해당 시) |
| service / operation | 예: atlas/ask, atlas/documents.import |
| input_refs | 자료·이전 판단·미해결 쟁점의 ID/버전/해시/읽은 범위 |
| instruction / output_requirements | 실제 질의, 기대 결과·근거·확인 범위 |
| return_to | 기다리는 work_id, recipient_role, continuation_ref |
| visibility | 독립/공개 회차, 허용 수신자, 공개 조건 |
| execution_policy_ref | 승인 범위·자원·오류 복구 정책 버전 |

continuation_ref는 Pilot이 저장한 다음 작업 명세를 가리킨다. 명세는 목적, 필수 입력, 대기 조건, 역할, 출력·검수 기준, 종료/보완 조건을 가진다. 외부 응답의 실행 코드나 쉘 명령을 실행하지 않는다. Atlas의 후속 제안은 판단 입력이며 실행 권한이 아니다.

같은 요청 ID와 다른 내용은 충돌이다. 질문·자료·목적을 바꾸면 새 요청을 만들어 이전 요청과 연결한다. 시간 초과나 응답 유실만으로 새 요청 ID를 만들지 않는다.

### 4.1 외부 매핑 — B1

A1 client_context에는 pilot_project_id/question_id/issue_id/round_id/binding_ref만 문자열 또는 null로 보낸다. import는 자체 schema의 pilot_project_id/work_ref/question_ref를 따른다. 전체 봉투와 실제 송신 payload·정규화 hash를 각각 보존하며 비밀 토큰을 넣지 않는다. 통신 재시도는 동일 key/payload를 유지한다. context echo를 공개 통제나 권한 적용 증거로 취급하지 않는다.

## 5. 서비스별 계약과 응답

공통 응답은 request_id, service instance, service request/job/import 참조, 원래 상태, 공통 outcome, 불변 result_ref, 실제 읽은 범위·한계, 구조화 가능한 오류, 재조회 위치를 가진다. 기존 서비스에 없는 필드는 미지원/미확인으로 표시하며 생성된 확정 정보로 채우지 않는다.

| 항목 | Atlas 문서 import | Atlas 질의 |
| --- | --- | --- |
| 현재 접수 | document-imports + 전용 인증 | A1 jobs kind=ask + A1 인증 |
| 완료 확인 | import 이벤트와 결과 대조 | job 조회·QA 참조 |
| 원형 | import record 및 source/extraction/page 참조 | QA 원형·consulted_pages·source 참조 |
| 수신 확인 | 외부 event ACK | Pilot 내부 영속 수신/전달 기록; 가상의 외부 ACK API 없음 |

두 연결은 같은 Atlas instance인지 대조한다. A1 질의에 지정한 source 집합은 강제 필터가 아니며 반환 범위를 Pilot이 확인한다. 페이지 expected hash가 달라지고 보존본이 없으면 최신본으로 대체하지 않고 입력 준비를 보류한다. 추출 경로는 다운로드 API가 아니다.

### 5.1 접수와 원형 검증 — B2/B3

A1 key는 자료실 jobs 전체에서 유일하며 receipt operation은 jobs.submit이다. import key는 consumer별이다. Documents 변환과 Atlas import의 key·fingerprint는 별개다. 외부 key에는 서비스·operation·프로젝트를 포함해 충돌을 피한다. receipt의 instance/operation/key/fingerprint를 대조하고 공급자 fingerprint를 Pilot 봉투 hash로 대체하지 않는다.

알려진 job은 우선 조회한다. 401/403/임의404를 미접수로 해석해 재제출하지 않는다. 응답 유실 복구 시 같은 요청과 execute 부작용을 함께 대조한다. 동일 URL의 instance 교체는 자동 재바인딩하지 않는다.

source는 version/hash 및 chunk 종료(eof/next_offset=null)를 확인한다. Atlas가 읽은 범위와 Pilot이 실제 받은 원형을 구분한다. completed라도 유효 QA가 없으면 검토 준비 완료가 아니다.

## 6. 상태와 전달 확인

세 상태축을 별도 유지한다.

- 외부 처리: prepared → submitted → accepted → running → completed/partial/failed/cancelled. 응답 유실은 receipt 확인 상태이며 실패로 단정하지 않는다. 실제 서비스 상태와 투영 규칙을 함께 저장한다.
- 내부 전달: awaiting_result → result_stored → delivery_pending → delivered → received/needs_input/not_applicable.
- 연구 작업: waiting → ready → running → review_required → completed/needs_more_evidence/blocked/superseded.

외부 completed는 연구 completed가 아니다. ACK는 수신 확인이며 검토 완료가 아니다. failed의 진단 result만으로 과학 토론을 시작하지 않는다. partial은 입력 적합성을 검토하고 영향받는 용도를 제한한다.

수신자 에이전트 프로세스가 종료됐어도 작업·역할·공통 입력·이전 의견·새 결과를 복원해 재개한다. 원래 PID나 대화창 존재에 의존하지 않는다. 에이전트가 응답했지만 필수 입력을 못 읽었다면 received가 아니라 needs_input을 기록한다.

### 6.1 상태 투영과 consumer별 수신 — B3

import 원래 phase(accepted/waiting_conversion/fetching/organizing/needs_attention/terminal)와 outcome, A1 interrupted/dispatch 진단을 보존한다. queued는 실행 예약 보증이 아니며 scheduled=false/dispatch_error/고아 running을 정상 대기로 숨기지 않는다.

공유 consumer 이벤트는 중앙 수신 원장에 모든 이벤트를 영속 저장한 뒤 프로젝트별로 분배한다. 비대상 이벤트를 버리고 공유 cursor만 전진시키지 않는다. 빈 events와 유지된 cursor는 정상 tail이다. 외부 ACK는 수신 원형과 전달 의무를 복구할 수 있게 저장한 뒤 수행한다. ACK 후 중단돼도 전달 작업을 복원한다.

result_stored는 검증된 원형의 내구성 저장, delivered는 대상 대기함 등록, received는 정확한 역할·회차·input revision 수신이다. 입력 제공/도구 기록을 남기며 모델의 읽었다는 진술만으로 전체 원문 접근을 인증하지 않는다.

## 7. 문헌 루프와 종합

한 문서 결과 도착 → 개별 근거 검토. 관련 자료가 준비되면 조정자가 질문에 맞춘 Atlas 통합 질의를 작성한다. 동일 논문의 본문·보충자료 연결/정리는 Atlas가 수행하며 독립 실증 두 건으로 세지 않는다.

Atlas 통합 답변 도착 → 출처 범위/원형 고정 → 전문가 종합 토론 → 조정자 결정.

결정 분기:
- 충분: 가설·설계 초안/수정/채택 등 후속 작업 등록.
- Pilot 보유/Atlas 미보유: 기존 자료 전달.
- 해석 부족: 추가 Atlas 질의.
- 변환 문제: Documents 보완.
- 새 근거 필요: 외부 탐색·확보.
- 확인 불가: 영향받는 주장·용도를 제한하고 다른 가능 작업 진행.

개별 전문가의 추가 요청은 조정자가 취합한다. 동일 질문/자료/목적은 중복 요청하지 않는다. 질문만 비슷한 서로 다른 조건은 함부로 합치지 않는다. 재질의는 무엇이 달라졌고 어떤 판단을 바꿀지 있어야 한다. 여러 결과를 기다리는 조건은 work의 dependencies에 필수/선택/대체 가능 조건으로 기록한다. 필수 쟁점이 미충족인 종합은 공백 정리로 제한하며 결론 채택을 뜻하지 않는다.

## 8. 에이전트 규칙

AGENTS.md와 docs/research/prompts/m1/protocol.md, task-packet.md를 따른다. 페르소나·마일스톤/단계 목적·이전 자료·변경분·출력/검수 기준을 명시한다. 동일 고정 공통 입력으로 독립 초기 의견 후 전원 제출 시 공개한다. 회차별 발언·도구 사용·근거·원응답을 보존한다.

독립 회차 중 새 답변은 개인 대기함에 저장한다. 현재 회차의 공통 입력에 조용히 끼워 넣지 않는다. 공통 근거에 영향을 주면 새 입력 revision을 만들고 영향을 받는 초기 검토를 다시 준비한다. 조정자 전달 권한이 독립 공개 규칙을 해제하지 않는다.

사실/문헌 보고/Atlas 해석/자신의 추론/제안을 구분한다. 동의는 증거가 아니고 자기평가는 독립 검토가 아니다. 핵심 가설·설계·마일스톤 완료는 의미 검토와 명시적 채택 이유를 갖는다.

공개 전 의견·가설을 공유 ask/위키 쓰기 입력에 넣지 않는다. 개인 inbox만으로 독립성을 보장하지 않는다. 독립 회차에는 고정 원형 패키지로 도구 접근을 제한하고 실제 제공 범위를 기록한다. Atlas project/auth가 역할별 비공개를 강제한다고 가정하지 않는다(B5).

## 9. 저장·복구·동시성

프로젝트 아래 공통 요청·전달 원장과 불변 입력/결과를 둔다. 기존 .atlas-link 및 .document-handoff 원장은 보존하고 서비스 참조로 연결한다. 이번 설계에서 기존 기록을 파괴적으로 이동하지 않는다. UI 체크리스트는 원장의 투영이며 별도의 수동 완료 진실 공급원이 아니다.

요청 저장 후 송신(outbox), 수신 원형 저장 후 전달 등록(inbox), 작업 점유 후 실행, 결과 저장 후 전달 확인 순서다. 로컬 원자적 기록 또는 재대조로 중간 종료를 복구한다. 외부 모델의 정확히 한 번 실행을 주장하지 않고 중복 채택을 방지한다.

결과·질문·역할/정책 revision으로 검토 중복을 판정한다. 작업별 시도 이력과 프로젝트 writer lock을 두고 실패한 모델을 타이머로 무한 재실행하지 않는다. 질의 변경 후 늦은 답변은 보존하고 superseded/관련성 검토로 연결한다. 이전 판단을 자동 덮어쓰지 않는다.

### 9.1 중지·늦은 응답·종료 — B4

로컬 stop/cancel_requested와 remote_cancel_confirmed/unsupported/unknown을 분리한다. 공개 A1 job cancel은 미지원이다. import cancel은 Documents 변환 취소나 기존 위키 롤백이 아니다. jobs/recover는 정상 연구 루프의 자동 재개 API로 호출하지 않는다.

Pilot 재시작은 전달 복구이며 원격 모델 재실행 권한이 아니다. 고아 작업은 실제 진단과 재개 조건을 표시한다. 결론 기록 직전에 work/input/policy revision과 실행 점유 generation을 대조해 오래된 실행기의 채택을 거부한다. 역할이 없어졌으면 임의 반환 대신 needs_input 또는 조정자의 재배정 기록을 남긴다.

사용자 정지는 신규 제출·후속 실행을 막는다. 이미 도착한 원형은 보존할 수 있다. 질문 변경·취소·M1 종료 후 응답은 자동 채택하지 않는다. M1 완료는 필수 dependency와 검토·판단 충족으로 결정하며 외부 요청 수가 0이라는 이유만으로 완료하지 않는다. 불필요해진 대기는 제외 이유를 기록한다. 종료 후 continuation과 다음 마일스톤은 자동 실행하지 않는다.

### 9.2 지식 반영 복합 요청 — 신규 계약 대기

한 요청에 answer와 knowledge의 복수 불변 결과를 허용한다. 전달 중복 키에는 request·단계·결과 revision/hash·수신 대상/input revision을 포함한다. 먼저 답변을 전달했어도 후속 반영 결과를 보존한다. 위키 결과 도착만으로 토론을 반복 생성하지 않는다.

답변 이용 가능, 위키 저장, 색인, parent 종료, 연구 완료를 분리한다. 입력 페이지 원형의 작업별 고정·회수, 이번 QA 후보만 처리, 단계 간 영속 연결은 Atlas 확장 사항이다. capability/계약 구현 전에는 경로를 비활성으로 두고 기존 readonly ask를 유지한다. 기존 import 이벤트를 재사용하지 않는다.

## 10. UI

프로젝트의 기존 작업/자료 화면에서 무엇을 누구에게 요청했는지, 외부 처리·Pilot 수신·담당 검토 상태, 다음 대기 조건을 보여준다. 요청·답변·검토·다음 작업을 연결해 펼쳐볼 수 있다. 원형 토론은 보존하고 과거 질문/결론의 버전을 표시한다. 마일스톤 끝에는 핵심 결과·근거·미확인·다음 단계 입력을 모아 보여준다.

## 11. 구현 단위와 수락 기준

1. 기존 A1 질의의 누락 연결부터 보완: 저장된 job-71f93df47d324b48을 재접수하지 않고 관찰·QA 수신·전달 대기까지 연결. 다른 instance/QA 해시 불일치 차단.
2. 공통 요청/반환 대상 원장: 문서 import와 ask 연결부를 기존 계약 위에 매핑. 같은 요청 재전송·응답 유실·이미 ACK된 결과 복구·잘못된 수신자 시험.
3. 작업 재개와 에이전트 수신 확인: 프로세스 종료/질문 변경/독립 공개 규칙/여러 응답 대기/프로젝트 간 격리를 시험.
4. 통합 질의 → 종합 토론 → 다음 작업 실행: 불필요한 동일 질의 반복 방지, 부분 결과 사용 제한, 원형 접근 실패 보존, 다음 행동 범위 검사.
5. 마일스톤 자율 루프·UI: 사람의 단계별 클릭 없이 허용된 M1 작업을 이어가며 완료 근거가 갖춰졌을 때만 마침. 다음 마일스톤 자동 착수 금지. 실제 외부 권한 필요 작업은 해당 작업만 대기.

Atlas 공동 검토 항목: 서비스별 봉투 매핑 가능 필드, consumer/instance/요청 추적, A1 응답 버전과 상태 의미, 현재 미지원 기능. Atlas에 새 통합 endpoint나 범용 이벤트를 먼저 요구하지 않는다. 필요성이 확인되면 계약을 별도 확장한다.


## 12. 공동 검토 수락시험과 개발 경계

Atlas 검토 원문: /Users/jspark/orca/projects/ResearchAtlas/docs/integrations/documents-atlas/pilot-service-request-review-2026-09-18.md

원문 8절의 17개 수락시험을 본 설계의 수락 기준으로 포함한다. 기존 서비스 시험과 신규 복합 요청 시험을 분리한다. 증거에는 외부 원상태·원형/hash·Pilot 상태·수신 대상·실행 횟수·채택 횟수를 남긴다.

- B1: 미지원 봉투/operation 거절과 실제 payload 보존.
- B2: key 충돌·접수 유실·execute 재전송·인증/instance/프로젝트 불일치.
- B3: 공유 consumer 분배·빈 tail/ACK 복구·dispatch/고아·QA 부재/partial/진단 결과·원형409/chunk/그림 부재.
- B4: 취소 경합·역할 교체/오래된 실행기·dependency 사용 제한·M1 종료/늦은 결과·정지/자원 범위. 사용자 정지는 전체 신규 실행을 막고, 개별 자원 제약은 영향 작업만 막는 것으로 구분한다.
- B5: 독립 회차 입력 revision과 공유 위키 노출 차단.
- 신규 복합 계약: answer 이후 knowledge 실패·재개와 페이지 저장/resolve/색인/보고 경계 복구. 해당 기능 구현 후 검증한다.

기존 ask 관찰·QA 수신·공통 원장·회차 반환·마일스톤 경계는 Atlas 새 API 없이 개발 가능하다. 지식 축적 operation은 별도 계약·구현이 필요하다. 그림 artifact/typed coverage/공개 ask 취소는 이번 필수 범위를 자동 확대하지 않는다. 사용자 정책 세 가지는 atlas-knowledge-feedback-discussion.md에서 미확정으로 유지한다.
