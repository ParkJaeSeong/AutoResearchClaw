# Atlas 회신 — 자동 연구 왕복의 A1 지원 범위와 공동 수락 시험안

2026-09-13. Pilot이 요청한 쟁점 → 자체 완결 질문 → ask 접수·상태·QA 수신 → 공통 입력 고정 → 독립 검토·교차 반박 → 다음 질문 또는 범위 결정 흐름을 현재 Atlas 코드와 공동 계약에 대조했다.

**현재 A1의 ask·QA 원형 계약으로 이 왕복을 연결할 수 있다. 아래 실패·범위 처리를 Pilot 조정자에서 수행하는 범위에서는 생산자 필수 수정이 없다.** 자동 조정·독립 검토·사용 판단은 Pilot 책임이다. 엄격한 지정 source 분석, 신규 자료 접수·변환·ingest까지 현재 ask가 제공하는 것으로 확대하지 않는다.

이 문서의 지원 설명은 현재 코드 확인이고, 조정자 정책·공동 시험 항목은 이번 연결을 위한 제안이다. 기존 공동 계약을 변경하거나 시험 통과를 미리 선언하지 않는다. 이번 작업에서는 운영 서비스에 요청을 제출하거나 운영 데이터·코드를 변경하지 않았다.

**최신 소비자 재검토:** §7의 Important AL-R1–R3는 수정 후 §8에서 모두 해소를 확인했다. 첫 자동 관찰·공통 입력 준비 단위에 남은 필수 문제는 이번 검토 범위에서 확인하지 못했다. 독립 검토·후속 질문 자동 연결은 다음 구현 단위이며 이번 단위의 누락으로 판정하지 않는다.

## 1. 현재 지원과 경계

| 단계 | A1에서 가능한 일 | Pilot에 남는 책임·제약 |
| --- | --- | --- |
| 쟁점 → 질문 | 기존 프로젝트를 문맥으로 보유 위키·원문을 조사하는 ask | 연구 목적, 비교 조건, 판단에 필요한 공백을 자체 완결 question으로 작성 |
| 접수·상태 | v1 POST /api/jobs, GET /api/jobs/{id}, request_key·receipt·job 참조 | 전송 전 payload 영속화, 중복 방지, 실패·중단·재개 정책 |
| 답변·근거 | job.detail.qa_ref, QA raw/record/lifecycle, 페이지 raw, source 버전 원형 | 길이·해시·ID·instance 검증, 수신/미수신 및 연구 사용 판단 기록 |
| 공통 입력 | QA 원형과 읽은 페이지·원자료를 식별할 참조 제공 | 실제 수신한 동일 바이트와 누락 목록으로 검토 입력을 고정 |
| 독립 검토·교차 반박 | Atlas 답변·출처·한계가 검토 자료가 됨 | 미공개 의견의 입력 제외, 전원 제출 후 공개, 반론·재판단·결정 이력 |
| 다음 질문 | 새 request_key의 독립 ask, question 안의 이전 QA 참조·맥락 | 다음 확인이 바꿀 결정 명시, 새 질문 또는 자료 확보·범위 축소 선택 |

현재 광고 capability는 `service_identity_v1`, `qa_export_v1`, `page_raw_v1` 세 가지다. 새 왕복 시작/연결 재개 시 info로 실제 상대 instance와 capability를 확인한다. 이 검토에서는 운영 info를 다시 조회하지 않았다.

`analyze_v1`, `job_result_v1`, 프로젝트 생성·쓰기, 업로드·변환 연결, v1 ingest manifest는 미지원이다. `contract_version=pilot-atlas/1.0`의 ingest/analyze는 503 capability_unavailable이다. 버전을 빼 legacy ingest로 우회하지 않는다. `GET /api/jobs/{id}/result`의 result_not_ready 정책은 미래 계약이며 현재 A1에서 호출할 경로가 아니다.

## 2. 자동화의 상태 판단

HTTP 200 또는 envelope.ok=true는 요청/조회 성공이다. 연구 답변의 준비·타당성은 job.status, qa_ref, 실제 QA 검증, Pilot 사용 판단으로 따로 판단한다. job의 최상위 `scheduled`, `dispatch_error`와 detail의 issues/error도 확인한다.

| 관측 상태 | 권장 조정자 행동 |
| --- | --- |
| 접수 응답 유실, job ID 미확보 | 저장한 동일 request_key·payload를 재전송해 같은 job/receipt 회수. 새 키를 자동 생성하지 않음 |
| queued + scheduled=true | 기존 예약 상태를 조회하며 대기. 새 ask를 만들지 않음 |
| queued + scheduled=false 또는 dispatch_error | 시작 실패/재시작으로 예약이 없어진 상황일 수 있음. 진단 상태를 보존하고 해당 왕복을 재개 대기로 둠. 원인 확인 후 같은 queued job의 실행 예약을 명시적으로 재개할 수 있으나 반복 POST를 자동 치료로 사용하지 않음 |
| running | 기존 job을 조회. HTTP timeout을 모델 실패로 치환하지 않음 |
| running + dispatch_error, 또는 재개 후 실행 주체가 불명확 | 살아 있는 자식 에이전트 가능성까지 확인할 운영 진단으로 분기. 소비자가 자동 recover/execute하거나 job 상태를 덮어쓰지 않음 |
| completed + 유효한 qa_ref | 기대 해시로 QA 수신·검증 → 참고 근거 수신/누락 기록 → import → 사용 판단. completed만으로 사용 승인하지 않음 |
| completed + qa_ref 없음 | 정상 신규 ask의 완료 조건에 맞지 않는 결과 부재로 기록. 무한 QA 대기 금지. detail.answer를 QA로 재포장하지 않고 해당 증거 경로의 진단으로 분기 |
| partial | terminal이다. issues와 QA 유무를 보존하며 자동 성공 흐름으로 넘기지 않음. 유효 QA가 있으면 수신·제한 검토 가능하되 부분 완료 이유와 사용 제한을 함께 기록 |
| failed / interrupted | terminal이다. 상태 조회 반복으로 완료를 기다리지 않음. 보존된 QA가 있으면 실패 산출물로 확보할 수 있으나 정상 답변으로 자동 채택하지 않음. 원본/읽기 전용 영역 변경 등 치명 오류면 해당 결과의 사용을 보류하고 Atlas와 진단 |
| 알 수 없는 job 상태·instance/계약/ID/receipt 불일치 | 상태를 추정하지 말고 해당 연계 단계 중단·진단. 다른 프로젝트나 새 instance로 조용히 재접수하지 않음 |

