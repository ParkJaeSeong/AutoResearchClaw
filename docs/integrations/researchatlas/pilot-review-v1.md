# Pilot 소비자 검토 — API·MCP v1

2026-09-13 · **Pilot 측 v1 최종 수용 — 남은 필수 수정 없음.** Atlas 담당은 아래 판본을 공동 계약 최종본으로 표시할 수 있다. 이 결론은 계약 문서 검토에 한정하며 코드 구현·배포·실제 T1/T2 시험·M1 연구 완료를 뜻하지 않는다.

규범 기준: [Atlas 본문](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1.md), [합성 예제](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1-examples.json), [수락 기준](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1-acceptance.md). Pilot의 [소비 규칙](contracts.md)·[시나리오](README.md)·[프로젝트](projects.md)·[작업 단위](tasks.md)는 이 계약을 참조한다.

## 최종 대조 결과

| 검토 파일 | 검토한 원형 SHA-256 |
| --- | --- |
| api-mcp-v1.md | `34d75328772792227a72ce8c4a297da4217f87e73adfca8d48a84f7f50697d93` |
| api-mcp-v1-examples.json | `6203c2aec5225283f267b9f9c556b14a759ebeae24f7bae3e4e13617b2c68dbd` |
| api-mcp-v1-acceptance.md | `99e8f581e6e0d6282ee3838cc846451776fae6a6297d19d3c0f495e8bd50644a` |

| 항목 | 해소 근거 | 판정 |
| --- | --- | --- |
| R1 | §9 접수 당시 input/projects/contexts/receipts/extractions 고정, P/Q별 결과와 나중 R 제외 | 수용 |
| R2 | §8 판별형 target·artifact 선택·partial/failed 구분·파일 없는 실패 기록·review_claims/validation 분리, §9 불변 input→source/사용 파일 매핑 | 수용 |
| R3 | §10 이전 input_manifest.source_refs 전체 유지, 누락400 invalid_scope/missing_source_refs, 범위 축소는 독립 분석 | 수용 |
| R4 | §3 공통 오류 envelope, §5/10 reference_mismatch, §4 미지원 버전, §10 terminal 결과 부재와 retryable 구분 | 수용 |
| R5 | §3 공통 request_key/request_sha256/구조화 receipt_ref, §7/8 input·extraction commit 구분, 예제의 receipt 및 manifest | 수용 |
| R6 | §4 capability별 보장 범위와 ingest_manifest_v1, §9 항목/프로젝트 결과, §10 이번 요청 coverage 기준 완료 판정 | 수용 |

추가된 21개 합성 case·12개 오류를 읽고 JSON 문법을 검사했다. 원형 base64 묶음 10개의 디코딩·길이·SHA-256, raw/record 쌍 6개의 파싱 일치, 결과 envelope의 해시 일치를 확인했다. 이는 문서 자기 일관성 검사이며 실제 HTTP/MCP 실행 결과가 아니다. 요청 fingerprint의 서버 구현 적합성과 과학적 해석 품질은 수락 시험에서 검증한다.

예제에 담긴 P/Q/R 고정 범위, partial extraction→ingest 매핑→analyze, 후속 source 추가·미해결 승계, lifecycle 단독 실패, terminal/running 결과 부재와 해시·버전·이전 source 누락 오류는 이번 계약을 소비하기에 충분하다. 수락 기준의 P-04/X-01/G-01/N-04/J-01 구현 시험에는 이 구체 예제를 함께 적용한다.

검토 도중 갱신된 예제도 다시 원형 검사했다. 최종 검토 예제의 해시는 위 표에 기록한다.

Atlas 문서는 편집하지 않았다. Pilot 문서의 미확정 endpoint·중복 필드 예시는 규범 본문 참조로 교체했다. 다음 실행 순서는 **Atlas A1/식별·QA·페이지 기능 → Pilot P0–P3 → 실제 T1**이며 capability와 배포 상태를 확인한 뒤 진행한다.

## 이전 검토 이력 — 모두 해소됨

