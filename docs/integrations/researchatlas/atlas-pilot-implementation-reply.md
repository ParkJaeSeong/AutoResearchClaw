# Atlas 회신 — Pilot P0–P3 HTTP 구현

2026-09-13. 요청한 소비자 구현 범위와 기존 프로젝트 ask 1건→후속 질문 1건의 T1에 이견 없습니다. **Atlas 운영 서버를 유지합니다.** 이 회신에서는 코드·설정·서비스 재시작·질문 접수를 수행하지 않았으며 info/projects/jobs만 읽었습니다. 실제 질문 제출과 Pilot 등록은 Pilot 담당이 수행합니다.

## 현재 운영 확인

- 주소: `http://127.0.0.1:18765`
- 연결 파일: `/Users/jspark/orca/projects/ResearchAtlas/output/atlas-18765.json` (본인 소유·0600, `{url,token}`)
- 계약: `pilot-atlas/1.0`
- instance: `4578a369-9f11-45b0-adb7-f95704aebfc9`
- capabilities: `service_identity_v1`, `qa_export_v1`, `page_raw_v1`
- 기존 프로젝트: `project-95e043c2a0c341af` · **고분자 복합재 연구**
- 이번 조회 시 delegated jobs는 빈 목록입니다. 실행 직전 현재 상태는 다시 조회하세요.
- 운영 코드 `1e20cd2`, A1 문서 기록 `a93e628`. [검증 보고서](/Users/jspark/orca/projects/ResearchAtlas/docs/evaluations/pilot-a1-t1-2026-09-13.md): 테스트259개, 실제 합성 Codex ask, HTTP/MCP 원형·동시 재전송·Pilot 파서 호환 검증 완료. 실제 Pilot 연구 import·T1은 아직 별도입니다.

## 연결과 UI

Pilot **백엔드에서 Atlas HTTP를 호출**하세요. Pilot 브라우저 UI가 다른 포트의 Atlas API를 직접 호출하면 Origin/cross-site 검사로 거절됩니다. Pilot 브라우저의 Origin/Host 헤더를 Atlas에 전달하지 않고, 연결 파일의 로컬 주소와 Bearer 토큰으로 서버 간 요청합니다. 토큰을 UI·연구 기록·로그·예외 원문·URL에 넣지 않습니다. `/api/session`은 Atlas 자체 UI용이며 Pilot 연결 정보 조회 방식으로 쓰지 않습니다.

info로 instance와 capability를 확인한 뒤 projects의 `{id,title}` 목록을 선택합니다. 프로젝트 목록 등 legacy 조회에는 최상위 instance가 없으므로 같은 연결의 info와 묶어 보존하세요. URL/토큰 변경만으로 새 자료실이라고 보지 않으며, instance 불일치는 자동 재바인딩하지 않습니다. 현재 프로젝트는 접근 권한 경계가 아닙니다.

## ask 접수·영수증·재개

실제 지원하는 최소 요청 예시입니다. request_key와 client_context 값은 Pilot이 자기 기록에서 발급하세요. 아래 예시 자체는 실행하지 않았습니다.

```json
{
  "contract_version": "pilot-atlas/1.0",
  "kind": "ask",
  "request_key": "pilot-t1-example-q1",
  "question": "동일한 CNT 함량에서 성형 조건에 따른 전기전도도 차이를 배향만으로 설명할 수 있는가? 공정 변화와 측정 방향을 구분하고 저자 해석과 Atlas 판단을 나눠줘.",
  "project": "project-95e043c2a0c341af",
  "client_context": {
    "pilot_project_id": "pilot-project-example",
    "question_id": "question-example",
    "issue_id": null,
    "round_id": "round-example",
    "binding_ref": "binding-example"
  },
  "execute": true
}
```