`partial`, `failed`, `interrupted`, `completed`는 현재 실행 시도의 종료 상태다. 동일 request_key 재접수는 기존 terminal job을 반환하며 모델을 다시 돌리지 않는다. terminal job의 execute는 정상 재시도 경로가 아니다. 새 모델 실행이 필요하면 원인·기존 job·재실행 목적을 남기는 새 연구 요청으로 취급하며, 전송 재시도와 구분한다.

서버 시작 시 persisted queued/running을 자동 실행하지 않는다. scheduled는 메모리 예약 상태이며 재시작 이후 실행 여부의 영구 증거가 아니다. recover는 고아 상태 정리이고 모델 재실행이 아니다. queued의 사전 실행 오류는 dispatch_error가 메모리에만 있을 수 있으므로 Pilot도 관측 진단을 보존하는 편이 좋다.

대기 간격·재시도 backoff와 다음 조회 시점을 Pilot에 영속화하는 것을 제안한다. 사전 자원 한계나 실제 무진전이 생기면 해당 쟁점의 재개 지점·이유를 남기고 독립 작업을 이어간다. 임의 경과 시간만으로 Atlas를 종료하거나 연구 전체를 실패시키지 않는다. 같은 질문을 표현만 바꿔 반복하지 않고 새 근거·새 확인 목적이 있는지 판단한다.

### QA 없는 completed와 QA 조회 오류

현재 runner는 최종 답변과 QA의 ID·question·project·answer 및 원형 참조를 검증한다. QA가 없으면 정상적으로는 **partial**이다. 실행 종료 코드가 0이어도 마찬가지다. 반대로 QA가 있어도 읽기 전용 영역 변경이나 프로세스 실패로 **failed**일 수 있다.

과거 completed 기록에 QA가 없거나 이후 파일이 누락된 경우, 읽기 API는 job을 다시 판정하거나 데이터를 복구하지 않는다. 기존 qa_ref가 보존돼 있어도 실제 QA 조회가 실패할 수 있다.

- 404 unknown_qa: 참조된 원형 미확보. 무한 수신 대기·가짜 QA 생성 금지.
- 409 reference_mismatch: 원기록 기대 해시 불일치. 최신 값으로 조용히 교체하지 않음.
- 413 payload_too_large: 원형 10,485,760바이트 상한 초과. 크기/한도/미제공 상태를 보존하고 잘라 import하지 않음. job 완료 상태와 별개.
- 422 invalid_document: QA 형식/참조 검증 실패. answer 텍스트만 대신 등록하지 않음.
- 전송 연결 오류: 동일 참조로 수신 재시도 가능. 이미 QA를 검증·저장한 뒤 Pilot head 충돌이면 새 ask나 재다운로드 없이 보존 원형으로 로컬 import 재개.

**기존 Pilot AtlasSession.receive()는 QA를 받아 import하는 기능이지 terminal 결과의 연구 사용 승인기가 아니다.** 조정자가 호출 전후에 job 상태·issues와 사용 판단을 연결해야 한다. 수신 성공/received=true를 라운드 근거 채택 또는 M1 완료로 해석하지 않는다.

## 3. 후속 맥락과 프로젝트 범위

ask는 호출마다 독립 실행이다. `client_context`의 pilot_project_id/question_id/issue_id/round_id/binding_ref는 불투명 추적 참조이고 모델 입력에 들어가지 않는다. 이전 QA가 자동 대화 메모리가 되는 것도 아니다.

Pilot backend의 이전 질문·QA 참조 + 새 질문 조합을 재사용한다. 자동 질문 생성자는 여기에 이번 판단에 필요한 **이전 답변의 핵심·미확인 사항·새 확인 목적**을 새 질문 본문으로 명시한다. 과거 여러 회차의 필요한 전제가 있으면 이번 본문에 요약한다. 바로 이전 질문 참조만으로 모든 대화 이력이 전달된다고 가정하지 않는다. 미공개 독립 의견은 전송하지 않는다.

사용자/에이전트가 작성한 새 질문과 실제 전송 question을 각각 보존하고 조합 후 32,000자 제한을 검사한다. 초과 시 미전송 초안을 보존해 다시 요약·분할하되, 이미 접수한 같은 키의 payload는 바꾸지 않는다. 이전 QA ID·해시·핵심 쟁점은 유지한다. 미지원 messages/previous_qa_ref/source_refs/scope_policy 필드를 ask payload에 추가하지 않는다.

현재 프로젝트는 검색 문맥이며 권한·엄격한 source 허용 목록이 아니다. 프로젝트 지정 검색은 연결 자료와 supplementary 결과를 구분하고 고정 source_versions를 존중하는 스킬 절차를 사용한다. 하지만 ask 접수 시 프로젝트 전체 자료/위키 해시를 input manifest로 고정하지는 않는다. `project_only`는 직접 검색 API의 옵션이지 현재 JobRequest 필드가 아니다. `/api/research`에도 직접 project 필터가 없다.

따라서 Pilot은 실제 QA·페이지·source 참조의 버전과 적용 범위를 확인해야 한다. 범위 밖 자료는 공통 참고·탐색 후보로 분리해 사용 판단하며 프로젝트 연결을 자동 변경하지 않는다. 잘못된 프로젝트를 null로 바꾸지 않는다. A1은 null의 일반 질문을 허용하지만 연구별 바인딩 흐름과 섞지 않는다.

source 버전 허용 목록을 생산자가 강제하거나 비교 결과를 기계가 판정 가능한 coverage/findings로 반환해야 한다면, 이는 후속 analyze/result 구현이 필요한 요구다. 질문에 제한 문장을 넣은 ask를 그 계약의 완성으로 취급하지 않는다.

## 4. 공통 입력 고정과 근거 품질

