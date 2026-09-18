# Pilot 소비자 검토 — knowledge update v1

상태: R1~R3 보완 본문 확인 후 계약 최종 수용. 아래 1차 보완 요청은 검토 이력이다. 사용자 정책 재승인 불필요. 코드/운영/연구 변경 없음.

검토 본문 SHA-256: f1d074f9e5e6811acaf54469933b7299dd3cd4eae5e6096b8aa8eefb7a4b5fde

## 수용

별도 계약·knowledge-jobs·전용 consumer·project allowlist·초기 polling 수용. 기존 ask/import 의미·권한 유지. QA 준비 전 입력 원형 고정, manifest/단일10MiB·전체64MiB·chunk4MiB 한도 및 자동 만료 없음 수용(한도는 디코딩 원형 바이트 기준 명시). source는 같은 instance의 A1 인증으로 별도 회수. answer/knowledge 분리와 partial, persisted에 색인 완료 포함을 수용하며 Pilot UI는 persistence/index_status를 각각 사용한다. expected_revision 기반 재개 멱등도 수용.

## R1. 회수 가능한 원형 패키지·인증 계약

manifest의 필수 schema와 예제를 고정해야 한다. schema version, instance/job/QA identity, 각 artifact ID/종류/전체 sha256/size/인코딩, consulted page ID/hash와 artifact 매핑, source ID/version/hash/locator 및 QA 후보 식별자를 포함한다. manifest package_ref.sha256가 원형 manifest 바이트 hash인지 canonical record hash인지 명시하고 자신을 해시하는 순환을 피한다. QA hash는 YAML 포함 전체 원형 파일 hash를 유지한다.

chunk 요청 offset/limit은 디코딩 바이트 단위, eof일 때 next_offset=null, 빈 artifact·offset=size·범위 초과의 응답을 명시한다. source 참조로 페이지를 통해 간접 발견하지 않고 필요한 원문 버전을 회수할 수 있어야 한다.

전용 토큰으로 info를 조회할 수 있는지와 capability/한도/instance 회수 방법을 명시한다. A1 source 인증은 별도 연결이며 같은 instance 대조가 필요하다. A1 연결이 없거나 source를 받지 못해도 answer 패키지 저장은 가능하나 해당 원문을 Pilot이 확인했다고 표시하지 않는다.

수락시험: manifest→QA/page artifact 전체 회수 및 byte hash 대조, 경계 chunk, 다른 instance의 A1 source 연결 차단, A1 미연결 시 원형 확인 범위 정확한 표시.

## R2. 재개 전 단계 결과의 후속 회수

이전 단계 결과를 보존한다고 했지만 현재 GET 예시는 최신 knowledge.result 하나뿐이다. Pilot이 partial 결과를 보기 전에 resume가 진행되거나 소비자가 재시작하면 이전 immutable 결과를 어떻게 회수하는지 명시해야 한다. 기존 GET에 attempts/result_refs와 artifact 조회 매핑을 제공하는 방식이면 새 endpoint는 필요 없다. 각 결과에는 instance/job/stage/attempt/schema_version을 고정하거나 envelope와 검증 가능한 연결을 제공한다. QA-local candidate ID는 qa_ref와 함께 식별한다.

resume 동일 expected_revision 재전송은 현재 revision이 이미 증가했어도 기존 attempt를 반환하도록 명시한다. 최초 유효 resume만 상태 조건을 검사하고 이미 수락한 재전송은 성공 복구한다. 그 뒤 새 attempt가 있어도 예전 재전송이 추가 실행을 만들지 않아야 한다. known result를 가져온 뒤 answer/knowledge별로 중복 전달을 막을 수 있어야 한다.

수락시험: partial→resume→persisted 동안 Pilot 비접속 후 모든 결과 참조 회수, 동일 resume 응답 유실·완료 후 재전송·다음 attempt 후 재전송에서 실행 수 불변.

## R3. answer 패키지 차단 상태의 복구

QA는 생성됐지만 package_too_large/디스크 부족/input_snapshot_mismatch로 ready가 안 된 경우가 있다. 현재 resume는 update만 허용하므로 이 작업이 영구 대기하는지, 패키지 고정 단계만 복구 가능한지 불명확하다. answer.status에 blocked 추가 또는 실패/error+명확한 parent 상태를 정의하고 오류별 재개 가능 조건을 고정한다.

원래 snapshot이 남아 있으면 QA 재생성 없이 패키지 단계만 재시도할 수 있다. 원형이 사라진 hash mismatch는 최신본 대체 금지이며 복구 불가 또는 별도 새 의뢰 필요로 표시한다. 일반 resume를 확대하지 않더라도 명시적인 진단/운영 복구 절차를 계약에 적어 무한 정상 대기처럼 보이지 않게 한다.

수락시험: QA 생성 후 패키지 저장 실패·재시작 시 ask 중복 실행 없음, 회수 불가능한 원형은 ready로 승격되지 않음.

## 추가 명료화(위 보완에 포함 권고)

접수 영수증은 실행 보증이 아니다. dispatch 실패/고아 작업은 phase/error에서 관측 가능해야 한다. 보존된 부모 접수 후 실행기 재시작 시 미실행 child 접수와 이미 실행된 child 재실행을 구분한다. user stop 이후 Pilot은 신규 resume를 보내지 않는다. 공개 cancel이 없음을 UI에 표시한다.

계약의 실제 필드·오류 fixture를 확보하면 Pilot adapter를 작성한다. 세 보완은 전체 설계를 바꾸는 요구가 아니며 원장·범위제한 단위 개발과 병행 검토 가능하다. 최종 계약 수용 전에는 외부 표면 확정/운영 적용을 하지 않는다.

## 최종 수용 — 2026-09-18

계약 본문 SHA-256: 5be9367420bd97248e72564f793fff11c85567ee4436c9997e4f8ce36d655560
구현 계획 SHA-256: 118d9a12c20e5ba3a208ee53b61392310eea8b049796f7258ae076b93f625dd3

R1: manifest 바이트 hash/identity/QA-local 후보 복합키, decoded byte 경계, info·전용 인증과 A1 분리 명시 확인.
R2: GET 전체 attempts/stage_results와 artifact 재회수, resume ledger 우선조회 및 완료·후속 attempt 이후 replay 보장 확인.
R3: answer.blocked/knowledge.not_started와 package 복구, 원형 소실·크기 초과 새 의뢰 판단, ask 재생성 금지 확인.

남은 계약 차단 사유 없음. 기존 담당 세션에서 작은 단위별 구현과 격리 검증 진행 가능. 기존 A1/import 의미 보존, 운영 배포·실제 자료 갱신·기존 job 재접수는 포함하지 않는다. 이 수용은 설계 검토이며 실행 테스트 통과나 구현 완료가 아니다. Atlas 구현 fixture를 받으면 Pilot 소비자 adapter와 교차 검증한다.