| 응답 위치 | 실제 필드 |
| --- | --- |
| POST `/api/jobs` 최상위 | `ok,contract_version,atlas_instance_id,request_key,request_sha256,receipt_ref,exists,job` |
| GET `/api/jobs/{id}` 최상위 | `ok,contract_version,atlas_instance_id,job` — 여기에는 최상위 receipt/exists가 없음 |
| `job` | `id,status,created_at,updated_at,payload,detail,scheduled,dispatch_error`; v1 job은 `contract_version,atlas_instance_id,request_key,request_sha256,receipt_ref`도 포함 |
| 완료 ask의 `job.detail` | `answer,issues,qa_id,qa_path,qa_ref,consulted_pages` 및 실행 범위 정보. 실패/미완료에서는 일부가 없을 수 있음 |
| `receipt_ref` | `{atlas_instance_id,operation:"jobs.submit",request_key,request_sha256}` |
| `qa_ref` | `{qa_id,sha256}` |
| `consulted_pages[]` | `{path,page_id,sha256}` — 참고 당시 전체 페이지 해시 |

접수 POST는 현재200을 반환합니다. execute=true여도 최초 응답의 job.status가 queued일 수 있고, scheduled는 일시적인 실행 예약 상태입니다. 후속 GET의 job.status를 기준으로 판단하세요. API ok=true는 조회/접수 성공이며 연구 완료를 뜻하지 않습니다.

전송 전에 원래 question/project/client_context/request_key와 실행 의사를 영속화하세요. HTTP 응답 유실 시 **같은 payload·키**로 재전송하면 같은 job·영수증을 회수합니다. 재전송에서 execute만 바꾸는 것은 허용하며, queued일 때만 실행을 요청합니다. completed/partial/failed/interrupted는 같은 키로 재실행하지 않습니다. 다른 내용·문맥은 새 키입니다. legacy 키를 v1으로 바꾸어 재사용하면409입니다.

client_context는 다섯 필드의 문자열/null만 허용합니다. 객체 안의 생략 필드는 null로 정규화합니다. client_context 자체의 생략/null과 빈 객체 `{}`는 다른 payload입니다. 질문의 공백·개행을 자동 정규화하지 않습니다. 서버가 반환한 request_sha256을 보존하고, 로컬 JSON 문자열의 단순 해시와 같다고 가정하지 마세요.

현재 요청 한도는 request_key 1–256자, question 최대32,000자입니다. ask에서 items는 생략/빈 목록, retry는 생략/false여야 합니다. 프로젝트 null은 일반 질문으로 허용하지만 T1은 명시적으로 선택한 프로젝트를 사용합니다. 잘못된 project를 null로 바꾸지 않습니다.

서버 재시작 시 queued/running을 자동 재개하지 않습니다. 응답 유실 재시도와 interrupted 작업의 재실행은 별개입니다. 종료 여부와 dispatch_error를 읽고 필요하면 협의하세요. 단일 요청 HTTP timeout을 모델 작업 전체의 실패로 바꾸지 않습니다. 현재 취소/SSE/WebSocket API는 없으며 상태를 주기적으로 조회합니다.

`POST /api/jobs/{id}/execute`는 예약 중인 같은 job에는 중복 예약하지 않지만, 실행 예약이 끝난 terminal job에는400을 반환할 수 있습니다. T1의 응답 유실 복구는 원래 v1 submit을 같은 키로 재전송하는 경로가 적합합니다. request_key만으로 조회하는 별도 GET endpoint는 없습니다.

## QA·페이지·source 원형 수신

QA는 `GET /api/qa/{qa_id}?expected_sha256=...`로 받습니다. 응답은 공통 v1 envelope와 `qa_id,raw,record,lifecycle`입니다. raw는 `{encoding:"base64",content_base64,size_bytes,sha256}`이며 **디코딩한 원형 바이트를 그대로 저장**한 뒤 길이/해시를 확인하고 기존 parse_atlas_qa/import 경로로 연결하세요. 재직렬화한 record, answer 문자열, 내부 input_sha256은 원형 파일 해시가 아닙니다.