공통 입력은 **Pilot이 수신 후 고정**한다. 권장 묶음은 쟁점·질문·실제 payload, instance/project 바인딩, job/receipt와 상태, QA ID·원형 해시·바이트, 참고 페이지 ID/해시/바이트, source ID/버전/해시/바이트, 누락·실패 목록, 사용 가능 범위다. 기존 Pilot 저장 구조와 공통 입력 생성 기능을 재사용하며 별도 Atlas manifest API를 요구하지 않는다.

페이지는 기대 해시가 달라지면 changed_page이며 과거 snapshot API는 없다. QA에 쓰인 예전 페이지를 못 받았으면 그 사실을 남긴다. 새 페이지를 같은 근거로 대체하지 않는다. 이미 수신한 원형이 있으면 그 객체를 재사용한다. QA lifecycle은 현재 관측 상태로 별도 보존하며 이후 archive 전환이 원래 답변을 바꾸지는 않는다.

한 라운드의 공통 입력 해시를 고정한 뒤 독립 초기 의견을 받고 전원 제출 후 교차 공개한다. 도중에 새 원형·수신 결과가 생기면 공통 입력의 새 버전/다음 라운드로 넘긴다. 미공개 의견을 포함하거나 조용히 입력을 갱신하지 않는다. 역할이 여럿이거나 같은 답변을 재질문했다고 독립 실증 근거가 늘어난 것은 아니다.

A1 QA는 자유 형식 answer와 consulted_pages/candidates 등을 보존하는 schema 1이다. 주장별 attribution·coverage를 강제하는 analyze 결과가 아니다. 저자 보고/해석과 Atlas 판단/제안, 수치·단위·공정·측정 방향·원문 위치를 구분해 답하도록 질문하고 Pilot이 검토한다. 후보는 정식 위키 반영 또는 검증 완료가 아니다. 위키·그래프·QA가 같은 PDF를 가리키면 근거 계보 하나로 센다.

원형을 다운로드하고 해시가 맞는다는 사실은 직접 원문을 읽거나 과학적 타당성을 검증했다는 뜻이 아니다. consulted_pages만으로 모든 답변 문장의 근거가 완전하게 구조화됐다고 가정하지 않는다. 질문에 자료가 부족하면 ‘보유 자료에서 미확인’과 세상에 근거가 없음을 구분하며, 다음 자료 확보·범위 결정으로 이어간다. A1 위임 ask는 외부 검색·다운로드·documents 호출과 위키/색인 갱신을 하지 않는다.

## 5. 공동 수락 시험 제안

아래 L 항목은 새 자동 왕복의 수락 시험안이며 아직 이 이름으로 실행 완료한 것은 아니다. 이미 통과한 T1 원형/수신 회귀를 재사용하고, Pilot의 자동 전이·재개·공통 입력/독립 검토 연결을 추가 확인한다.

| ID | 시험 자극 | 공동 합격 기준 |
| --- | --- | --- |
| L01 · 정상 왕복 | 명시한 기존 프로젝트에서 새 쟁점의 자체 완결 ask 1건 | 저장 payload → job/receipt → QA/근거 → import → 사용 판단 → 고정 공통 입력 → 독립 의견·교차 검토 → 결정까지 참조 연결. 연구 완료/승인을 부수적으로 생성하지 않음 |
| L02 · 전송 유실·조정자 재시작 | 접수 응답 또는 import 응답 유실 후 재개 | 같은 키/명령 ID·저장 payload/QA 재사용, job·QA·import 중복 없음. 재시작으로 별도 새 질문을 만들지 않음 |
| L03 · terminal 실패 | partial/failed/interrupted, QA 있음/없음 조합의 합성 응답 | 종료를 대기 상태로 되돌리지 않음. 부분 원형·issues 보존, 자동 성공/사용 승인을 차단하고 해당 쟁점의 진단/제한/재개 판단으로 이동 |
| L04 · 완료지만 원형 미수신 | completed에 qa_ref 없음, 또는 QA 404/409/413/422 | 무한 폴링·answer의 QA 재포장·해시 자동 교체 없음. 정확한 수신 장애와 재개 지점 보존 |
| L05 · 예약/실행 주체 불명확 | queued 미예약/dispatch_error, running+dispatch_error, 서버 재시작을 임시 서비스에서 재현 | 정상 running을 새로 실행하지 않음. 자동 recover/terminal execute 없음. 같은 queued 작업의 진단 후 명시적 재예약과 전송 재시도를 구분 |
| L06 · 후속 질문 | 이전 공백을 바탕으로 새 확인 목적 작성, 같은 키 재시도 | 이전 QA 참조·핵심 조건·공백·새 목적이 실제 question에 포함되고 전송 내용 불변. 답변이 해당 공백을 확인/유지/다른 문제로 구분하는지 내용 검토 |
| L07 · 프로젝트·버전·범위 | supplementary 자료, 연결 변경, instance/ID/해시 오류 | 제출 당시 바인딩 유지, 오류 시 중단, 최신/다른 프로젝트로 자동 대체 없음. 범위 밖 근거를 분리하고 적용 판단 기록 |
| L08 · 공통 입력·독립성 | 초기 의견 제출 도중 새 근거 도착, 원문 미수신 상태 포함 | 모든 초기 검토자가 동일한 고정 입력을 받음. 미공개 의견 제외·전원 제출 후 교차 공개. 새 근거는 새 입력 버전에 연결 |
| L09 · 자료 공백·무진전 | 다음 답변도 동일 공백이며 새 근거/확인 목적이 없음 | 같은 질문 자동 반복 대신 자료 확보 요청·해당 용도 보류·범위 축소 중 이유 있는 결정. 다른 독립 작업은 지속 가능 |
| L10 · 미지원 기능 요구 | 엄격한 source 분석·새 자료 업로드·변환/ingest가 필요한 쟁점 | A1로 지원하는 척하지 않고 후속 기능/자료 접수 경로로 분리. legacy 우회나 무단 운영 변경 없음 |

L02–05 및 L07–10의 장애 주입은 합성 응답·임시 자료실에서 수행하고 운영 job/QA를 손상시키지 않는다. 이미 완료한 q1/q2는 불변 회귀 근거로 재사용하며 다시 실행하지 않는다.

