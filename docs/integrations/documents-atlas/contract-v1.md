# Pilot–Documents–Atlas 문서 지식화 계약 v1

2026-09-17 · 상태: v1 규범 본문. 담당별 최종 수용·해시는 agreement-v1.md에 기록한다. 사용자 요청에 따른 설계 확정이며 구현·배포 완료가 아니다. 기존 Pilot–Atlas A1 ask 계약은 유지한다. 이 계약의 신규 기능은 별도 capability 협상과 수락 시험을 통과한 뒤 사용한다.

## 1. 역할과 정상 흐름

Pilot은 원문을 확보하여 Documents 변환을 요청하고, 받은 작업 참조를 Atlas에 전달한다. Atlas가 작업을 기다려 결과를 회수·지식화하며 Pilot은 결과를 받아 연구 사용 여부를 판단한다. Documents에 완료 push를 요구하지 않는다.

1. Pilot이 원문·이미지·고정 변환 설정으로 Documents에 접수한다.
2. Pilot이 영수증을 저장하고 Atlas에 Documents 작업 참조·서지·연구 목적·프로젝트를 전달한다.
3. Atlas가 접수 기록을 커밋한 뒤 상태를 1회 조회한다. 미완료면 조회 시도 종료 후 600초 뒤 다시 조회한다.
4. Documents COMPLETED/PARTIAL 결과를 Atlas가 불변 참조로 고정·다운로드·해시 확인한다.
5. Atlas가 원형/변환 연결·내용 정리·위키·요청한 검색 색인을 반영한다.
6. Atlas가 고정 결과와 완료 이벤트를 저장한다. Pilot 서비스가 이벤트를 조회하여 결과를 영속화하고 event ID별 ACK한다.

Documents 접수, 변환 완료, Atlas 지식화 완료, Pilot 연구 채택은 서로 다른 상태다. QA 생성·발췌 질답은 원문 등록이나 지식화의 대체가 아니다.

## 2. 현재 지원과 신규 요구

현재 Documents는 PDF 외 DOC/DOCX/PPT/PPTX/HWP/HWPX/JATS XML/Markdown/TXT를 공통 입력으로 지원한다는 담당 검토가 있다. 일반 XML·HTML 지원으로 확대하지 않는다. JATS+그림은 HTTP `/api/tasks/jats`와 MCP `queue_jats_base64`가 구현돼 있다. MCP `queue_pdf_path/base64` 이름은 호환 명칭이다. 운영 MCP의 HTTP와 동일 배포·저장소 여부는 실행 전 검증해야 한다.

현재 상태·verification 자산에는 개별 해시와 다운로드 참조가 있지만 전체 불변 manifest·고정 instance·일반 접수 request_key·회수 보관 보장은 신규 요구다. Atlas에는 별도 import 대기/600초 조회/외부 완료 이벤트·ACK가 아직 구현되지 않았다. capability 없는 서버에 신규 요청을 기존 ask/ingest로 바꿔 보내지 않는다.

현재 새 논문 DOI 10.3390/polym16192694는 Pilot JATS XML 확보와 Atlas 발췌 QA 단계다. 본 계약 확정으로 변환 접수·원문 등록·연구 재개를 수행하지 않는다.

## 3. 전송과 버전 협상

신규 계약 식별자: `pilot-documents-atlas/1.0`. Atlas 기존 `pilot-atlas/1.0`은 바꾸지 않는다. HTTP와 MCP는 하나의 서비스 계층·작업·영수증·오류 의미를 공유한다. 아래 신규 명칭은 이 버전의 구현 목표이며 현재 호출 가능한 기능이 아니다.