QA raw/record와 현재 lifecycle은 별개입니다. `include_lifecycle=false`이면 null이며, true에서 이력이 손상되면 `{available:false,status:null,candidates:[],error:...}`로 정상 raw/record와 함께 반환합니다. lifecycle 안의 error는 `error_code,error,retryable,details`의 부분 오류이며 최상위 계약/instance가 반복되지 않습니다. 과거 QA 파일은 archive 전환 후에도 불변입니다.

QA·페이지 원형 상한은 디코딩 기준 **10,485,760바이트 포함**입니다. 전체 JSON 응답은 base64와 record 때문에 이보다 큽니다. 수신 버퍼/응답 한도를 원형 한도와 동일하게 잡지 마세요. 초과는413이며 details의 `size_bytes,max_bytes,raw_available:false`를 읽습니다. 이것으로 completed job을 실패 처리하거나 원형을 잘라 import하지 않습니다.

페이지는 `GET /api/pages/{page_id}?include_raw=true&expected_sha256=...`로 조회합니다. 최상위 식별 필드는 `id`이고, 전체 파일 해시는 `sha256` 및 `raw.sha256`입니다. 기존 markdown은 YAML 제외 본문입니다. 참고 당시 해시와 현재 파일이 다르면409 changed_page이며 **과거 페이지 snapshot 조회 API는 없습니다**. 현재 페이지로 조용히 교체하지 말고 수신하지 못한 옛 근거로 표시하세요. 페이지 카탈로그 조회는 다른 위키 기록의 구조 오류에도 영향을 받을 수 있습니다.

원본 source는 legacy 응답 형태가 다릅니다.

| 경로·필드 | 실제 의미 |
| --- | --- |
| `page.source_refs[]` | `{source_id,version,title}`; 여기에는 원본 sha256이 없음 |
| `GET /api/sources/{source_id}/versions/{version}?offset=0&limit=262144` | 최상위 `ok,source_id,version,title,sha256,media_type,size,content_base64,offset,next_offset,eof` |
| source의 `size` | 원본 전체 바이트 수. `size_bytes`가 아님 |
| source의 `sha256` | 원본 전체 파일 해시. 현재 묶음의 해시가 아님 |
| source의 `content_base64` | 해당 offset의 바이트 묶음. `raw` 객체나 encoding 필드는 없음 |
| `GET .../file` | 원본 전체 바이너리, `X-Source-Sha256` 헤더. 별도 metadata 응답의 size와 수신 바이트 길이를 대조 |

HTTP 소비자는 metadata 묶음 조회로 version/hash/size를 확인하고 `/file`로 원형을 받아 대조할 수 있습니다. 묶음 방식이면 next_offset/eof를 따라 합친 전체 길이·해시를 검증합니다. 매 source 조회는 서버에서 전체 원본을 읽어 해시를 검증하므로 작은 묶음으로 반복할수록 비용이 늘어납니다. source 응답에는 v1 envelope/instance가 없으므로 같은 연결의 info와 결합합니다. 파일명이나 로컬 qa_path/path를 네트워크 자원 ID 대신 사용하지 않습니다.

새 job의 qa_ref는 완료 시 보존합니다. 기존 legacy job의 읽기 전용 참조 보완은 파일 누락/불일치 때문에 실패할 수 있고, 그때 없는 qa_ref를 만들지 않습니다. 보존된 qa_ref가 있더라도 QA 조회의404/413은 별도로 처리하세요. QA 파서 호환과 실제 원문 확인·주장의 과학적 타당성은 별도 판단입니다.

## 후속 질문의 중요한 제약

**현재 ask는 호출마다 독립 실행입니다.** client_context는 Pilot의 불투명 연결 참조이고 모델 프롬프트에 넣지 않습니다. 같은 question_id/round_id/binding_ref를 보냈다고 이전 답변을 자동으로 읽거나 대화가 이어지지 않습니다.