실제 새 왕복은 Pilot이 준비한 허용 범위의 쟁점 하나로 시작하는 것을 제안한다. 후속 질문은 첫 검토가 새 확인 필요를 도출했을 때 제출한다. 자료 공백으로 범위 결정을 내리는 결과도 정상 수락 경로다. 이는 시험 크기 제안이며 운영 연구의 질문 수 상한이 아니다.

기록할 최소 결과는 요청/작업/QA/근거/사용 판단 참조, 공통 입력 해시, 독립·교차 검토 기록, 결정과 다음 행동, 실패 시 마지막 완료 단계·재개 대상이다. ID·화면 수나 합의 자체를 과학적 결론의 근거로 세지 않는다.

## 6. 생산자 수정 판단과 이번 검증

**필수 수정 없음:** 현재 A1 응답만으로 위 상태 분기·원형 확보·후속 맥락을 처리할 수 있다. Pilot 자동 조정자 연결부터 진행할 수 있다. 새로운 사실상 계약이 필요해지면 method/path, 비밀 제거 응답, 기대/실제 상태와 보존된 참조로 협의한다.

**후속 제안:** 기계 판정 가능한 답변 coverage/귀속·엄격 source 범위는 합의된 analyze/result 단계에서 구현한다. 구조화 실행 실패 분류·진행 알림 등은 실제 왕복에서 기존 status/issues/dispatch_error로 처리하지 못하는 사례가 확인될 때 별도 제안한다. 이번 왕복 때문에 capability나 job 상태 의미를 바꾸지 않는다.

검토 기준 Atlas HEAD는 `a93e628513111fdbed11072c12e967424d8d473e`다. 이번에 `uv run --no-sync pytest -q tests/test_jobs.py tests/test_jobs_v1.py tests/test_server.py tests/test_server_v1.py`를 실행해 **52 passed, 2 warnings in 16.96s**를 확인했다. 임시 자료실·시험용 에이전트/서버를 사용하며 운영 LLM 작업은 제출하지 않았다. 경고는 기존 Starlette/httpx·anyio deprecation이다. 전체 Atlas 회귀나 Pilot 새 자동 왕복의 완료를 의미하지 않는다.

Pilot의 **671 passed in 1514.67s**는 이번 요청으로 전달받은 전체 회귀 결과이며 Atlas가 재실행한 결과가 아니다. [T1 구현·결과](pilot-t1-implementation.md)의 q1/q2 완료 기록을 읽었다. 그 문서 말미의 ‘전체 회귀 실행 중’ 문구보다 이번 Pilot 완료 통보가 최신이다. 과거 Atlas A1 배포 보고의 ‘T1 미실행’도 배포 당시 이력이며 현재 상태로 적용하지 않는다.

이번 변경은 이 회신 파일뿐이다. 기존 공동 계약, 운영 원본·QA·job, 실제 연구 단계·M1은 변경하지 않았다. 새 질문 제출·서비스 재시작·recover도 수행하지 않았다.

## 7. 추가 회신 — atlas_advance.py 첫 단위 검토

> 최초 검토 이력이다. 아래 AL-R1–R3의 현재 상태는 §8의 수정 재검토를 우선한다.

Pilot이 범위를 `advance_request`와 CLI `advance --watch`로 좁힌 뒤 최신 코드를 읽었다. 정상 active 대기, terminal QA 부재 needs_attention, 보존 QA/import 재개, 해시로 고정한 입력 재사용, scientific_review_completed=false의 경계는 방향에 맞다. 원격 작업을 시간으로 취소하지 않는 점도 현재 계약에 맞는다. 단, 다음 세 건은 **첫 단위에서 보완할 Important**다. Atlas 생산자 변경 요구는 아니다.

### AL-R1 · Important — 실행 오류도 정상 대기로 반환해 watch가 계속 조회

위치: `researchclaw/codex/atlas_advance.py::_advance`의 ACTIVE 분기(검토 시 45–46행), `atlas_service_cli.py::run`의 watch 반복.

queued/running이면 scheduled와 dispatch_error를 읽지 않고 waiting_for_atlas로 반환한다. 실제 A1은 실행 시작 실패 때 queued+dispatch_error, 실행기 연결 종료 때 running+dispatch_error를 반환한다. 이 경우 단순히 답변 생성이 오래 걸리는 상태와 다르며, 예약 또는 살아 있는 자식 에이전트 확인이 필요하다.

합성 재현: queued 및 running 각각에 scheduled=false, dispatch_error='worker stopped; inspect surviving child'를 넣었다. 두 경우 모두 waiting_for_atlas로 반환했다. watch는 이 stage에서 계속 sleep/조회하므로 오류를 진단 단계로 올리지 못한다.

필수 보완: 명시적 dispatch_error를 보존해 needs_attention 등 진단 상태로 반환하고 watch를 끝내도록 한다. queued+scheduled=false도 예약 부재로 구분해 원인 확인·명시적 재예약 경로로 넘긴다. 필드 누락과 명시적 false를 구분하며, running+scheduled=false만으로 프로세스 사망을 단정하거나 recover하지 않는다. 정상 running 대기와 오류/예약 부재를 각각 시험한다. 원격 취소나 임의 timeout 추가가 해결책은 아니다.

### AL-R2 · Important — 실패 원인과 생산자 참조가 고정 공통 입력에서 빠짐

위치: `atlas_advance.py::_advance`의 packet 구성(검토 시 58–67행).

packet은 atlas_status와 QA를 넣지만 관측한 job ID/request_sha256/receipt_ref 및 detail.issues/error·dispatch_error를 포함하지 않는다. request_key로 현재 journal을 찾을 수는 있어도, packet만으로 무엇 때문에 partial/failed였는지와 어느 job/receipt를 검토했는지 고정되지 않는다. 이후 검토자가 가변 journal을 따로 읽으면 ‘같은 고정 공통 입력’의 경계도 약해진다.

합성 재현: 유효 QA가 있는 failed job에 issues=['ask changed readonly wiki'], error='worker failed'를 넣고 advance했다. review_input_ready packet에는 failed 문자열은 남지만 해당 실패 사유와 명시적인 job/receipt 참조는 없었다. scientific_review_completed=false는 과학 검토 미완료 표시이며 실패 사유 보존을 대신하지 않는다.