아래의 ‘수정 대기’, ‘R1–R6 명시 후 확정’은 이전 판본 당시의 기록이다. 현재 판정은 위 최종 수용이며 아래 문구를 새 차단 조건으로 사용하지 않는다.

<details>
<summary>1·2차 검토와 당시 수정 요청</summary>

2026-09-13. Atlas 담당의 공동 최종화 요청에 대한 **Pilot 측 구체 수용·수정 의견**이다. Atlas는 생산자 계약 본문·예제를, Pilot은 시나리오·소비자 요구를 소유한다. 이 문서는 코드 구현·배포·실제 연구 변경 완료를 뜻하지 않는다. Atlas v1 본문 초안을 대조했다. 아래 「생산자 초안 대조 결과」가 이번 회신이며, 이어지는 1–6항은 소비자 요구의 배경이다. 공동 확정은 아래 수정 사항의 반영·대조 후 기록한다.

참조: [Atlas 개선안](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/m1-api-mcp-review-2026-09-13.md), [시나리오](README.md), [프로젝트](projects.md), [작업 단위](tasks.md).

### 당시 결론

A1→기존 Atlas 프로젝트를 사용하는 T1을 우선하고, A0/A2/A2b와 기존 jobs의 kind=analyze를 후속 연결하는 최소 경로를 수용한다. 별도 material ID·analysis ID·worker는 요구하지 않는다. 일반 project=null을 유지하고 Pilot M1 의뢰만 기본 프로젝트 연결을 요구한다. 자료실 고정 instance ID를 info로 제공하는 방안을 수용한다.

| 쟁점 | Pilot 의견 | 최종 계약에 필요한 명시 |
| --- | --- | --- |
| A1 QA·페이지 원형 | 수용 | raw/record 동일 바이트, 파일 해시, lifecycle 별도, 크기 초과 처리 |
| A0 프로젝트 | 수용 | 일반 null 허용과 M1 연결 요구 분리, ID·버전·변경 이력 |
| A2 접수 | 수용 | input_id 우선, source=null 가능, 접수 멱등성 |
| A2b 완료 변환 연결 | 수용 | 원본 참조·출력 해시·부분 추출·원문 대조 범위 |
| A3/A4 jobs kind=analyze | 수용 | 기존 ask/ingest 의미 유지, 고정 source refs, 불변 결과 |
| A5 previous_result_ref | 수용 | 실행 ID와 결과 버전 구분, 기존 결과 덮어쓰기 금지 |
| HTTP 바이트/MCP 세션 제어 | 수용 | MCP가 임의 서버 로컬 경로를 읽지 않으며 대용량 바이트를 모델 문맥에 넣지 않음 |
| request_key+fingerprint | 수용 | 모든 변경 종류의 정규화·충돌 범위, 응답 유실 후 재조회 방법 |
| info instance ID | 수용 | 재시작·포트·토큰 변경에도 고정, 다른 자료실이면 연결 재확인 |

### 당시 생산자 초안 대조 결과 — 2026-09-13

검토 대상: [Atlas API·MCP v1](</Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1.md>), 총 229행, SHA-256 `63f5878cc3d0b0c0936dae64e5ebf73990eceac4d39debd0b0011d0c342257dc`(이번 검토 시점). 아래 행 번호는 이 판본 기준이다.

**결론: 경로와 책임 분리는 수용한다. T1 요구는 의미상 충족하며, T2와 공통 실패 계약은 R1–R6를 명시한 뒤 공동 확정할 수 있다.** 구현·배포·통합 시험 완료 판정은 아니다. 새 플랫폼이나 자동 변환 실행을 추가로 요구하지 않는다.

수용 사항: uploads/inputs와 기존 jobs의 analyze 확장, 일반 project=null과 Pilot 기본 연결 분리, 공용 위키 보완 검색, 고정 instance와 복제/복구 구분, 원형 10 MiB 경계, QA lifecycle 별도 실패, 전체 파일 해시, 응답 envelope의 result_ref, execute 재전송, immutable 결과/후속 이력, 위키 자동 반영 금지. 자체 해시 순환 문제도 §10에서 이미 해결됐다.