후속 질문은 새 request_key를 사용하고, question에 이전 질문에서 확인한 핵심 쟁점·필요한 인용/QA 참조·이번에 확인할 내용을 자족적으로 적어 주세요. 원래 Q1/Q2 및 연결 이력은 Pilot에 보존합니다. 이전 답변 전문을 무조건 복사하기보다 이번 질문에 필요한 근거와 한계를 명시하되, 미공개 독립 의견은 보내지 않습니다. `messages`, `previous_qa_ref`, `previous_result_ref` 같은 새 ask 필드는 현재 지원하지 않아400입니다.

ask는 보유 위키·원문을 확인하고 신규 QA/후보를 보존할 수 있지만 위키·색인을 편집하지 않습니다. 외부 탐색·다운로드·documents 호출은 위임 실행 범위에서 제외됩니다. 자동 ingest·업로드·프로젝트 쓰기·지정 source analyze는 이번 A1에 없습니다. source 목록을 엄격하게 고정하는 분석은 후속 analyze 계약 범위이며, ask의 project는 검색 문맥입니다.

## 오류 처리와 T1 기록

v1 info/QA/page raw/job의 새 오류는 `{ok:false,contract_version,atlas_instance_id,error_code,error,retryable,details}`를 반환합니다. 인증/Host/Origin 오류도 구조화됩니다. 다만 stats/projects/search/source 등 legacy 조회의 모든 오류에 같은 envelope가 있다고 가정하면 안 됩니다. 비JSON 응답·연결 끊김도 전송 오류로 구분하세요. source 무결성 불일치는 현재409 changed_source이며 legacy 코드입니다. v1 ingest/analyze는503 capability_unavailable, 알 수 없는 버전은400 unsupported_contract_version입니다.

T1에서는 두 질문 각각의 사전 저장 요청→job/receipt→QA 원형 해시→참고 페이지·source의 수신/미수신 결과→Pilot import ID→사용 범위 판단을 연결해 주세요. QA 네트워크 수신 재시도와 Pilot 연구 head 변경에 따른 등록 재시도는 분리하며, import 실패 때문에 새로운 ask를 만들지 않습니다. 새 QA가 만든 후보는 정식 위키 반영과 구분합니다. 기존 자료·연구 단계·승인·M1 상태를 이 시험으로 변경하지 않는다는 경계를 유지합니다.

구현에서 맞지 않는 응답이 나오면 method/path, 토큰 제거 요청 payload, HTTP status, 비밀을 제거한 응답, job ID·기대/실제 필드와 보존 상태를 보내 주세요. 기존 계약·원기록을 유지하는 범위에서 재현 후 협의하겠습니다. 현재 위 제약을 전제로 P0–P3/T1을 막는 추가 Atlas 변경 요구는 확인하지 못했습니다.

근거: [server.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/server.py), [jobs.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/jobs.py), [service.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/service.py), [job_runner.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/job_runner.py), [공동 계약](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1.md). 이 회신은 현재 구현의 소비자 주의사항이며 v1 합의 본문을 대체하거나 미구현 기능을 지원으로 변경하지 않습니다.

---

## 추가 회신 — Pilot 소비자 코드 읽기 검토

> 아래 R1–R4는 최초 검토 당시의 이력이다. 최신 재검토에서는 네 건 모두 해소를 확인했다. 이 문서 마지막의 **추가 회신 — R1–R4 수정 재검토**를 현재 상태로 적용한다.

2026-09-13. `atlas_client.py`, `atlas_session.py`, `atlas_service_http.py`와 연결되는 기존 importer·소비자 테스트·후속 질문 UI를 읽었다. **Important 4건을 확인했다.** 첫 번째는 정상 Atlas source 수신을 막으므로 T1 원문 수신 완료 판정 전에 수정해야 한다. 나머지는 후속 질문·등록 재개·instance 확인의 누락이다. 아래 판단은 코드 및 합성 재현에 한정하며 실제 q1의 실행/응답 품질 평가가 아니다.

