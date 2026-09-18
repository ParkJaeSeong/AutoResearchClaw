# 현재 API·MCP 검토

[전체 줄거리](README.md) · [계약 제안](contracts.md) · [작업 단위](tasks.md)

2026-09-13 로컬 소스 정적 검토. 실행 중인 서비스의 동작·설정이나 과학적 분석 품질은 이번에 시험하지 않았다. Atlas의 기존 검증 보고는 별도 프로젝트가 수행한 기록이며 이번 Pilot 통합 시험 결과로 세지 않는다.

## 현재 제공되는 인터페이스

| HTTP | MCP | 실제 범위와 한계 |
| --- | --- | --- |
| GET /api/stats, /api/projects | atlas_stats, atlas_projects | 보유 현황·프로젝트 목록. 프로젝트는 접근 권한 경계가 아님 |
| GET /api/sources | atlas_sources | 등록 source ID·버전·해시·페이지 목록, 페이지네이션 |
| GET /api/search | atlas_search | BM25/vector/hybrid, project/project_only, limit/offset. 외부 웹 검색 아님 |
| GET /api/pages/{id} | atlas_page | expected_sha256은 YAML 포함 파일 해시, markdown은 본문. 다르면409; 원형/과거 버전 조회는 별도 보완 |
| GET /api/sources/{id}/versions/{version} | atlas_source | 전체 원본 해시를 확인하고 base64 묶음 반환. next_offset/eof로 전체 수신 확인 |
| GET /api/sources/{id}/versions/{version}/file | 직접 대응 도구 없음 | 원본 파일 바이트. MCP에서는 atlas_source로 이어 읽기 |
| GET /api/research | atlas_research | 연구 내용·조건·저자/Atlas 구분 조회. page/kind/attribution/term 필터; 프로젝트 필터는 직접 제공하지 않음 |
| POST /api/jobs | atlas_submit | ask/ingest 접수, execute=true이면 실행 요청 |
| GET /api/jobs/{id} | atlas_job | 상태·답변·일부 결과·실행 오류 |
| GET /api/jobs | 직접 대응 도구 없음 | 작업 목록. MCP 클라이언트는 보관한 작업 ID로 조회 가능 |
| POST /api/jobs/{id}/execute | atlas_execute | queued 작업 실행 |
| POST /api/jobs/recover | 직접 대응 도구 없음 | 남은 에이전트가 없는 고아 running 기록 정리. 자동 이어 실행 아님 |

MCP는 기존 HTTP 서비스를 호출하는 stdio 어댑터다. 별도 worker를 만들지 않는다. 연결 파일의 URL·토큰을 읽고 localhost HTTP 인증을 사용한다. 토큰은 문서·프롬프트·Git에 저장하지 않는다.

## 확인한 공백과 영향