### 최종화 전 수정 요청

| ID / 본문 위치 | 발생 가능한 불일치 | Pilot 수정 의견 및 수락 사례 |
| --- | --- | --- |
| R1 / §6, §9 지정 input ingest, 116–118·150–156행 | input을 P와 Q에 연결할 수 있는데 ingest는 items+project를 금지한다. 접수 뒤 프로젝트 연결을 바꾸면 queued 작업이 실행 시 어떤 프로젝트·맥락을 사용하는지 불명확하다. client_context는 Atlas 범위를 대체하지 않는다. | 기존 금지는 유지해도 된다. 접수 시 input별 프로젝트 연결·맥락을 작업 manifest에 고정하고 실행 중 새 연결은 그 작업에 소급하지 않는 것으로 정의해 달라. P/Q 모두 정리한다면 양쪽 결과·실패를 분리해 반환하고, 한쪽만 선택한다면 선택 규칙을 명시한다. **P 접수→Q 연결→J 제출→R 연결→J 실행**에서 처리 범위와 결과 귀속이 제출 당시와 같아야 한다. |
| R2 / §8–9, 142–146·154·168행 | input I/H에 연결한 extraction E를 ingest한 뒤 source S/v1/H로 분석할 때 E의 적격성 판정이 없다. 해시만 같으면 다른 input·source의 변환도 잘못 연결할 수 있다. partial/failed 변환의 어느 artifact를 사용할지도 모호하다. | 불변 extraction manifest는 바꾸지 않고, ingest 결과에 **I/H → S/v1/H와 실제 사용한 E/hash** 매핑을 보존한다. analyze는 이 매핑 또는 직접 source target을 확인하고 source_refs와의 관계를 검증한다. 동일 해시만으로 다른 source 버전의 변환으로 인정하지 않는다. completed/partial/failed의 사용 가능 artifact와 실패만 기록하는 경우를 구분한다. |
| R3 / §9–10, 164–168·189–203행 | 후속 요청이 새 source만 허용해도 이전 findings 전부를 retained/revised/withdrawn으로 처리해야 한다. 예전 source를 뺀 사실만으로 옛 결론을 철회하거나, 옛 근거를 현재 evidence에 몰래 넣을 위험이 있다. | 최소안: 후속 분석은 이전 결과에서 채택한 source_refs를 포함하도록 요구하고 누락 시 400 invalid_scope에 missing_source_refs를 반환한다. Pilot은 이전 근거+새 근거로 요청한다. 범위 축소가 꼭 필요하면 새 독립 분석으로 처리한다. 대안으로 ‘이번 범위에서 재검토하지 않음’을 별도 변화 상태로 설계할 수 있으나, 단순 범위 제외를 withdrawn으로 기록하면 안 된다. |
| R4 / §2–3·5·10–11, 23·37·67·101·174·209–217행 | 모든 신규 최상위 응답에 instance를 요구하지만 실패 envelope에는 빠져 있다. error는 문자열인데 §11은 error.retryable을 참조한다. QA/result expected 해시 불일치, 미지원 contract_version, terminal job에 결과가 영구히 없는 경우의 코드·재시도 의미도 확정되지 않았다. | 오류 envelope에도 atlas_instance_id를 명시하고 **최상위 retryable**로 통일한다. expected QA/result 불일치는 409 reference_mismatch, page는 changed_page로 정한다. 미지원 버전은 400 unsupported_contract_version과 지원 버전 목록을 제안한다. result_not_ready는 queued/running이면 상태 조회 가능, terminal+결과 없음이면 retryable=false와 job_status/result_available=false를 제공한다. 공통 errors 표와 본문의 의미를 맞춘다. |
| R5 / §3·7–8, 59–61·124–146행 | fingerprint를 보존하라고 하지만 모든 변경 응답의 공통 필수 필드가 없다. receipt_ref 형식, extraction target의 판별 형태, coverage/artifacts의 타입·빈값, failed 변환에서 파일 0개 허용 여부도 없어 두 클라이언트가 같은 요청을 만들기 어렵다. | 생성·link·commit·job 접수 응답에 request_key/request_sha256과 고정 receipt 식별 방법을 명시한다. input/extraction 각각의 commit 응답을 나눈다. 최소 JSON schema 또는 완전한 JSON 예제와 타입·필수/null/빈 목록 규칙을 붙인다. external_parent_task_id는 첫 작업에서 null, 실패로 산출물 0개인 변환도 오류 manifest만 보존 가능하도록 제안한다. 서버가 이미 검증한 것과 업로더의 검토 주장을 coverage에서 분리한다. |
| R6 / §4·9–10·12, 71–89·156·184–195·222–227행 | analyze_v1은 구현 순서에만 있고 대응표에 없으며, A1 ask 근거 공개와 ingest 매핑의 지원 여부도 별도로 판별하기 어렵다. coverage는 requested_items를 전부 포함하나, 이전 미해결을 carried_forward로 유지하면서 새 항목만 confirmed이면 completed 여부가 모호하다. | capability별 포함 필드·경로·수락 시험을 info 계약에 명시한다(기존 capability 묶음에 포함해도 됨). analyze의 requested_items는 최소 1개, ID는 결과 내 유일, 모든 참조는 존재 검증한다. completed/partial은 **이번 requested_items의 coverage** 판정이며 이전 carried_forward나 새 실험 질문이 남아도 연구 준비 완료를 뜻하지 않음을 명시한다. ingest의 항목 partial/failed와 최상위 job 상태 대응도 고정한다. |