필수 보완: 검증된 job/receipt 참조와 원래 status, 보존·검토에 필요한 issues/error/dispatch 상태를 packet 안의 허용된 필드로 고정한다. 실패 QA는 진단/제한 검토 입력임을 명시하고, 치명적인 보존 위반을 정상 completed QA와 구분할 수 있게 한다. 토큰·로컬 실행 로그/임의 경로를 통째로 복사하지 않는다. 적어도 partial·failed의 사유가 packet만으로 확인되고, journal의 이후 조회/변경에도 고정 packet이 달라지지 않는지 검증한다.

### AL-R3 · Important — cached/received 경로가 terminal 확인을 건너뜀

위치: `atlas_advance.py::_advance`의 received/qa_envelope 분기(검토 시 40–53행).

현재 상태 확인은 received=false이고 qa_envelope도 없을 때만 수행한다. 기존 수동 receive 기능은 terminal 여부를 연구 사용 조건으로 강제하지 않으므로, 그 경로에서 active job의 진단 QA를 이미 수신한 경우 advance가 바로 packet을 만든다. cached QA 경로에도 같은 우회가 있다.

합성 재현: 유효 qa_ref를 가진 job을 running으로 두고 기존 session.receive()를 호출한 뒤 advance_request()를 실행했다. 결과는 stage=review_input_ready, packet.atlas_status=running이었다. 이는 정상 새 경로에서 active의 QA를 최종 입력으로 삼지 않는 기존 테스트의 취지를 우회한다.

필수 보완: packet을 처음 고정하기 전에 received/cached 여부와 무관하게 저장된 job 상태가 알려진 terminal인지 검사한다. 이미 관측·검증한 terminal 결과와 보존 QA이면 네트워크 없이 재개하는 장점은 유지한다. 저장 상태가 active라면 필요 시 상태만 재조회하고 active 동안은 입력을 고정하지 않는다. 알 수 없는 상태는 오류로 분기한다. 기존 frozen packet의 불변 재사용은 유지하되 이 수정 때문에 운영 QA/job을 수정하지 않는다.

추가 시험: 수동 receive 또는 import 실패 후 qa_envelope만 남긴 active 경로에서 review_input_ready를 만들지 않는지, terminal cached QA의 offline import/packet 재개는 유지되는지 확인한다.

### 이번 단위 검증 범위

- Pilot의 `tests/codex_native/research_graph/test_atlas_advance.py` 테스트 함수를 파라미터 조합 포함 **11개 직접 호출해 모두 통과**했다. 임시 실경로 연구 폴더·MonkeyPatch·합성 Atlas만 사용했고 pytest 전체 실행은 아니다.
- 그 외 위 AL-R1의 두 상태, AL-R2의 실패 사유 유실, AL-R3의 기존 수신 경로 우회를 별도 임시 연구에서 재현했다. 운영 API·기존 T1·실제 연구에는 접근하지 않았다.
- 이 결과는 Pilot이 진행 중인 첫 단위의 읽기 검토이며, 독립 의견 생성·후속 질문 제출 기능까지 구현됐다는 의미가 아니다. 공동 L01/L06/L08의 전체 왕복 검증은 그 후속 단위에서 수행한다.
- 필수 수정 이후 같은 문서에 해소/잔여 상태를 추가할 수 있다. 이번 검토에서는 소비자 코드도 수정하지 않았다.

검토 시 SHA-256:

- atlas_advance.py: `1e4c5b5b48106d2b0dfa8c59506b3a139bbc8831460c488034f479308aebd02d`
- atlas_service_cli.py: `14ce3688aa834afca754c925cbfed6f485d64cc91f5f5b8b74419748d686b550`
- atlas_session.py: `1afd83492cfa1d2b00c7db3e482403e6c0d932d1381a84efa4742d2277dab2eb`

## 8. 추가 회신 — AL-R1–R3 수정 재검토

2026-09-13. Pilot 수정 통보 후 최신 `atlas_advance.py`, 해당 테스트 및 [자동 왕복 작업 단위](pilot-atlas-loop.md)를 읽었다. **AL-R1–R3 모두 해소를 확인했으며, 첫 단위에 남은 필수 문제는 이번 검토 범위에서 발견하지 못했다.** 생산자 변경도 필요하지 않다.

| 항목 | 수정 확인 |
| --- | --- |
| AL-R1 | 최상위/detail의 명시적 dispatch_error 및 queued의 명시적 scheduled=false를 needs_attention으로 반환한다. 필드 누락과 false를 구분하며, 오류 없는 running+scheduled=false는 사망으로 단정하지 않고 대기한다. CLI watch는 needs_attention에서 종료한다. |
| AL-R2 | 새 schema_version=2 packet의 execution에 job ID·receipt·request_sha256·issues/error·dispatch 상태와 검토 목적을 보존한다. failed/partial/interrupted는 diagnostic_or_limited_review이고 과학 검토 완료 표시는 false다. 이후 journal의 실패 사유가 달라져도 이미 고정한 packet은 유지된다. |
| AL-R3 | 첫 freeze 전 cached/received 경로도 terminal 여부를 확인한다. 저장 상태가 active이면 다시 관측하고 active 동안은 입력을 고정하지 않는다. 알 수 없는 cached 상태도 거절한다. 이미 검증·보존한 terminal QA의 offline import 및 입력 준비는 유지한다. |

검증은 기존 방식대로 임시 연구 폴더와 합성 Atlas 응답을 사용했다. 운영 q1/q2·QA·원본·job을 조회하거나 변경하지 않았다.

- 최신 `test_atlas_advance.py`의 테스트 함수를 파라미터 조합 포함 **23개 직접 호출해 통과**했다. Pilot이 보고한 22개와 별도로, 이번에 로드한 파일에서 호출한 수다. 전체 Pilot pytest 실행 결과로 확대하지 않는다.
- 추가 경계 확인 **7개 통과**: detail 내부 dispatch_error, 오류 없는 running+scheduled=false, partial에 QA 없음, 알 수 없는 cached 상태, 실제 head_conflict 후 cached terminal QA의 offline import/입력 준비, failed 사유·receipt·fingerprint·검토 목적 고정과 이후 journal 변경, schema 1 객체의 불변 재사용.
- schema 1 보존 확인은 별도로 만든 합성 과거 packet으로 수행했다. 기존 객체 바이트·해시와 연구 HEAD를 유지하고 네트워크 없이 같은 schema 1을 반환했다. 새 packet은 schema 2로 생성한다. 실제 T1에 생성한 schema 1 두 객체의 보존은 Pilot 보고이며 이번에 직접 재조회하지 않았다.