| ID | 실제 확인 | M1에서 막히는 부분 | 담당/판단 |
| --- | --- | --- | --- |
| G1 | HTTP/MCP에 새 파일 업로드·queue 등록 경로 없음 | Pilot이 새로 확보한 파일을 전송하고 분석 대상 ID를 받는 자동 연결 | Atlas 접수 API; Pilot 전송 어댑터 |
| G2 | ask는 question/project만 허용하며 items/retry 거절. ingest는 question 거절, items와 project 동시 지정 거절 | 특정 논문 버전들에 특정 분석 질문을 묶을 수 없음 | Atlas의 명시적 분석 계약 필요 |
| G3 | ask 내부 결과에 consulted_pages가 있으나 public_job 허용 목록에서 제외 | 실제 답변이 참고한 페이지·해시 회수 부족 | Atlas 공개 응답 보완 |
| G4 | QA ID·경로는 제공하지만 QA 원기록 조회 경로/도구 없음 | 원래 답변·참조·후보를 보존하는 Pilot 기존 QA import에 직접 연결 불가 | 안전한 QA 원기록 조회/내보내기 필요 |
| G5 | JobRequest에 source_refs, analysis_goal, previous_analysis_id, Pilot 쟁점 참조 등 없음 | 지정 자료 분석·후속 분석을 기계적으로 검증하기 어려움 | 질문 문자열에 적는 임시 방식과 정식 보장을 구분 |
| G6 | 페이지 단위 변경 감지와 고정 source 버전은 있으나 다중 자료 snapshot·알림은 없음 | 협의 중 입력이 달라질 수 있음 | 우선 Pilot이 수신 바이트와 해시를 고정; Atlas에 범위 고정 분석 추가 |
| G7 | API job 응답에는 명시적 분석 결과 스키마가 없음 | 답변 문장에서 주장·조건·미확인 사항을 다시 추측해 파싱 | Atlas 버전 있는 결과 계약 필요 |
| G8 | 자동 재개 없음, HTTP 작업 목록/recover에 MCP 직접 대응 없음 | 재시작 후 요청 중복·잘못된 새 실행 위험 | Pilot 영속 작업 기록 우선. 운영 MCP 보완은 후속 |
| G9 | 현재 연구 내용 attribution은 author_report/author_interpretation/atlas_interpretation/atlas_proposal | Pilot 가설·결과를 되돌려 축적할 때 출처 의미 손실 가능 | M2/M3 반환 계약에서 Pilot 기원과 결과 상태를 추가 설계 |
| G10 | 프로젝트 생성·source/input 연결은 내부/CLI에 있지만 HTTP/MCP는 목록 조회만 제공 | 자동 프로젝트 시작·자료 연결 공백 | Atlas 서비스와 Pilot ID 연결 기록 |
| G11 | 신규 queue 입력은 input_id/sha256과 source_id/version=null일 수 있음 | 접수 즉시 source를 요구하면 기존 정책과 충돌 | input→ingest→source 매핑 우선 |
| G12 | 페이지 해시는 전체 파일, markdown은 본문. QA input_sha256도 파일 해시와 다름 | 원형 동일성을 잘못 검증할 위험 | 원형 바이트·파일 해시 명시 |
| G13 | documents 호출은 위임 실행기에서 제외 | 접수·분석 API만으로 PDF 변환이 연결되지 않음 | A2b 변환 산출물과 원본 해시 대응 |

G3의 consulted_pages만 공개해도 원기록 전체, 주장별 근거 연결, 실제 읽은 범위까지 자동 충족되는 것은 아니다. QA에는 참고 페이지와 추가 후보의 source_refs를 보존할 구조가 있지만 모든 답변 주장에 근거를 요구하는 분석 계약과는 다르다.

## Atlas 개선안 수용·정정

[Atlas 검토 문서](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/m1-api-mcp-review-2026-09-13.md)의 G1–G9 확인과 추가 정정을 반영했다.

- 별도 material_id를 우선 만들지 않고 input_id를 사용한다. 최신 공동 결정안은 기존 jobs의 kind=analyze와 불변 결과 참조를 사용하고 별도 analysis_id를 만들지 않는 것이다.
- QA 원기록은 불변이며 archive/후보 상태는 이벤트에서 계산한다. raw/record와 lifecycle을 분리한다.
- 지정 자료 제한은 결과의 채택 근거를 검증한다. 파일 접근 격리로 과장하지 않는다.
- A2 접수 멱등성과 파일 중복 제거는 다르다. 프로젝트·발견 이유 변경과 재전송을 구분한다.
- 프로젝트의 범위·ID 연결은 [별도 문서](projects.md)에 추가했다. 여러 Pilot 연구가 Atlas 프로젝트를 공유해도 근거 버전·판단은 독립적으로 유지한다.

## 프로젝트 범위 정정

Atlas 일반 자료·질문은 project=null을 허용한다. 기본 프로젝트 연결 요구는 Pilot M1 의뢰에만 적용한다. 선택 프로젝트에서 project_only=false는 공용 wiki 보완이며 다른 프로젝트 전용 페이지까지 자동 포함하지 않는다. 다른 프로젝트 해석은 해당 프로젝트를 별도 조회한다.

## 프로젝트 코드 대조