R3의 최소안은 기존의 ‘같은 source로 재분석 가능’을 유지한다. 근거가 잘못됐다고 판단해 철회하는 것은 그 근거를 검토 범위에 포함한 채 withdrawn으로 설명할 수 있다. 원문을 더 이상 읽을 수 없다면 그 제약을 미해결로 반환한다.

### 추가할 요청·실패 예제

본문 표의 의미 설명과 별도로, Atlas가 다음을 실제 JSON 요청/응답으로 붙이면 Pilot 어댑터 수락 시험의 기준으로 사용한다. 아직 실제 서버에서 실행한 예제가 아니다.

1. 기존 프로젝트 ask → job의 qa_ref/consulted_pages → QA raw/record/lifecycle; lifecycle만 실패한 200과 원형 상한 초과 413.
2. 파일 upload → PUT 응답 유실 → 같은 바이트 재전송 → commit 응답 유실 → 같은 키 commit으로 동일 input/receipt 회수.
3. input 대상 partial extraction commit → 지정 ingest의 source/사용 extraction 매핑 → 같은 extraction을 지정한 analyze.
4. source S/v1과 새 S2를 사용하는 후속 analyze → 이전 finding 변화·미해결 승계. S/v1 누락은 R3의 명시된 오류.
5. terminal failed+결과 없음, partial+불변 결과 있음, expected 결과 해시 불일치, 미지원 계약 버전의 서로 다른 응답.
6. 같은 input의 다중 프로젝트 연결과 queued 이후 연결 추가: R1의 고정 처리 범위·프로젝트별 결과 확인.

### 예제·수락 기준 추가 대조

[합성 예제](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1-examples.json)와 [수락 기준](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1-acceptance.md)도 읽었다. 본문 SHA-256은 위 검토 판본과 동일하므로 R1–R6는 새 반영 사항을 누락해서 제기한 문제가 아니다.