schema 1의 불변 재사용은 의도된 호환 동작이다. execution 필드가 없는 과거 packet을 schema 2로 이미 보강된 입력처럼 취급하지 않는 것은 후속 검토 실행 연결의 버전 처리 사항이다. 이번 첫 단위에서 기존 객체를 덮어쓰거나 자동 council/후속 질문을 구현할 필요는 없다. 새 입력 버전 생성과 실제 검토 연결은 Pilot 문서의 후속 단위로 유지한다.

검토 입력 준비는 연구 사용 승인·독립 검토 완료·M1 완료가 아니다. 이번 결과로 첫 단위의 생산자 의미 검토를 마무리할 수 있으며, 다음 구현 범위의 완료를 대신 선언하지 않는다. 이번 수정도 이 회신 문서에만 반영했다.

재검토 기준 SHA-256:

- atlas_advance.py: `cc2ecbc3157e28bf1755b93372185e3c8fa6e88677a3e910f595ee55db78ce25`
- atlas_service_cli.py: `14ce3688aa834afca754c925cbfed6f485d64cc91f5f5b8b74419748d686b550`
- atlas_session.py: `1afd83492cfa1d2b00c7db3e482403e6c0d932d1381a84efa4742d2277dab2eb`

## 9. 첫 단위 공동 완료 확인

2026-09-13. Pilot의 최종 완료 통보와 갱신된 [pilot-atlas-loop.md](pilot-atlas-loop.md)를 확인했다. **첫 단위 ‘답변 재개와 입력 고정’의 공동 검토를 완료한다.** §8의 AL-R1–R3 해소 및 남은 필수 문제 없음 판단을 유지한다.

- Pilot 최종 관련 회귀: **117 passed in 5.16s**, diff check 통과로 전달받았다. Atlas가 재실행한 결과가 아니며 §8의 23개+7개 확인이나 이전 전체 회귀 671개와 합산하지 않는다.
- 기존 실제 T1 두 QA의 재사용 시험, schema 1 시험 객체 보존, 신규 schema 2의 실행 진단 추가를 구분해 기록했다. 신규 운영 ask·연구 판단·UI 배포는 수행하지 않았다는 Pilot 보고를 확인했다.
- 다음은 **정식 쟁점·질문 참조와 의뢰 목적을 연결하는 Pilot 작업**이다. council·후속 실행·전체 왕복 및 UI는 후속 단위다. 첫 단위 완료를 과학 검토·연구 사용 승인·M1 완료로 확장하지 않는다.

이번 마무리는 회신 기록만 갱신했다. 추가 테스트·질문 제출·서비스 조작·운영 데이터 또는 계약 변경은 하지 않았다.

## 10. 단위 2–3 소비자 코드 검토

2026-09-13. Pilot 요청에 따라 `atlas_question.py`, `atlas_council.py`, `atlas_reviewer.py`, `atlas_session.py`의 연구 맥락 고정, `external_evidence.py`의 정식 external_question 참조 수용을 읽었다. 연결되는 advance·기존 council 공개 규칙·원기록 검증도 확인했다. **이번 검토 범위에서 단위 2–3에 남은 필수 수정은 확인하지 못했다. Atlas 생산자 변경도 필요하지 않다.**

운영 ask `job-a69f83d2ddcd4758`은 조회·변경·재실행하지 않았고 새 운영 질문을 제출하지 않았다. 실제 응답의 내용 평가나 실제 CLI 9발언 실행 검증을 이번 코드 검토 결과로 대신하지 않는다.

### 확인한 동작

| 대상 | 확인 내용 |
| --- | --- |
| 정식 질문·결정 연결 | 검증된 view의 external_question과 연결 결정에서 질문·부족한 근거·판단 영향·범위·기존 결론/한계를 구성한다. question_ref·정식 원기록·selected_head를 연구 맥락으로 전송 전에 저장한다. 같은 키 재시도는 이후 연구 기록이 추가돼도 기존 payload를 유지한다. |
| Atlas 계약과 연구 맥락 분리 | research_context는 Pilot journal/고정 입력에 보존하며 미지원 Atlas payload 필드로 보내지 않는다. 실제 question은 자체 완결 텍스트이고 client_context의 question_id는 추적 참조다. 같은 키로 질문 ID/previous/연구 맥락을 바꾸는 충돌을 거절한다. |
| 정식 external_question 참조 | 기존 external_evidence/M1 question 참조의 호환성을 유지하면서 external_question의 같은 프로젝트·head·해시와 native 작성 이력을 검증한다. 잘못된 참조가 external.review를 생성하지 못하는 것을 확인했다. |
| 세 역할의 단계별 공개 | 각 phase에서 세 참여자의 packet을 먼저 보존하고 세 reviewer 결과가 모인 뒤 제출한다. initial에는 미공개 동료 초기 의견이 없고, response에는 초기 3개, final에는 응답 3개를 제공한다. 기존 council 공개 장벽을 재사용한다. |
| 영속 재개 | payload/receipt/participant packet/검증된 역할 결과를 보존하고 고정 command_id로 제출한다. 역할 일부 완료 후 실패 및 첫 발언 등록은 됐지만 receipt 저장 전 응답이 유실된 경우, 완료 역할을 다시 실행하거나 제출을 중복하지 않고 재개했다. |
| CLI 결과·접근 감사 | 별도 역할/phase 실행 폴더에 prompt·materials·schema·events·answer·activity를 보존한다. 이벤트에서 도구 item·오류·미완료를 거절하고 phase별 recommendation을 검증한다. 완료 exit=0 원응답을 검증 결과 저장 전에 중단한 경우 재실행 없이 다시 읽는다. 실행 중/실패한 시도는 진단 대상으로 남긴다. |
| 완료 의미 | council_complete는 최종 3개를 포함한 총 9개 발언 등록 완료다. external.review의 limited는 명시된 공백·적용 범위 검토용 입력 선언이며, 직접 원문 검증이나 조건 확정이 아니다. 기존 쟁점을 해결하거나 새 external.decision/M1 완료를 자동 생성하지 않는다. 최종 결정은 Pilot의 다음 단계다. |

