# Pilot 검토 — Atlas A1 구현 계획

2026-09-13 · **구현 계획 수용. 착수를 막는 계약·구조 문제 없음.** 아래 보완은 확정 계약을 변경하지 않는 구현·수락 시험 구체화다. Atlas는 Task 0부터 진행할 수 있으며 별도 재승인 회신을 기다릴 필요는 없다. 필수 검증은 해당 Task 완료·배포 전에 충족한다.

검토 대상: [Atlas A1 계획](/Users/jspark/orca/projects/ResearchAtlas/docs/superpowers/plans/2026-09-13-pilot-atlas-v1-a1.md), 검토 시 SHA-256 `5989a7f481d267b38591e54aa402564f8fe41e7dd41c5fe0e323773eadeaea85`.

기준: [공동 계약](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1.md), [수락 기준](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/researchpilot/api-mcp-v1-acceptance.md), [Pilot 최종 수용](pilot-review-v1.md). 계획·현재 Pilot 수신 코드의 읽기 검토이며 구현이나 실서비스 시험을 수행한 결과가 아니다.

## 수용한 구조와 작업 경계

- Task 0의 미커밋 기존 서비스 기준 고정, 기존 main 사용, 운영서버 사전 중단 금지를 수용한다. Pilot의 별도 작업 경로에 Atlas의 main 방침을 적용하거나 변경하지 않는다.
- Task 1–3의 작은 공통 모듈, 명시적 identity 초기화, 단일 읽기의 raw/record, lifecycle 별도 실패를 수용한다.
- Task 4의 legacy 요청 보존과 v1 ask 분기, 기존 job backfill 금지, 정확한 qa_ref·consulted_pages 반환을 수용한다.
- Task 5에서 HTTP와 MCP가 공통 서비스를 사용하고 실제 프로토콜 오류까지 검증하는 방향을 수용한다. Pilot이 HTTP부터 연결하는 것과 충돌하지 않는다.
- Task 6의 합성 자료실 검증→배포→실제 T1 순서, A1 준비와 Pilot T1 완료의 분리를 수용한다. A0·업로드·지정 analyze를 기다릴 필요가 없다.

## 해당 Task 완료 전에 추가할 필수 검증

| ID / Task | 보완할 사례 | 완료 기준 |
| --- | --- | --- |
| V1 / 4·5 | 같은 request_key를 HTTP/MCP에서 동시에 제출, 접수 응답 유실 후 재전송, queued 작업에 동시 execute | 동일 job·fingerprint·receipt이며 worker 실행은 최대 한 번이다. 단순 순차 재전송 시험 외에 동시성·응답 유실 사례를 포함한다. 실행 전이의 원자성은 기존 단일 worker 구현에서 검증한다. |
| V2 / 2·4·5 | QA가 10 MiB 초과이거나 사라진 기존 job 조회 | QA export 불가가 기존 job을 failed로 바꾸거나 저장 기록을 변경하지 않는다. 초과 QA의 파일 해시 계산과 raw export 상한을 구분한다. legacy job의 읽기 전용 qa_ref 보완 실패 때문에 job 상태 자체를 조회할 수 없게 만들지 않는다. 없는 원기록 참조를 만들어내지 않는다. |
| V3 / 2·5·6 | 합성 QA 원형과 실제 T1 원형을 Pilot 기존 parse_atlas_qa에 전달 | 파일 해시·질문·답변·project·consulted_pages·candidates가 기대대로 해석된다. Pilot에는 중복 YAML 키·alias·깊이·노드 수 검사가 있으므로 ‘10 MiB 이내’만으로 수입 성공을 판단하지 않는다. Atlas 서버에 Pilot 모듈 의존성을 추가하지 않고 Pilot 측 호환 시험으로 확인한다. |
| V4 / 4·5 | 같은 키의 legacy↔v1 교차 재전송, 잘못된 project, 미지원 버전/기능 | 기존 row·payload·이벤트 불변. project 오류를 null로 바꾸지 않는다. 미지원 버전은400, 알려진 계약의 미지원 analyze/ingest 기능은503 capability_unavailable이며 새 job을 만들거나 실행하지 않는다. |
| V5 / 3·5·6 | A1 capability의 양쪽 transport 의미와 재기동 | HTTP/MCP 모두 qa raw/record/lifecycle, page raw, ask 문맥·receipt·근거를 제공한 뒤 묶음 capability를 광고한다. source 다운로드도 실제 T1에서 길이·해시를 확인한다. 서비스 URL/토큰 변경 후 같은 instance를 확인하고 기존 job을 조회할 수 있어야 한다. |
| V6 / 6 | 배포 직전 새 job 접수와 재시작 경쟁 | 활성 job을 한 번 읽은 사실만으로 안전한 교체를 보장하지 않는다. 기존 종료/배포 절차에서 실행과 신규 접수를 조정하고 재확인한다. 실행 중이면 배포를 미루며 강제 종료·자동 recover·자동 재실행을 하지 않는다. 배포 뒤 이전 job/QA/source 보존을 확인한다. |