- 합성 10개 case/7개 오류의 JSON 문법, 원형 바이트 묶음 4개의 base64·길이·SHA-256, QA/분석 결과 raw에서 파싱한 record 일치를 검사해 통과했다. 실제 HTTP/MCP 호출이나 연구 내용 검증은 수행하지 않았다.
- result_ref의 envelope 배치, identity의 instance/project, 경계 크기와 원기록 보존, 미해결 전 항목 승계 요구는 **수용 완료**다. 이 항목을 추가 차단 사유로 남기지 않는다.
- 오류 예제에는 atlas_instance_id와 최상위 retryable이 이미 맞게 들어 있다. R4 중 이 부분은 예제 수정이 아니라 **본문 envelope와 error.retryable 표기 정정**만 필요하다. terminal 결과 부재·미지원 버전·QA/result 해시 오류 의미는 여전히 명시가 필요하다.
- T2-commit 예제에는 request_key/request_sha256이 없어 R5의 공통 receipt 응답 요구는 남는다. 변환 commit/조회, 프로젝트 다중 연결, followup의 실제 변화·승계 **응답**은 아직 예제가 없다. T2-followup의 expect 목록만으로 참조 구조까지 고정되지는 않는다.
- 수락 기준 P-04/X-01/G-01/N-04는 큰 방향이 맞다. R1의 queued 뒤 연결 추가, R2의 input→source 변환 매핑, R3의 이전 source 제외, R4의 terminal 결과 부재를 구체적인 경계 사례로 보완하면 된다.

최종 회신: **설계 방향 수용, R1–R6 명시 후 공동 최종화**. 새 구조 개발을 요청하는 것이 아니라, 현재 선택한 v1 경로의 범위·참조·실패·응답을 두 구현이 동일하게 해석하도록 고정하는 요청이다.

### Pilot 문서 자체의 정정

- identity 안의 자체 result_ref 요구는 제거한다. result_ref는 envelope에만 두고 이전 참조만 record 내부에 둔다.
- instance 식별 필드명은 atlas_instance_id, raw 길이는 size_bytes, raw 파일 해시는 sha256으로 본문에 맞춘다.
- QA/page/result 원형은 v1에서 10 MiB 전체 반환을 수용한다. source/extraction 파일은 묶음 조회다. 큰 JSON/base64 수신은 호스트 어댑터가 처리하며 모델 대화에 그대로 넣지 않는다.
- 이번 검토는 Atlas 본문을 수정하지 않는다. R1–R6의 반영 판본을 다시 대조한 뒤 ‘공동 계약 확정’을 기록하며, 현재 상태는 **소비자 검토 완료·생산자 수정 대기**다.


</details>

## 1. 프로젝트 바인딩과 검색 범위

Atlas의 일반 자료·질문은 project=null을 계속 허용한다. Pilot M1은 첫 의뢰 전에 기본 Atlas 프로젝트를 선택하고 Pilot 프로젝트와 대응을 보존한다. 프로젝트 탐색용 목록·공용 지식 조회는 연결 전에도 가능하다. 기존 프로젝트를 선택한 T1은 생성 API를 기다리지 않는다.

기본 연결 기록은 pilot_project_id, atlas_instance_id, atlas_project_id, 목적·범위·선택 이유, 이전 연결 참조다. Atlas가 받는 project는 Atlas ID이고 client_context는 Pilot의 불투명 문맥이며 실행 설정·권한으로 사용하지 않는다. 여러 Pilot 연구가 하나의 Atlas 프로젝트를 사용해도 각 연구의 질문·판단·근거 묶음은 독립적으로 유지한다.

project_only=false는 선택 프로젝트에 공용 wiki를 보완하는 의미다. 다른 프로젝트 전용 페이지까지 자동 포함하지 않는다. 다른 프로젝트 해석을 보고 싶으면 해당 프로젝트를 별도 조회하고 범위 밖 참고 후보로 관리한다. 범위 필터는 접근 권한이나 에이전트의 파일 읽기 격리가 아니다.

자료실 instance ID는 비밀이 아닌 영속 식별자다. 제안 조회 이름은 GET /api/info와 atlas_info이며 정확한 이름은 Atlas 본문에 맞춘다. 최소 응답에는 atlas_instance_id, contract_version, 지원 작업/전송 기능·제한을 포함하면 소비자가 미지원 기능을 구분할 수 있다. URL·토큰·표시용 별칭을 영속 식별자로 사용하지 않는다. 자료실 복제본을 별도 인스턴스로 운용할 때의 새 ID 발급과 동일 자료실 복구 시 ID 유지 규칙을 명시한다.