| 서비스/행동 | HTTP | MCP |
| --- | --- | --- |
| Documents 계약 정보 | GET /api/integration/info | get_integration_info |
| Documents 일반 입력 | 기존 POST /api/tasks + contract_version/request_key/config_revision | 기존 queue_pdf_path/base64에 같은 계약 필드 추가 |
| Documents JATS+assets | 기존 POST /api/tasks/jats + 동일 계약 필드 | 기존 queue_jats_base64에 동일 계약 필드 추가 |
| Documents 영수증 복구 | GET /api/integration/receipts/{request_key}?operation=… | get_submission_receipt(request_key, operation) |
| Documents 상태 | 기존 GET /api/tasks/{id} | 기존 get_task |
| Documents 고정 결과 | GET /api/tasks/{id}/result-manifest?revision=… | get_result_manifest |
| Documents 회수 확인 | POST /api/tasks/{id}/retrieval-acks | acknowledge_result_retrieval |
| Atlas 접수 | POST /api/document-imports | atlas_import_from_documents |
| Atlas 목록·재조정 | GET /api/document-imports?cursor=… | atlas_document_imports |
| Atlas 조회 | GET /api/document-imports/{id} | atlas_document_import |
| Atlas 조치 | POST /api/document-imports/{id}/resume 또는 /cancel | atlas_resume_document_import / atlas_cancel_document_import |
| Atlas 이벤트 | GET /api/events?cursor=…&limit=… | atlas_events |
| Atlas ACK | POST /api/events/ack | atlas_ack_events |

Documents capability `document_handoff_v1`, Atlas capability `documents_import_v1`이 실제 동작할 때만 선언한다. 정보 응답에는 영속 instance_id·build_revision·지원 입력·전송 한도·설정 revision을 포함한다. 재시작/동일 DB 복구는 instance 유지, 독립 복제는 새 instance다.

큰 파일은 HTTP로 전송하고 MCP는 접수·조회와 작은 참조에 사용한다. base64 도구도 수신 어댑터가 처리하며 모델 문맥에 원문 바이트를 펼치지 않는다. 기존 asset 다운로드 경로는 manifest에서 발견한다. 새 명칭이 기존 라우트와 충돌하면 담당이 최종 수용 전에 보고하며 몰래 다른 이름으로 구현하지 않는다.

## 4. 식별·접수·멱등성

공통 identity는 service instance + task/import ID이며 파일 경로나 DOI만으로 동일성을 판단하지 않는다. `consumer_id`는 인증된 서비스 등록에 바인딩한다. payload 임의 consumer 값으로 권한을 얻지 못한다. 로컬 인증만으로 소비자를 구분할 수 없는 배포에서는 consumer 분리 인증/허용 매핑을 구현하기 전 다중 소비자 보장을 선언하지 않는다.

Documents 접수는 request_key·contract_version·고정 config_revision·원문 표현/MIME/이름/바이트·JATS asset 매핑을 받는다. 서버가 canonical fingerprint를 계산하며 같은 consumer+operation+key/동일 내용은 같은 task/receipt, 다른 내용은 충돌이다. 설정 기본값은 최초 접수 때 고정하고 재전송에 새 기본값을 적용하지 않는다. 동시 생성은 원자적으로 하나만 허용한다. fingerprint에는 원문·자산 해시, 실행/변환/프롬프트 설정 revision을 포함하며 비밀을 제외한다. 원본 raw 해시는 클라이언트 값을 믿지 않고 검증한다. 일반 접수와 JATS 접수 간 operation 공간은 다르며 각각 HTTP/MCP 교차 재시도는 같은 공간을 사용한다.

Atlas 접수 필수:
- request_key, contract_version, consumer_id; pilot_project_id·work/question 참조.
- atlas_project_id: 명시적인 프로젝트 ID 또는 null. Pilot M1은 기본 지식 프로젝트를 명시한다. Atlas 일반 자료에는 null 허용.
- documents_service_ref: 등록 별칭+expected instance; task_id, 원문 표현/MIME/해시, package fingerprint, 알려진 parent/root/retry 관계.
- 서지·출처 URL, 목적·요청한 정리 범위·검색 색인, partial 정책(초기 v1은 가용 범위 정리 후 partial).
- 원문 회수 참조. Documents 자산 참조 또는 사전 등록된 Pilot 원형 조회 참조 중 하나. 임의 파일 경로/URL 실행·토큰 전달 금지.
- expected_result_ref 및 previous_import_ref는 있는 경우. 없으면 지정 task의 첫 회수 가능한 terminal snapshot을 선택하고 영속 고정한다.

양 서비스 영수증은 instance/operation/request_key/request_sha256/접수 ID를 반환한다. Atlas 응답에는 import_id·phase·outcome·next_poll_at을 추가한다. 서버 정규화 fingerprint가 기준이다. 누락 기본값, set 의미의 배열 정렬, 순서 의미 배열 유지, 문자열 trim 여부를 필드 schema로 정의하고 수락 시험에서 HTTP/MCP 동일성을 확인한다.