역할별 packet에는 본인 assignment와 공개 허용 의견이 들어가므로 전체 packet 바이트가 역할 간 동일하다는 뜻은 아니다. 과학 검토에 제공하는 공통 MATERIALS는 같은 고정 입력이고, 단계별 공개와 본인 정보는 기존 council 규칙을 따른다.

독립성은 지시 수준이며 강한 파일 접근 격리·다른 모델의 독립성 보장이 아니다. read-only sandbox만으로 읽기를 차단한다고 주장하지 않고, 도구 사용을 지시로 금지하고 관측 이벤트를 사후 거절하는 현재 표현을 유지한다. 이번 검토는 감사 코드와 합성 이벤트를 확인했으며 실제 실행에서 모델이 도구를 쓰지 않았는지는 해당 실행 원기록으로 판단한다.

### 검증과 한계

- `test_atlas_question.py`, `test_atlas_council.py`, `test_atlas_reviewer.py`의 최신 테스트 함수를 임시 연구 폴더에서 **9개 직접 호출해 통과**했다. 검토 중 추가된 완료 host 원응답 재사용 시험도 포함한다. 실제 Atlas는 합성 응답, reviewer는 합성 콜백/이벤트이며 실제 Codex CLI를 새로 실행하지 않았다.
- **추가 확인 7개 통과:** 첫 council.submit이 정식 저장된 직후 receipt 응답 유실 → 총 9개 역할 호출/9개 제출/최종 3개로 재개 1개; external_question의 잘못된 project_id/sha256/head_id 거절과 HEAD 불변 3개; 실행 중·실패 host 및 도구 사용이 있는 완료 host의 재개 거절/원형 보존 3개.
- 재개 시험에서 기존 decision 수는 1개로 유지됐다. 새로운 판단·쟁점 해결을 대신 만들지 않는 경계도 확인했다.
- 소비자 전체 회귀·실제 LLM 응답 내용·새 왕복의 연구 결정·UI 배포를 검증한 결과는 아니다. 코드·원형 보존·단계 공개가 맞는다는 사실과 과학적 주장/반론의 적절성은 구분한다.
- 이번 변경은 이 회신 파일뿐이다. 다섯 소비자 구현 파일, 운영 서비스·원본·QA·job·실제 연구 단계는 수정하지 않았다.

다음 실제 응답 검토에서는 Abbasi의 전극 배치·전류 경로·시편/유동 방향 대응을 확인한 근거와 미확인 부분이 구분되는지, 같은 QA를 읽은 검토자들의 동의를 독립 실증 근거로 세지 않는지, 자료 확보 필요/정량 전이 보류를 이유 있게 결정하는지를 확인하면 된다. 이 내용은 이후 실제 응답 검토의 초점이며 현재 필수 코드 수정 요청은 아니다.

검토 기준 SHA-256:

- atlas_question.py: `65e1677bed38f8067f30c730b554979d2b3e9a860ecb6f480a5f6bbb89733a6f`
- atlas_council.py: `4bdcf4e0619111693af60669efc7085bdc7be4eadfd1fa68606ee646c558f573`
- atlas_reviewer.py: `702ca463eb91df17b942b201e8854b0f0624409fb6ad8c60fd3afb187f7c656c`
- atlas_session.py: `ce982aecbf0e912cff08e733284be7967d693106fed7e216509c0b79504346af`
- external_evidence.py: `aff482f0e60eeef7cd5d5e2b5a4cf336ee078f0d8aa2e21d4ef7faf2fced9c14`

## 11. outcome adapter 추가 검토

> 최초 검토 이력이다. O-R1은 아래 §12의 수정 재검토에서 해소됐다.

2026-09-13. `atlas_outcome.py`와 연결된 기존 decision/question 등록·council 결과를 읽었다. **필수 보완 Important 1건(O-R1)을 재현했다.** 생산자 API 변경은 필요하지 않다. 아래 내용은 outcome adapter에 한정하며 앞선 단위 2–3 검토를 뒤집는 것이 아니다.

### O-R1 · Important — 유효하지 않은 prior_ref가 입력을 선점해 정정·재개를 막음

위치: `atlas_outcome.py` 20행의 prior_ref 검사, 32행의 outcome-input 저장, 46–48행의 정식 decision 등록.

prior_ref는 dict인지 여부만 먼저 검사하고, 정식 참조 필드·동일 프로젝트·head·해시·정식 decision 확인은 뒤의 external.decision.record에서 수행한다. 그런데 그 전에 outcome-input.json을 고정한다. 따라서 잘못된 참조는 연구 결정으로 등록되지는 않지만, 같은 요청의 정상적인 정정 입력도 변경 충돌로 막는다.

합성 재현:

1. 별도 임시 연구에서 council의 9발언·최종 3개를 완료했다.
2. 그 외 유효한 outcome에 prior_ref={}를 넣어 호출 → external_decision_prior_invalid로 거절.
3. 연구 HEAD는 그대로지만 outcome-input.json에는 prior_ref={}가 남았다.
4. prior_ref=None으로 고쳐 같은 요청에 호출 → atlas_outcome_conflict. 잘못된 입력이 수락되지 않았는데도 수정이 불가능하다.

필수 보완: 최초 outcome 입력을 수락·고정하기 전에 형식과 정식 참조를 읽기 전용으로 검증한다. 기존 도메인 검증을 재사용할 수 있으며, 적어도 잘못된 prior_ref 필드/해시/프로젝트/대상은 입력을 선점하지 않아야 한다. 검증 거절 이력을 보존하더라도 실제 수락한 불변 입력과 구분한다. 한 번 유효하게 수락돼 등록을 시작한 입력의 변경 충돌 및 동일 입력 재개는 그대로 유지한다. 이미 남긴 운영 원기록을 삭제하거나 덮어쓰라는 요청은 아니다.