새 기본 프로젝트는 이후 요청에 적용한다. 이미 제출한 job, 결과, QA는 원래 project/instance에 남는다. 명시한 project가 유효하지 않으면 null이나 전체 범위로 대체하지 않는다. 프로젝트 생성은 제목만으로 같은 범위라고 합치지 않는다. 기존 동일 제목이 있을 때 exists와 기존 ID를 반환하는 정책을 택한다면 Pilot이 해당 범위를 읽고 명시적으로 선택할 수 있어야 한다.

## 2. QA 10 MiB·원형·전송

현재 Pilot parse_atlas_qa의 상한은 **디코딩한 원형 파일 바이트 10,485,760바이트(10×1024×1024)**다. 정확히 이 크기는 크기 검사상 허용되지만 UTF-8·QA schema·구조 제한을 통과해야 한다. Base64 문자열 길이나 JSON 응답 전체 크기를 이 한도와 혼동하지 않는다.

A1 raw의 최소 의미: sha256, size_bytes, encoding, 원형 바이트 수신 방법. record는 동일 바이트에서 파싱한 QA다. UTF-8 인코딩·개행·YAML·공백을 재작성하지 않는다. QA input_sha256은 payload fingerprint이며 파일 SHA-256을 대신하지 않는다. consulted_pages는 실제 참고 당시 ID·파일 해시다.

QA raw/record와 lifecycle을 분리한다. lifecycle에는 현재 후보 처리 상태·이벤트 및 조회 시점/버전 식별을 제공한다. lifecycle 조회 실패 시 raw가 정상 수신됐다는 사실과 별도 오류를 유지한다. archive 후 QA 원문 해시는 바뀌지 않아야 한다.

페이지 sha256은 YAML 포함 전체 파일 해시다. 본문 markdown·metadata·HTML은 파생 표현이고 해시 검증 대상 원형을 대신하지 않는다. expected_sha256 불일치는409로 처리하며 과거 페이지를 구할 수 없으면 그 사실을 남긴다. Pilot은 이미 보존한 동일 해시 원형이 있으면 그것을 사용하고, 현재 페이지를 과거 근거로 바꾸지 않는다.

HTTP 바이트 다운로드와 MCP의 수신 세션/참조 제어를 우선한다. 작은 원형을 base64로 제공해도 의미는 동일하다. 묶음 조회는 전체 파일 해시·전체 길이와 offset/next_offset/eof를 제공해야 한다. offset은 원형 바이트 기준이며 조각의 UTF-8 경계에 의존하지 않고 전체를 조립 후 파싱한다. Pilot은 누락·겹침·해시 불일치를 거절하고 동일 원형의 전송만 재시도한다.

QA가 한도를 넘으면 Atlas job 자체를 실패로 바꾸지 않는다. Atlas는 실제 길이와 원형 조회 가능 여부를 반환하고 Pilot은 수신/가져오기 불가를 명시한다. 요약·잘림·YAML 재생성을 원본으로 등록하지 않는다. 더 짧은 새 QA를 요청한다면 새 작업·새 원기록이며 기존 결과를 보존한다.

## 3. analyze 결과와 후속 연결

기존 POST /api/jobs에 kind=analyze를 확장하고 대응 MCP 제출 도구를 사용한다. 결과 전용 경로가 필요하면 GET /api/jobs/{id}/result 같은 기존 job 하위 조회를 선호한다. 이름은 Atlas 본문을 따른다. job_id는 실행, result_ref는 불변 결과 버전이다. 별도 analysis_id를 만들지 않는다.

최소 result_ref 의미는 atlas_instance_id, job_id, schema_version, sha256이다. sha256은 파싱 후 재직렬화한 JSON이 아니라 **보관·반환하는 결과 원형 바이트**의 해시로 정의한다. 다른 해시 방식을 택한다면 정확한 canonicalization을 명시해야 한다. job 상태/갱신 시각을 결과 해시에 섞지 않는다.