Documents의 정규 operation은 일반 입력 `convert.file`, JATS+assets 입력 `convert.jats`로 고정한다. 영수증 조회의 operation은 필수이며 HTTP/MCP가 같은 값을 사용한다. 알 수 없는 operation은 명시 오류로 반환하고 같은 key의 다른 operation을 임의 선택하지 않는다. 멱등 공간의 consumer는 인증된 접수자이며 위임 조회 시에도 원 영수증의 접수자 공간을 사용한다.

Documents handoff의 `submitted_by_consumer_id`는 인증된 Pilot으로 고정한다. 접수 시 `retrieval_consumer_id`로 등록된 Atlas를 지정하고 서버 측 Pilot→Atlas 허용 매핑을 검증한다. 해당 Atlas에만 위임된 handoff의 영수증·작업·고정 결과 조회와 회수 ACK 권한을 부여한다. 영수증은 제출자·회수자 참조를 반환한다. request_key 멱등 공간은 제출자 Pilot에 남고 retrieval_consumer_id는 fingerprint에 포함한다. 회수자만 바꾼 동일 key 재접수는 충돌이다. v1은 접수 시 고정 매핑만 지원하고 별도 승인된 위임 계약 없이 회수자를 변경할 수 없다.

회수 의무·삭제 보호는 `(handoff_receipt_id, retrieval_consumer_id)`로 기록하고 결과 고정 후 정확한 result_ref를 연결한다. Atlas ACK는 자신의 인증·해당 receipt·고정 result_ref를 검증해 그 의무만 충족한다. 다른 revision·다른 handoff·다른 consumer의 ACK나 Pilot 제출자의 ACK로 Atlas 미회수 보호를 풀지 않는다. Pilot에는 별도 회수 의무를 자동 생성하지 않는다. 공유 task의 다른 handoff/회수 consumer 의무는 독립적으로 남는다. Atlas 접수 전 실패/취소로 회수하지 못하면 보호는 유지되며 명시적 운영자 강제 삭제+tombstone 정책만 적용할 수 있다. Documents 회수 ACK와 Atlas 완료 이벤트 ACK는 별개다.

위임 Atlas가 key+operation만으로 여러 Pilot의 영수증을 조회할 수 있는 경우에는 최초 받은 receipt_id로 조회 범위를 고정한다. v1 영수증 복구 경로는 원 접수자 Pilot의 인증으로만 사용한다. Atlas의 영수증 조회는 위임된 handoff receipt 참조를 task/result 조회 응답에서 제공하며 원 접수자의 key 공간을 추측·열거하지 않는다.

Pilot은 Documents 요청 전 outbox를 저장하고 영수증을 받은 뒤 Atlas 요청을 별도 저장한다. Atlas 접수 실패 때 Documents를 재제출하지 않는다. Documents 응답 유실은 먼저 영수증 조회 또는 동일 key 재전송으로 복구한다. 기존 비멱등 서버에서는 needs_attention이며 force/rerun으로 우회하지 않는다.

## 5. 불변 결과와 원문·변환 버전

Documents terminal 결과 manifest는 instance_id/task_id/result_revision/terminal_status/finalized_at, 원문 표현·package fingerprint, 실행 설정, root/parent 및 알려진 재실행 관계, artifacts, regions/quality/issues, 보관 조건을 포함한다. task 내 artifact ID는 유일해야 한다. 각 artifact는 역할·원래 MIME·전송 MIME·크기·sha256·조회 참조·가용 여부·누락 이유를 갖는다. 원문·Markdown·ZIP·그림·표/수식·regions·생성 설명을 구분한다.

`result_ref={instance_id,task_id,result_revision,manifest_sha256}`. manifest_sha256은 UTF-8로 고정 저장한 manifest 원형 바이트의 SHA-256이다. 자기 해시는 manifest 본문에 넣지 않고 응답 envelope에 둔다. ZIP 자신의 해시를 ZIP 내부에 넣지 않는다. 결과 snapshot과 artifact 바이트는 변경하지 않으며 변경 가능한 사람 검토는 review_revision으로 분리한다. pending 상태 GET은 가볍게 유지하고 매번 원형 파일 전체를 다시 해시하지 않는다.

JATS XML SHA-256은 XML 원형 해시다. 그림 포함 package fingerprint/ZIP 해시와 구분한다. XML ID/위치로 근거를 연결하고 없는 PDF 페이지/bbox를 만들지 않는다. 그림이 빠지면 issues/coverage에 남긴다. 제공되지 않은 원격 그림을 Documents가 수집했다고 가정하지 않는다.