V2는 계약 확대 요청이 아니다. 계약에 이미 있는 ‘원형 export 오류와 job 상태 분리’를 Task 4의 legacy qa_ref 동적 보완에도 적용하는 것이다. 참조를 얻을 수 없는 상황의 표현은 기존 호환 필드와 오류 규칙 안에서 정하고, 정상 참조처럼 위장하지 않는다.

## 구현 범위를 키우지 않을 주의점

Task 1의 source 집합 정규화 시험은 공통 함수 단위로 수행할 수 있다. 이를 위해 analyze나 업로드 endpoint를 먼저 구현하지 않는다. link/commit의 target_id는 내부 정규화 입력이며 확정 HTTP/MCP 요청에 새로운 필수 필드를 추가하지 않는다.

Task 0의 보존 자료는 코드·설정 식별 정보와 원기록의 비교 가능한 목록/해시를 중심으로 한다. 전체 자료실 내용을 문서나 모델 문맥에 복제하지 않는다. 활성 서비스가 쓰는 SQLite는 일관된 백업 방법을 사용하며, 활성 job이 만든 정당한 변경과 마이그레이션으로 인한 변경을 구분한다. 토큰·연결 파일 원문은 검토 산출물에 남기지 않는다.

10 MiB 경계 시험은 encode_raw helper뿐 아니라 유효한 QA의 실제 HTTP/MCP 반환에서도 수행한다. 임시 자료실에만 경계 fixture를 만들고 운영 자료를 부풀리지 않는다.

## Pilot P0–P3 병행 준비

**가능하다.** 계약은 확정됐으므로 Atlas 구현 완료를 기다리지 않고 설계·fixture 기반 준비를 진행할 수 있다. 다만 이 검토는 Pilot 코드 구현 착수·완료를 뜻하지 않는다. Pilot의 진행 중인 구현 브레인스토밍과 별도 실행 계획에서 작업을 구체화한다.

| 작업 | 지금 준비 가능한 것 | Atlas 의존 / 완료 증거 |
| --- | --- | --- |
| P1 연결 클라이언트 | 연결 정보 읽기, HTTP 통신 경계, info/capability·오류 해석과 합성 응답 시험 | Task 5 후 실제 연결; 토큰 비노출·instance 일치·QA/page 수신 |
| P0 프로젝트 바인딩 | 기존 Pilot 연구→기존 Atlas project ID·instance·이유 기록, 변경 이력과 이전 요청 불변 | 프로젝트 목록과 info 실제 확인. A0 생성은 불필요 |
| P2 요청 기록 | 전송 전 질문·키·binding 저장, job/receipt 회수, 응답 유실·재시작 상태 설계 | Task 4·5 후 같은 키 재전송·단일 실행 공동 검증 |
| P3 원형 수신·등록 | 합성 QA로 기존 파서/import 경로 연결, 해시·중복·연구 head 충돌 처리 설계 | Task 2·5 후 실제 raw 보존→등록. 네트워크 재시도와 Pilot 등록 재시도 분리 |

현재 Pilot의 atlas_http.py는 Pilot UI의 QA 가져오기 요청을 받는 로컬 어댑터이고 Atlas 서비스 호출 클라이언트가 아니다. atlas_intake.py의 import_qa와 core/research_graph/atlas_format.py의 parse_atlas_qa는 재사용할 수 있다. UI 파일 업로드를 서비스 연결로 대체하는 부분, 바인딩·요청 영속화는 별도 준비가 필요하다.

Pilot 첫 연결은 HTTP를 기본 후보로 설계 중이다. Atlas MCP 구현은 같은 계약의 도구 접근을 보장하며, Pilot에 두 개의 연구 상태 저장소나 별도 실행기를 요구하지 않는다.

## Atlas 완료 회신에 필요한 정보

1. 배포 코드 식별자, 자동 검사 결과, 실제 광고 capability 및 미지원 기능.
2. 토큰을 제외한 연결 방법과 instance ID, 기존 T1 프로젝트 확인 방법.
3. 합성 HTTP/MCP 원형·오류·중복 요청 검증 결과와 아직 수행하지 않은 항목.
4. 운영 배포 여부·기존 기록 보존 결과. Pilot이 아직 준비되지 않았으면 T1은 미실행으로 표시.

실제 T1은 기존 프로젝트 선택→질문→job→QA·필요 page/source 원형→Pilot 사용 판단→후속 질문이다. 전송 성공, 근거 사용 판단, M1 완료는 각각 기록한다. Atlas A1 착수는 수용하며, Pilot 수신 준비와 실제 T1은 별도 담당 작업으로 이어간다.