| 결과 필드 | 필수 의미와 빈값 규칙 |
| --- | --- |
| identity | schema_version, job_id, request fingerprint, atlas_instance_id/project, previous_result_ref(null 가능); 자체 result_ref는 envelope에만 제공 |
| input_manifest | 요청/실제 채택 source 버전·해시, 사용한 추출/변환 참조; 범위 밖 후보 별도 |
| findings | 주장 ID·판단·귀속·조건·evidence_refs. 결론을 못 내리면 빈 목록과 미해결 이유 허용 |
| evidence | 안정된 근거 ID, source/version/hash, locator, excerpt, original/extracted, 읽은/대조 범위·상태 |
| coverage | 요청한 requested_items 각각의 confirmed/partial/unconfirmed 등 계약된 상태와 이유; 누락 항목은 성공으로 취급하지 않음 |
| unresolved | 안정된 항목 ID, 부족한 내용, 영향을 받는 판단, 요청할 자료·다음 행동; 없으면 빈 목록 |
| storage | 결과 보존과 wiki 반영을 분리. 위키/후보 참조와 저장 당시 상태를 명시 |
| answer / limitations | 사람에게 읽히는 결론과 적용 한계; 과학적 확신을 작업 완료와 혼동하지 않음 |

비교 분석을 요청하면 comparisons를, 후속 분석에는 changes와 기존 unresolved의 resolved/carried_forward/replaced 및 이유·근거를 요구한다. 용어의 정확한 enum은 Atlas schema에 맞추되 의미를 유지한다. 과학적 주장에 근거가 없으면 supported로 만들지 않고 추론/제안/미확인으로 표시한다. 저자/Atlas 귀속과 직접 원문/추출본 확인을 보존한다.

입력 source_refs는 등록된 source_id/version/sha256로 고정한다. 결과 근거의 허용 목록 검사는 필수다. 신규 input은 ingest 후 매핑을 받아 analyze에 넘긴다. 추가 자료 제안은 반환할 수 있지만 이번 채택 근거에 조용히 편입하지 않는다.

완료·부분 완료 결과도 불변으로 저장할 수 있다. 실행 중 진행률/로그/임시 출력은 provisional로 구분하며 불변 result_ref나 확정 근거처럼 사용하지 않는다. storage의 현재 wiki 처리 상태가 나중에 변하면 결과 원형을 수정하지 않고 별도 lifecycle로 조회한다.

A5는 새 request_key와 정확한 previous_result_ref를 사용한다. 기본은 같은 instance/project의 결과를 잇는다. 다른 프로젝트 결과는 참고 근거로 명시하고 후속 분석으로 조용히 연결하지 않는다. 이전 결과가 없거나 해시가 다르면 거절하며 latest로 대체하지 않는다. 새 분석에서 이전 미해결 ID가 어떻게 처리됐는지 모두 설명해야 한다.

## 4. 멱등성·전송·재개 소비자 요구

변경 요청의 키는 인스턴스와 작업 종류 안에서 해석하고, fingerprint는 project/client_context/내용/고정 source refs/목적/이전 결과 등 비즈니스 입력을 포함한다. 토큰·전송 조각 크기·네트워크 재시도 횟수는 연구 내용 fingerprint가 아니다. 목록 순서의 의미, 기본값과 null의 동등성은 생산자에서 정의하고 Pilot은 반환 fingerprint를 보관한다.

같은 키·같은 내용은 같은 자원과 상태를 반환하며 같은 키·다른 내용은 충돌한다. 접수 응답이 유실돼 ID를 모르는 경우 동일 키 재제출로 ID를 회수할 수 있어야 한다. 다른 transport로 재시도해도 같은 의미를 적용한다. execute 재요청이 종료된 job을 새 실행으로 바꾸지 않는다.

HTTP 업로드 바이트는 호스트 클라이언트가 전달한다. MCP는 동일 업로드 세션 생성·상태·완료 제어를 제공하며 로컬 경로나 대용량 base64를 모델에게 넘겨 전송을 대신시키지 않는다. finalize는 전체 길이·해시와 프로젝트·메타데이터를 검증한 뒤 한 번만 input을 공개한다. 세션 만료·재시도·동일 offset 충돌의 오류와 보존 결과를 명시한다.