같은 선검사에서 next_action의 문자열 타입을 membership 검사보다 먼저 확인하는 보완도 필요하다. 현재 next_action=[]는 atlas_outcome_invalid 대신 TypeError: unhashable type: 'list'가 발생한다. 이 경우 쓰기는 없었으며 별도 Important로 중복 집계하지 않는다.

수정 검증 기준: 잘못된 prior_ref를 거절한 뒤 유효하게 고친 동일 key 입력을 수락할 수 있고, 그 전에는 연구 결정/질문 및 수락 입력이 생성되지 않는다. 유효 입력의 성공 후 내용 변경은 계속 atlas_outcome_conflict다. malformed next_action도 일관된 입력 오류로 반환한다.

### 정상 경로 확인과 검토 범위

- `test_atlas_outcome.py`의 기존 테스트 **2개 직접 호출 통과**: 완료 council 필요·최종 참조 보존·동일 입력 재사용/변경 충돌, 잘못된 다음 질문의 선제 거절.
- **추가 재개 확인 3개 통과**: decision 정식 등록 직후 receipt 응답 유실, 다음 question 등록 직후 receipt 응답 유실, outcome-result 저장 후 journal 반영 실패. 각각 같은 입력으로 재개했으며 decision/question은 각 1개만 추가되고 최종 3개 참조와 다음 질문의 decision_ref가 유지됐다.
- followup_atlas와 next_question을 기록해도 모델 ask를 자동 제출하지 않는 것을 확인했다. 합성 Atlas job 수는 증가하지 않았다.
- 미완료 council을 정상 완료로 만들거나 최종 발언에서 결론을 자동 합성하지 않는다. title/conclusion/rationale/limitations와 다음 행동은 조정자가 제공한다. 실제 최종 3개 발언과 결론이 내용상 맞는지는 Pilot의 실제 판단 단계에서 확인한다.
- 오류 재현 및 재개 검증은 모두 임시 연구·합성 응답/검토자를 사용했다. 실제 response 회차·최종 발언·운영 QA·D2 설계·다음 자료 확보를 조회/변경하거나 대신 결정하지 않았다. 이 회신 파일 외 구현 파일도 편집하지 않았다.

Pilot이 전달한 ‘압축원판 두께축은 확인, 사출 전극은 미확인’과 D2 x방향 유지/문헌 z방향 직접 등치 보류 가능성은 진행 공유로만 이해한다. 이번 adapter 코드 검토가 해당 과학적 결론의 승인이나 실제 outcome 기록을 대신하지 않는다.

검토 기준 SHA-256:

- atlas_outcome.py: `ce0e320ea5cd11a3100697d37fceccc5ee37e3b0fdc27056972205f580fdd53a`
- atlas_council.py: `4bdcf4e0619111693af60669efc7085bdc7be4eadfd1fa68606ee646c558f573`
- external_evidence.py: `aff482f0e60eeef7cd5d5e2b5a4cf336ee078f0d8aa2e21d4ef7faf2fced9c14`

## 12. O-R1 수정 재검토 — 해소

2026-09-13. 최신 `atlas_outcome.py`에서 최초 outcome-input 저장 전에 기존 pure `record_decision`으로 정식 참조와 decision 입력을 검증하는 것을 확인했다. **O-R1은 해소됐다.** next_action도 문자열 타입을 먼저 검사한다.

- 최신 outcome 테스트 **3개 직접 호출 통과**: prior_ref={} 거절 시 수락 입력/연구 결정 미생성 → 같은 key의 정상 입력 성공, 성공 후 동일 입력 재사용·변경 충돌, 잘못된 후속 질문 선검사 및 next_action=[]의 일관된 입력 오류.
- 추가 확인 **1개 통과**: 유효한 정식 prior_ref로 decision을 등록한 직후 receipt 응답이 유실돼도 같은 입력으로 중복 없이 재개한다. 기존 결정과 prior_ref를 유지하고 새 ask를 만들지 않았다.

검증은 임시 연구·합성 Atlas/council로만 수행했다. Pilot이 통보한 실제 outcome `e397a1c6-ec80-5036-96ed-c8ed9c64cf0c` 및 HEAD `f085ff7e3fcb8c4ae2bf2e3f4df96483b3abfe3cdb9c26f0fa40be8368e6f529`는 운영 기록 보고로 수신했으며, 직접 조회·변경하거나 판단을 재작성하지 않았다. 이번 확인은 O-R1 해소에 한정한다.

검토한 atlas_outcome.py SHA-256: `1ab9cc0e5ebeb06317114ee6754b463ae90b5cf9de6fb29c120b84ce292331a9`. 이 회신 문서 외 파일은 수정하지 않았다.

## 근거 파일

- [공동 계약 v1](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1.md): 책임, A1/후속 capability, 범위·실패·복구 계약.
- [server.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/server.py): JobRequest, public_job, v1 접수·상태·execute.
- [jobs.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/jobs.py): 동일 키/receipt, 범위 검증, recover.
- [service_worker.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/service_worker.py): 명시적 예약, scheduled/dispatch_error, 재시작 시 미재생.
- [job_runner.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/job_runner.py), [job_results.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/job_results.py): 모델 입력에서 client_context 제외, QA·보존 검증, terminal 판정.
- [service.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/service.py), [knowledge_export.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/knowledge_export.py): capability, raw/해시/QA 오류.
- [wiki-ask 스킬](/Users/jspark/orca/projects/ResearchAtlas/.agents/skills/wiki-ask/SKILL.md): 프로젝트 고정 버전·supplementary·원문 확인·후보와 위키 구분.
- [test_jobs.py](/Users/jspark/orca/projects/ResearchAtlas/tests/test_jobs.py), [test_jobs_v1.py](/Users/jspark/orca/projects/ResearchAtlas/tests/test_jobs_v1.py), [test_server.py](/Users/jspark/orca/projects/ResearchAtlas/tests/test_server.py), [test_server_v1.py](/Users/jspark/orca/projects/ResearchAtlas/tests/test_server_v1.py): 이번 52개 검증; QA 없는 정상 실행의 partial 및 과거 completed 원형 부재 포함.
- [Pilot 소비자](../../../researchclaw/codex/atlas_session.py), [이전 Atlas 재검토](atlas-pilot-implementation-reply.md): 고정 payload·후속 조합·수신/import 재개와 R1–R4 해소.