같은 원문을 재변환하면 source/version을 재사용하고 extraction/result와 위키 이력을 추가한다. 원문 바이트가 바뀔 때만 새 source version을 연결한다. 같은 DOI의 PDF/XML은 서로 다른 표현이다. 선택 재시도는 parent child 관계, 전체 재실행은 root/duplicate family와 Pilot의 요청 원 task 참조를 보존한다. 항상 새 task를 명시적으로 후속 import에 연결하며 자동 최신 추종 금지. 같은 원문이어도 연구 목적·프로젝트 의뢰는 합치지 않는다.

## 6. Atlas 조회기·실행 경계

Atlas는 별도 durable import 레코드를 소유하고 결과 지식화에 기존 ingest 실행기를 재사용한다. Documents 의견의 jobs kind 확장은 외부 상태 일원화 취지로 반영하되 내부 저장 구조 결정은 Atlas 안을 따른다. 네트워크 대기를 LLM running 작업으로 만들지 않는다.

접수 커밋→최초 1회 상태 조회→조회 완료 시각+600초. 429 Retry-After가 600초보다 길면 그 이후에 조회한다. 짧은 네트워크 timeout은 원격 작업 제한 시간이 아니다. 만기 레코드 원자적 claim·lease_generation을 사용해 중복 worker와 이전 lease의 늦은 쓰기를 차단한다. 재시작 후 missed tick을 몰아 실행하지 않는다.

기존 사용자 ask/ingest의 queued/running을 재시작 시 자동 실행하지 않는다. import가 만든 ingest만 연결한다. organizing 중단은 기존 job·batch·파일 반영을 먼저 조정하고 안전한 재개가 불명확하면 needs_attention이다. 실제 실행기 자동 재시작을 무조건 보장하지 않는다.

phase: accepted/waiting_conversion/fetching/organizing/needs_attention/terminal. outcome: null/completed/partial/failed/cancelled. 원래 Documents 상태·마지막 관측·오류·재시도 여부·next_poll_at·고정 result_ref·ingest_job_ref를 별도 보존한다.

- QUEUED/PROCESSING: 다음 조회. 시간/횟수만으로 실패 판정 금지.
- COMPLETED/PARTIAL: manifest와 원형 확보 후 정리. PARTIAL은 초기 v1 Atlas outcome도 partial.
- FAILED: 결과는 진단용 보존 가능, 자동 지식화·새 변환 접수 금지.
- 통신/5xx: 다음 주기 재조회. 권한/instance 불일치/해시 불일치/404는 needs_attention과 이벤트. 404는 삭제로 단정하지 않고 not_found_or_unavailable, task/asset을 구분한다.
- completed이나 결과 부재: 공급자가 retryable 지연을 명시할 때만 재조회, 아니면 needs_attention.
- resume는 조치·고정 identity 확인 후 같은 요청을 재개하며 내용 변경은 새 요청이다. cancel은 Atlas 후속 작업만 중단한다. 공유 Documents 작업 삭제/취소나 기존 지식 롤백으로 전파하지 않는다.

## 7. 완료·통지·보관

completed는 원문과 변환 snapshot 보존, source/project/extraction 연결, 요청 범위 내용 정리·읽은 범위·미확인 기록, 위키 이력, 요청한 검색 색인의 실제 조회 가능 상태를 충족해야 한다. 요청하지 않은 선택 색인은 not_requested다. 정리 범위와 결과를 별도로 반환하며, 누락이나 요청 색인 실패가 있으면 partial로 보존한다. 형식 통과를 사실 정확성 보증으로 쓰지 않는다.

고정 Atlas 결과: import_id/request 참조, Documents result_ref, source_refs/extraction_refs/page_refs(당시 hash), read_scope/unresolved/index_status/ingest_job_ref. result_ref의 자체 해시도 envelope에만 둔다.

Atlas terminal 전환+결과 참조+outbox event는 같은 트랜잭션이다. 파일 고정 후 DB 커밋하고 장애 시 조정한다. event에는 atlas_instance_id/consumer_id/event_id/sequence/import_id/request_key/result_ref/outcome/phase를 넣는다. 대형 본문·비밀은 넣지 않는다. needs_attention도 통지 이벤트를 발행한다.

