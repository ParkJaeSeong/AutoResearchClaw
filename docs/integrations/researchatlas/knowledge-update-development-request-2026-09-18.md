# Atlas 개발 요청 — 질의와 지식 반영

사용자가 통합 개발 목록의 추천안을 기준으로 개발 착수를 승인했다. Pilot은 기존 A1 답변 수신 분리를 구현 중이다. Atlas는 다음 범위의 구체 계약과 구현 계획을 작성하고 Pilot과 정렬한 뒤 구현을 진행한다. 현재 요청은 운영 배포나 실제 자료의 위키 변경 지시가 아니다.

기준: Pilot 통합 목록 docs/superpowers/plans/2026-09-18-pilot-integrated-development-roadmap.md E, Atlas의 pilot-service-request-review-2026-09-18.md 및 pilot-knowledge-feedback-review-2026-09-18.md.

운영 기본안: 원문 보고와 Atlas 해석을 구분하고 해석은 프로젝트에 보존. 문헌 요약은 공용 재사용, 프로젝트 해석 공용 승격은 별도. 답변과 근거가 보존됐다면 위키 반영 실패 중에도 Pilot 검토는 계속하며 해당 반영만 복구. 비공개 Pilot 가설은 공용 위키에 반영하지 않음.

Atlas 범위:
1. 기존 readonly ask를 유지하는 명시 복합 operation과 capability, HTTP/MCP 동일 의미, 쓰기 권한.
2. 이번 QA 후보만 처리하는 고정 범위. 전역 pending ingest 금지.
3. QA ready 이후 update 영속 연결과 단계별 불변 결과. 답변/위키 저장/색인/부분 실패 분리.
4. 자동 갱신 전 답변에 사용한 페이지 원형 고정·회수. 작업 한정 패키지로 크기/보관/회수 조건 명시. 범용 역사 API는 불필요.
5. 변경 직전 hash 대조, 후보별 처리 이유와 source/version/locator, before/after hash, 중복 쓰기 방지.
6. 답변 재생성 없이 실패 단계 재개. 초기 관찰은 job polling, import 이벤트/ACK 재사용 없음.

요청 산출물: 요청/응답 및 오류 예제, 단계 상태/결과 참조와 키 규칙, 인증/capability, 원형 패키지 계약, 구현 단위 및 격리 수락시험. Pilot 소비자 검토가 필요한 항목을 표시해 회신. Pilot은 공통 원장·에이전트 반환·단계별 전달 중복 방지·M1 실행 경계를 담당한다.

공동 시험: QA 이후 page 갱신/409, 답변 성공+반영 실패, 일부 후보 보류, 저장/resolve/색인 경계 중단과 복구, 재전송·독립 회차 비공개 보존.

기존 job-71f93df47d324b48은 재접수 금지. Pilot에서 completed 답변과 연결 근거 11건을 보존했고 연구 HEAD는 유지했다. 새 operation 적용을 위해 과거 readonly 요청을 쓰기로 승격하지 않는다.