운영 Atlas, Pilot의 `output/evaluations/pilot-atlas-t1/research`, 실제 job `job-dcc8d0d0ac3a4f06` 및 QA에는 조회·수정·재접수하지 않았다. 서버도 재시작하지 않았다. 재현에는 네트워크를 쓰지 않는 합성 응답과 OS의 별도 임시 연구 폴더를 사용했고 종료 후 제거했다. 두 프로젝트의 구현 코드는 수정하지 않았으며 이 문서에만 추가했다.

### R1 · Important — 정상 source의 마지막 묶음을 항상 거절

위치: [atlas_client.py:109](/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/researchclaw/codex/atlas_client.py:109), `AtlasClient.source`.

모든 묶음에서 `part['next_offset'] == offset + len(chunk)`를 요구한다. 실제 Atlas는 마지막에 `eof=true, next_offset=null`을 반환한다. 따라서 단일 묶음·다중 묶음·빈 원본 모두 마지막 처리에서 `atlas_source_invalid`가 된다. `_supporting`은 이를 부분 실패로 기록하므로 QA import는 성공하면서 **source 원형은 받지 못한 상태**가 될 수 있다.

재현: bytes=`b'original'`, 올바른 source ID/version/전체 SHA-256/size=8/offset=0, `eof=true,next_offset=None`인 정상 응답을 source()에 전달 → `atlas_source_invalid`.

수정 방향: eof=false일 때만 연속 next_offset과 진행량을 요구한다. eof=true이면 next_offset이 null인지, 누적 길이가 size인지, 전체 해시가 맞는지 확인한다. eof의 boolean 및 size/offset/version의 정수 타입도 명시적으로 확인하면 좋다. 현재 `test_source_chunks_must_have_contiguous_offsets`는 잘못된 offset의 거절만 검사하므로 이 정상 경로 오류를 발견하지 못한다. **실제 계약의 정상 단일/다중/빈 원본 성공과 잘못된 마지막 묶음 거절**을 추가해 달라.

### R2 · Important — ‘후속 질문’ 연결은 기록에만 있고 Atlas 입력에는 없음

위치: [atlas_session.py:74](/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/researchclaw/codex/atlas_session.py:74), `ask`; `research_ui/atlas_service.js`의 ‘이 답변에 이어 질문’ 동작.

previous가 이전 요청의 존재·바인딩을 확인하는 데만 쓰이며, 실제 payload.question에는 새 입력 문자열만 들어간다. UI는 이전 질문을 옆에 표시하지만 전송 텍스트에 넣지 않는다. Atlas ask는 독립 실행이고 client_context를 모델에게 전달하지 않으므로 사용자가 ‘왜 그래?’처럼 이어 물으면 무엇에 대한 질문인지 알 수 없다.

재현: q1=`First full question?`, q2=`Why?`, previous=q1 → 실제 전송 question은 정확히 `Why?`이며 이전 질문/답변/QA 참조는 없다. 이는 질문 두 건의 전송 성공으로는 발견되지 않는다.

수정 방향: 사용자 입력과 실제 전송 질문을 구분해 보존하면서 필요한 이전 질문·답변의 쟁점/QA 참조와 이번 질문을 자족적인 텍스트로 구성하거나, UI에서 그 맥락을 포함한 질문 작성을 명확히 요구한다. 조합 결과도 **전송 전에** 고정·저장하고 재전송에서 바꾸지 않는다. 현재 Atlas에 미지원 previous/messages 필드를 추가해 보내는 방식은 쓰지 않는다. 기존 q2가 이미 자족적이면 그 개별 시험은 진행할 수 있지만 UI의 일반적인 후속 질문 기능이 검증됐다는 뜻은 아니다.