Pilot 서비스가 60초 간격으로 이벤트를 조회하는 것을 v1 기본으로 한다. 이는 Atlas→Documents 600초 조회와 별개이며 에이전트 자동 대화 개시를 뜻하지 않는다. 수신·처리 기록을 영속 저장한 뒤 event_id 목록으로 ACK. cursor는 조회 위치이며 누적 ACK가 아니다. at-least-once 전달이며 중복/역순을 import/result/sequence로 처리한다. 다른 consumer ACK는 거절한다. ACK 유실 재전송은 성공으로 수렴한다.

v1 보관 기준: Documents handoff 접수는 자동 만료 없음. 등록 consumer가 회수하기 전 삭제를 기본 거절하고, 운영자 강제 삭제는 명시 사유·tombstone을 남긴다. 회수 ACK 후에도 자동 삭제하지 않는다. 다른 consumer의 미회수 상태는 유지한다. ACK는 Atlas가 바이트/해시/원형을 영속 저장했다는 뜻이며 지식화 완료가 아니다. 삭제 API와 일괄 삭제에도 동일 규칙을 적용해야 한다. 기존 task는 별도 pin/회수 계약 적용 전 제품 보호를 보장하지 않는다.

Atlas v1 이벤트/영수증/고정 결과는 자동 만료하지 않는다. 장기 운영 GC는 후속 계약으로 둔다. 잘못된/만료 cursor는 명시 오류로 반환하고 consumer별 전체 import 상태 페이지 조회로 재조정한다(가칭 GET /api/document-imports?cursor=… 및 atlas_document_imports). 용량 부족은 성공으로 위장하지 않고 접수 전 오류 또는 기존 요청 needs_attention으로 보존한다. 무기한은 무한 저장 용량 보장이 아니라 임의 자동 삭제를 하지 않는 정책이다.

## 8. 구현 단위와 수락 시험

1. Documents 계약 안내 정정·운영 HTTP/MCP 동일 instance·입력·capability 확인.
2. Documents 고정 instance/config revision·접수 멱등 영수증·조회. 병렬·응답 유실·설정 변경·HTTP/MCP 교차 재시도 동일 task, 내용 변경409.
3. Documents snapshot manifest·원문/자산·PARTIAL/child/family·회수 ACK/삭제 보호. 해시·ZIP경로/링크·중복경로·압축해제 한도 검증, 부모 결과 보존.
4. Pilot 변환 outbox→Atlas 접수 outbox. 두 호출 사이 장애에도 중복 변환 없음.
5. Atlas import/600초 조회/lease. 가상 시계599/600초·429·재시작·장기 처리·이전 lease 쓰기·기존 job 자동 실행 없음.
6. Atlas 회수→ingest→검색. 원형 동일 재변환 source 재사용, 새 extraction, 지식화 중단 복구 또는 명시 needs_attention. QA만 생성되면 실패.
7. 이벤트+ACK. Pilot 중단·ACK 유실·중복·역순·consumer 격리·cursor 복구·보관/삭제 정책.
8. 같은 consumer/key의 convert.file/convert.jats 영수증이 독립 복구됨; 허용된 Pilot→Atlas 회수, 미등록 Atlas·payload 위조·타 consumer ACK 거절, 다른 receipt/result revision ACK로 보호 해제 금지, 회수자만 바꾼 동일 key 충돌, ACK 재전송 수렴.
9. 별도 실행 시 실제 JATS+그림 논문1건: 접수→변환→등록→검색 출처 반환→Pilot 수신. 현재 논문은 이 문서 작업에서 처리하지 않는다.

## 9. 근거와 공동 수용

- [Pilot 초안](polling-handoff-proposal-2026-09-17.md)
- [Atlas 검토](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/documents-atlas/polling-handoff-review-2026-09-17.md)
- [Documents 검토](/Users/jspark/orca/documents/doc/integrations/pilot-atlas/polling-handoff-review-2026-09-17.md)

Pilot은 위 결정을 수용한다. 두 담당의 필수 보완인 operation별 영수증 복구와 Pilot 제출자/Atlas 회수자 위임·삭제 보호를 반영했다. 수용 기록은 agreement-v1.md에 별도 보관하여 규범 본문 해시를 안정적으로 유지한다. 구현 확정과 배포·수락시험 통과는 다른 기록이다.