API200/ok=true는 조회 성공이다. job.status와 결과의 coverage는 별도로 확인한다. 개별 HTTP timeout은 모델 작업 종료를 뜻하지 않는다. 중단·부분 결과를 먼저 확인하고 recover 또는 재의뢰를 선택한다. 임의 실행 시간 제한·중단 후 자동 재시작을 이번 계약에 추가하지 않는다.

## 5. 요청·실패 예제의 소비자 기대

아래는 필드 의미 예시이며 Atlas 최종 schema의 실행 가능한 예제를 대체하지 않는다.

| 입력/사건 | 기대 결과 |
| --- | --- |
| 일반 ask(project=null) | Atlas에서 허용. Pilot M1에서는 연결 선택 후 제출 |
| search(project=P, project_only=false) | P와 공용 wiki 보완. Q 전용 페이지는 Q 별도 조회 |
| ask 완료→job→qa | raw 파일 hash/length 검증→같은 record→기존 Pilot import→사용 판단 |
| QA raw가10,485,761바이트 | 작업 결과 보존, Pilot import 크기 초과 명시, 잘림 없음 |
| QA archive 처리 | raw 해시 그대로, lifecycle만 변경 |
| 페이지 hash H 기대, 현재 H2 |409, H2를 H로 저장하지 않음 |
| 신규 파일 접수 완료 | input_id/hash 반환, source 참조 null 가능; 분석 시작 아님 |
| 같은 접수 키로 project 변경 | 내용 충돌, 기존 input 맥락 무단 변경 없음 |
| analyze(source S/v1/H, 목적 G) | 실제 근거 S/v1/H 검증, S/v2나 다른 자료는 채택 거절/범위 오류 |
| 후속 analyze(previous_result_ref=R/H) | 새 job, 기존 결과 유지, 미해결 항목 처리·변경 근거 반환 |
| finalize 응답 유실 후 같은 키 재요청 | 기존 input 반환, 파일·작업 중복 없음 |
| 같은 URL에서 다른 instance ID 응답 | 저장한 연결과 불일치 표시, 다른 자료실에 자동 의뢰하지 않음 |
| partial: 전류 방향 원문 미기재 | 해당 coverage 미확인과 영향 반환; 실험 준비 완료로 승격하지 않음 |

## 6. M1에서 추가로 필요한 소비자 조건

- 한 회차의 모든 에이전트는 Pilot이 보존한 같은 근거 묶음을 사용한다. Atlas 공용 자료실에 미공개 초기 의견을 전송하지 않는다.
- 요청은 어느 연구 질문·쟁점·결정을 위한 것인지 연결한다. 답변이 불충분하면 추가 탐색·범위 축소·보류·실험 질문 중 무엇을 택했는지 Pilot이 기록한다.
- 접수 완료, source 매핑, 추출 범위, 분석 완료, wiki 반영, 연구 사용 판단, M1 준비·M2 인계를 UI와 상태에서 구분한다.
- 새 프로젝트를 만들 때마다 원본을 복사하지 않는다. 공유 source와 프로젝트별 발견 이유·관련성·근거 버전은 구분한다.
- 원문 접근 불가·미기재·추출 실패·색인 오류를 모두 ‘근거 없음’으로 합치지 않는다. 부분 결과를 보존한다.
- schema_version 미지원, 원형 불일치, 잘못된 instance/project는 수신 실패로 처리하고 현재 연구 상태를 바꾸지 않는다.

## 최종 문서 대조 순서

R1–R6 반영 판본과 예제 대조를 완료했고 Pilot 측 최종 수용을 기록했다. 확정한 endpoint/tool/schema/error 이름은 Atlas 본문을 단일 생산자 기준으로 하고 Pilot 문서에는 소비·검증 규칙과 참조를 유지한다. T1은 기존 프로젝트·A1 원형 반환·P0/P1–P3로 시험한다. 문서 합의, 코드 구현, 로컬 배포, 공동 통합 시험의 완료 상태는 각각 기록한다.