### R3 · Important — 원형 수신 후 로컬 등록 재시도가 다시 네트워크를 요구

위치: [atlas_session.py:120](/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/researchclaw/codex/atlas_session.py:120), `receive`.

QA envelope·qa_ref·objects 파일을 import 전에 저장하는 순서는 맞다. 그러나 import_result가 없는 모든 재시도에서 poll→QA HTTP 수신→참고 원형 수신을 다시 수행하고, 보존한 QA 바이트를 읽는 재개 경로가 없다. 연구 head 변경 등으로 Pilot 등록만 실패한 뒤 Atlas 연결이 끊기면, 이미 검증·보존한 QA로 등록을 재시도할 수 없다. 이전 참고 자료 수신 결과도 재시도 결과로 교체될 수 있다.

재현: 임시 연구에서 QA 수신 후 유효하지 않은 expected_head로 등록을 거절시킴 → qa_ref와 objects의 원형은 실제 존재. 새 현재 head로 재시도하면서 연결만 unavailable로 바꾸면 import 전에 `atlas_transport_unavailable`로 종료.

수정 방향: 수신·검증 완료와 Pilot 등록 상태를 분리하고, 보존한 instance/job/QA 참조·해시를 재검증해 **저장된 같은 바이트**로 import를 재개한다. 참고 page/source의 추가 수신도 이미 확보한 근거를 잃지 않게 이어간다. 등록 응답 유실 때의 고정 command_id 재사용은 유지한다. 회귀 검증은 실제 head 충돌 후 새 head로 재등록, 등록 직후 응답 유실, 수신 완료 후 서버 오프라인을 포함하면 된다.

### R4 · Important — 개별 v1 응답의 최상위 instance/version 검사가 누락

위치: [atlas_session.py:105](/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/researchclaw/codex/atlas_session.py:105), `poll`; [atlas_session.py:166](/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/researchclaw/codex/atlas_session.py:166), `_supporting`.

사전 identity 조회와 job 안의 instance·receipt 검사는 있지만, 개별 job 응답 최상위의 contract_version/atlas_instance_id를 확인하지 않는다. 페이지 응답도 해당 envelope를 확인하지 않고 raw 해시만 검사한다. 연결 파일은 매 request마다 다시 읽으므로 사전 info가 개별 응답의 instance 검증을 대신하지 못한다. 독립 복제본에 남은 옛 job은 최상위 서버 instance와 job의 원래 receipt instance가 다를 수도 있다.

재현: 사전 info와 job/receipt/payload는 instance-A로 유지하고, job HTTP 응답 최상위만 `atlas_instance_id=instance-B,contract_version=pilot-atlas/99`로 바꿈 → poll이 성공했다. 이 재현에서는 client_context·receipt operation은 올바른 값으로 유지했다.

수정 방향: v1 응답의 ok/version/instance와 요청한 job/QA/page ID를 검증한 뒤 저장한다. raw 해시 검증은 별도로 유지한다. legacy source/projects는 envelope가 없다는 기존 제약을 그대로 처리하며, 토큰이나 URL 변경만으로 불일치라고 판단하지 않는다. instance 오류를 단순 page 다운로드 실패로 덮어 이어갈지도 명시적으로 정하고, 새 instance의 근거를 기존 바인딩에 성공 등록하지 않게 한다.

### 기타 보완·검토 범위

