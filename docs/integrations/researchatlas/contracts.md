# Pilot의 Atlas v1 소비 규칙

2026-09-13 · Pilot 측 계약 최종 수용. 구현·배포·실제 통합 시험은 별도로 확인한다.

정확한 HTTP 경로·MCP 도구·필드·enum·오류·기능 광고 규칙은 [Atlas API·MCP v1 본문](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1.md)을 단일 기준으로 한다. 요청·응답은 [합성 예제](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1-examples.json), 구현 후 검증은 [수락 기준](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1-acceptance.md)을 따른다. 이 문서는 별도 schema나 미확정 endpoint를 제안하지 않는다.

[검토 결론](pilot-review-v1.md) · [시나리오](README.md) · [프로젝트](projects.md) · [작업 단위](tasks.md)

## 1. 연결과 의뢰

Pilot은 연구 질문·외부 탐색·자료 확보·분석 의뢰·연구 사용 판단을 담당한다. Atlas는 원본 보존·변환 산출물 연결·근거 분석·위키 정리를 담당한다. 자동 documents 실행은 v1 범위 밖이다.

첫 M1 의뢰 전에 Pilot 프로젝트와 Atlas 프로젝트를 연결하고 atlas_instance_id·목적·범위·선택 이유를 보존한다. 일반 Atlas project=null 사용은 허용한다. 기본 연결을 바꿔도 기존 job/QA/결과의 프로젝트는 바꾸지 않는다. 다른 instance를 같은 자료실로 자동 해석하지 않는다.

선택 프로젝트의 project_only=false는 공용 wiki 보완이며 다른 프로젝트 전용 해석은 별도 조회한다. 프로젝트는 권한 경계가 아니다. 미공개 독립 의견은 Atlas에 전송하지 않는다.

## 2. 원형과 자료 접수

QA/page/result 원형은 디코딩 파일 바이트 10,485,760바이트까지 수신한다. 길이·SHA-256·파싱 구조를 검사하고 모델 대화에는 큰 base64를 넣지 않는다. source/extraction 파일은 계약된 바이트 offset 묶음으로 조립한다. YAML·개행을 재생성한 내용을 원형으로 등록하지 않는다.

페이지 해시는 YAML 포함 전체 파일, QA input_sha256은 요청 fingerprint다. 과거 페이지 해시 불일치에는 현재 페이지를 대신 쓰지 않는다. QA lifecycle 조회 실패와 원형 수신 성공은 분리하고 보관 후 상태 변화로 원형을 고치지 않는다.

업로드는 호스트 어댑터가 인증 HTTP로 바이트를 보내고 MCP는 같은 세션을 제어한다. 업로드 commit은 접수이며 분석 실행이 아니다. input에 source_ref가 없을 수 있고 ingest의 불변 매핑을 받은 뒤 source 분석을 요청한다. 새 발견 이유·프로젝트와 전송 재시도를 구분한다.

완료 변환의 target·파일 해시·artifact 선택·부분 추출 범위를 보존한다. 업로더 review_claims와 Atlas validation을 구분하며 failed 변환의 진단 파일을 근거로 채택하지 않는다. input 대상 추출본은 ingest의 input→source 및 사용 extraction/파일 매핑을 확인한다.

## 3. 분석과 후속 질문

Pilot 자동 ingest는 items를 명시한다. 제출 당시의 프로젝트·맥락·receipt·변환 범위를 고정한 결과를 받고 각 항목과 프로젝트의 partial/failed를 읽는다. top-level completed만으로 연구 사용 가능 판정을 내리지 않는다.

analyze에는 source_refs·question·analysis_goal·requested_items·scope_policy를 고정한다. 반환 근거는 허용 source 버전 안에서만 채택하고, 범위 밖 제안은 다음 회차에 명시적으로 편입한다. 원문 확인과 추출본 확인, 저자 주장과 Atlas 해석을 구분한다.

result_ref는 불변 결과 바이트의 참조이며 응답 envelope에 있다. record 내부에 자체 해시를 넣지 않는다. Pilot은 원형과 instance/project·요청 문맥을 함께 보존한다. 같은 검토 회차의 에이전트에게 같은 수신본을 전달한다.

후속 analyze에는 새 request_key와 정확한 previous_result_ref를 사용하고 이전 input_manifest.source_refs 전체를 포함한다. 범위를 줄이면 독립 분석을 요청하고 Pilot에서 두 결과의 적용 범위를 비교한다. 이전 findings 변화와 모든 미해결 항목의 resolved/carried_forward/replaced를 확인한다.

이번 requested_items의 coverage에 따른 completed/partial과 M1 준비 완료는 별개다. Atlas 결과의 storage는 저장 당시 상태이며 후속 wiki 반영은 연결 QA lifecycle로 조회한다. 연구 사용·가설·실험 설계·준비·M2 인계 판단은 Pilot이 기록한다.

## 4. 재전송과 검증

같은 작업 재전송은 같은 request_key·내용을 유지하고 request_sha256·receipt_ref·자원 ID를 보존한다. 통신 timeout을 작업 실패로 간주하지 않는다. 상태와 보존된 결과부터 확인하고 완료 작업을 자동 재실행하지 않는다.

capability가 없는 기능은 지원으로 가정하지 않는다. 계약 버전·instance·프로젝트·원형이 맞지 않으면 연구 상태를 변경하지 않는다. result_not_ready의 terminal/retryable을 구분해 무한 조회하지 않는다.

T1은 기존 프로젝트 ask→QA·페이지·source 수신→Pilot import→사용 판단이다. T2는 확보→접수→변환 연결→ingest→지정 분석→후속 분석→설계 사용 판단이다. 문서 검증, 구현 검사, 배포 확인, 실제 T1/T2 시험을 따로 기록한다. Pilot 기원의 M2/M3 결과 반환은 후속 계약으로 다룬다.