Library.project_create(title)와 CLI project create는 이미 있다. 현재 같은 제목이면 기존 프로젝트를 반환하므로 서비스 요청의 범위·멱등성·동명 충돌을 별도로 설계한다. Library.project_attach는 source 버전을, Workflow.attach는 queue 입력을 프로젝트에 연결한다. HTTP/MCP에는 이 변경 기능이 미노출이다.

project_attach는 명시 버전으로 갱신할 수 있고 버전을 생략한 재연결은 기존 버전을 유지할 수 있다. 프로젝트 자료 목록을 자동 최신 근거 묶음으로 해석하지 않는다. 프로젝트는 접근 권한 경계가 아니다.

## 재사용할 수 있는 것

- request_key와 내용이 같으면 기존 작업을 반환하고, 같은 키로 다른 내용을 보내면 거절한다.
- 자료실당 위임 작업 하나씩 실행하며 접수·실행을 분리한다. Pilot은 허용 범위 안에서 명시적으로 실행 요청할 수 있다.
- 서버 재시작 시 queued/running을 자동 완료·재실행하지 않는다. 부분 결과·중단 상태를 보존한다.
- source ID/버전/해시, YAML 포함 전체 파일 해시, 저자/Atlas 해석 구분을 재사용한다.
- ingest는 기존 등록 입력을 분석·위키화하는 기반이다. 질문과 자료를 함께 받는 신규 계약은 이 실행·보존 체계를 확장하는 것이 적절하다.
- Pilot의 현행 QA Markdown import·외부 근거 묶음·독립 검토·준비 검증·M2 인계에 연결한다. API 답변 수신만으로 이를 완료 처리하지 않는다.

## 오류와 시간의 의미

MCP HTTP 클라이언트의 timeout=60은 개별 HTTP 요청의 응답 대기다. 비동기 모델 작업 전체를60초 후 종료하는 계약이 아니다. 클라이언트 통신 실패를 작업 실패로 단정하거나 새 request_key로 다시 실행하지 않는다.

상태 조회 HTTP200/ok=true와 job.status=completed는 다르다. completed도 과학적 정답 보장이 아니다. 명시적 오류 코드가 있는 ServiceError 외에 일반 ValueError는 error 메시지만 반환할 수 있으므로 Pilot은 모든 실패에 error_code가 있다고 가정하면 안 된다.

## 검토 근거

Atlas 소스 루트: `/Users/jspark/orca/projects/ResearchAtlas`.

- [서비스 문서](/Users/jspark/orca/projects/ResearchAtlas/docs/local-service.md), [위임 작업 문서](/Users/jspark/orca/projects/ResearchAtlas/docs/delegated-jobs.md).
- [server.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/server.py:18): 닫힌 요청 형식, 공개 결과 허용 목록, 전체 HTTP 라우트.
- [mcp_server.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/mcp_server.py:32): 실제 도구 서명, HTTP 공통 호출, 요청 timeout.
- [jobs.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/jobs.py:42): ask/ingest 제약, queue ID 검사, 요청 키 중복 처리.
- [job_runner.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/job_runner.py:17): 실행 시 범위 확정, 외부 검색 제외, 기존 batch 이어 처리.
- [job_results.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/job_results.py:45): QA 대조와 consulted_pages 내부 결과.
- [service.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/service.py:148): 페이지 변경 감지, 원문 바이트·해시, 검색/연구 조회.
- [qa.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/qa.py:34): QA 참고 페이지·후보 source refs 보존.
- [research_content.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/research_content.py:7): 해석 주체의 지원 값.
- [library.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/library.py:152), [workflow.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/workflow.py:117), [cli.py](/Users/jspark/orca/projects/ResearchAtlas/src/researchatlas/cli.py:84): 프로젝트 생성·연결, input 접수와 선택적 source 참조.
- Pilot [QA 파일 연결](../../research/guides/atlas-file-evidence.md), [준비·인계](../../research/guides/m1-preparation-handoff.md).

현재 미노출 기능은 위 HTTP/MCP 표면 기준이다. 별도 CLI·내부 라이브러리의 기능 부재를 뜻하지 않는다.