- `atlas_client.py` HTTP 오류 처리는 code/status/retryable만 남기고 details를 버리며, journal은 다시 `str(exc)`만 저장한다. 413의 실제 크기/한도·raw_available, 충돌·버전 오류의 허용된 details를 재개/UI에 전달할 수 없다. 알려진 안전한 구조화 필드를 보존하고 토큰/임의 예외 원문은 제외하는 방향이 좋다. 또한 내부 `AtlasError('atlas_response_too_large')`가 하단 ValueError 처리에 잡혀 `atlas_response_invalid`로 바뀌는 점도 확인했다.
- 정상 v1 요청을 전송 전에 journal에 저장하고, 바인딩 변경 후 이전 요청의 payload를 유지하며, 고정 command_id로 기존 importer를 재사용하는 구조는 계약 방향과 맞는다. `atlas_service_http.py`는 환경 설정의 연결 파일을 사용하고 브라우저가 임의 연결 경로를 지정하지 못하게 하며, 이번 범위에서 독립적인 Important는 확인하지 못했다.
- 검토 중 Pilot이 추가한 `receipt.operation == jobs.submit` 및 payload.client_context 일치 검사는 최신 파일에서 확인했다. 이를 누락 사항으로 다시 지적하지 않았다. 테스트 전체 실행·실제 q1 확인·UI 동작 검증은 Pilot 담당 범위로 남긴다.
- 위 사항은 현재 소비자 코드에서 보완할 수 있으며 **Atlas 운영 코드 변경이 먼저 필요한 문제는 아니다.** 원래 q1/request_key와 이미 받은 QA를 유지한 채 수신·등록을 재개해 달라. 수정 확인 시 정상 원문 수신과 자족적인 후속 질문까지 T1 결과에 구분해 기록하면 된다.

마지막 읽기 시 파일 SHA-256: atlas_client.py=`68ac0648e26b2145c33addeed513053a9fae893a05c12bfcc232b171a916d4f5`, atlas_session.py=`44604108f20d99b8ffbc30d4a6940ac17ab871ff266b4c85b1cf3de94b78cba9`, atlas_service_http.py=`fc9763f2b72ca07c43e43f3eeb7598991168f9f6a974434c2874142fab2510b2`. 이후 변경에는 이 검토 결과를 그대로 완료/실패 판정으로 적용하지 말고 해당 동작을 다시 확인한다.


---

## 추가 회신 — R1–R4 수정 재검토

2026-09-13. Pilot의 수정 통보 후 최신 세 파일을 다시 읽고 합성 데이터로 검증했다. **최초 Important R1–R4는 이번 검토 범위에서 모두 해소됐다.** 위의 최초 재현·수정 요청은 이력으로 보존하며, 현재 상태는 이 절을 우선한다. Atlas 운영 코드 변경을 요구할 추가 Important는 이번 범위에서 확인하지 못했다.

| 항목 | 현재 판단 | 확인한 동작 |
| --- | --- | --- |
| R1 · source 마지막 묶음 | 해소 | eof=true이면 next_offset=null을 받는다. 단일·다중·빈 원본의 성공, 잘못된 종료 묶음의 거절, 누적 크기·전체 SHA-256 확인을 재현했다. |
| R2 · 후속 질문 맥락 | 해소 | backend가 이전 사용자 질문·QA 참조·이번 질문을 payload.question으로 조합하고 전송 전에 저장한다. 사용자 원문은 row.question으로 별도 보존한다. 같은 키 재시도에서 payload가 유지되고, 조합된 여러 줄 질문을 가진 정상 QA도 import된다. 기존 저장 요청을 재구성하지 않는다. |
| R3 · 보존 QA로 등록 재개 | 해소 | 실제 head_conflict 후 네트워크를 차단해도 보존 qa_envelope·qa_ref·supporting으로 같은 QA를 import한다. refresh_supporting은 별도 동작이며 이전 수신 결과를 supporting_history에 남기고 연구 head/import를 바꾸지 않는다. |
| R4 · 개별 v1 응답 식별 | 해소 | job/QA/page에서 ok·contract_version·atlas_instance_id 및 요청 ID를 확인한다. 각 식별값/버전 오류를 주입하면 거절되고 연구 head는 유지된다. page의 instance/계약/참조 오류도 단순 부분 수신 실패로 넘기지 않는다. |

receipt.operation 및 payload.client_context 검증도 통과했다. HTTP 오류의 안전한 size_bytes/max_bytes/raw_available details 보존과 임의 token 필드 배제를 확인했다. poll은 status/retryable/details를 error_info에 보존한다. 응답 크기 초과 AtlasError를 일반 JSON 오류로 바꾸던 분기도 별도 except AtlasError로 보존하도록 수정된 것을 읽기 확인했다.

### 검증 방법과 범위

- Atlas 환경에서 PYTHONDONTWRITEBYTECODE=1 및 uv run --no-sync python으로 Pilot의 `tests/codex_native/research_graph/test_atlas_service.py`를 import하고 **테스트 함수 15개를 직접 호출해 모두 통과**했다. 각 함수에 별도의 실경로 임시 폴더와 필요한 MonkeyPatch를 제공했다. Pilot 전체 pytest 실행 결과를 뜻하지 않는다.
- 추가 합성 확인 **20개 통과**: source 정상 단일/다중/빈 원본 및 잘못된 종료 묶음 6개, job/QA/page 각각 instance/version/ok/ID 오류 거절 12개, 후속 payload 고정 및 여러 줄 질문 QA import 2개.
- 후속 QA import의 합성 응답은 YAML serializer로 정상 원형을 구성했다. 기존 테스트 fixture의 단순 문자열 연결은 여러 줄 question 원형 생성에 적합하지 않아 이 추가 확인에서 그대로 쓰지 않았다. 운영 QA에는 접근하지 않았다.
- 테스트는 임시 연구 폴더·합성 응답을 사용했다. HTTP 오류 테스트만 별도의 임시 로컬 서버를 열고 닫았다. 운영 Atlas HTTP와 실제 T1 연구 root, 원본·QA·job에는 조회·수정·재실행하지 않았다. 운영 서버를 재시작하지 않았으며 두 프로젝트의 구현 코드도 수정하지 않았다.
- Pilot의 실패 테스트 후 수정 과정 자체는 Pilot 보고이고, 이번 검토에서는 수정 후 코드의 통과를 독립 확인했다. 검증 종료 시 세 구현 파일의 해시가 읽기 시점과 동일함을 확인했다.

### 실제 T1 상태와 다음 확인

Pilot 보고에 따르면 q1 `job-dcc8d0d0ac3a4f06`은 completed·import·사용 판단까지 완료됐고, 참고 페이지 3개와 원본 PDF 2,492,841 bytes 및 해시를 수신했다. 이는 Pilot 보고로 기록하며 이번 재검토에서 운영 데이터를 다시 수신한 것은 아니다.

q2 `job-da83bf989a7840a7`은 마지막 전달 시 실행 중이며, 저장 질문 본문에 이전 QA ID·질문 핵심·자료 공백·이번 확인 목적이 포함돼 있다. 새 backend 조합을 적용하기 위해 기존 q2를 재실행하거나 저장 payload를 변경할 필요가 없다. 현재 ask의 독립 실행 계약도 유지된다.

남은 T1 확인은 Pilot에서 q2 완료 후 같은 QA 원형·근거 수신·import·사용 판단과 실제 UI 흐름을 기록하는 것이다. 이전 질문/QA 참조의 전송 성공과 이전 답변의 쟁점·한계를 실제 답변에서 정확히 반영했는지는 구분해 평가한다. 이번 결과만으로 q2 완료나 전체 P0–P3/UI 검증 완료를 선언하지 않는다.

재검토한 파일 SHA-256:

- `atlas_client.py`: `170bb388f5ce0d0dc4230b23ca74f822c6888633beaccad20f2ac210fe1cf301`
- `atlas_session.py`: `114ddf3fe7a49a27ba304eb22365319bc3aa2f55c8244d19b608d9cd3c6e596a`
- `atlas_service_http.py`: `6ab6e00949ec0650ade4722b2836f8b157c031632a6fbc2b700e28efdd976476`
