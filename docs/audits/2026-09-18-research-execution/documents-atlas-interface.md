# Documents·Atlas 인터페이스 추가 감사

2026-09-18. Pilot 소비자 코드와 양 공급자의 배포 기록을 읽어 기존 감사의 인터페이스 범위를 보완했다. 현재 운영 API 호출·재접수·서비스 변경·공급자 전체 코드 감사는 하지 않았다. 배포 기록은 당시 증거이며 현재 가동 상태 보증이 아니다.

## 경로별 확인

| 경로 | 확인된 기반 | 남은 연결/검증 |
| --- | --- | --- |
| Pilot→Documents 변환 접수 | operation별 영수증 복구, 전용 인증, instance/config/회수 consumer 고정, 원문 hash 확인 | 연구 작업의 시작 훅·정지 정책·공통 UI와 묶여야 함 |
| Documents→Atlas 회수/지식 정리 | 두 공급자 운영 배포 기록에 제출자 pilot-production→회수자 atlas-production 매핑 존재. Atlas import를 별도 접수하고 공급자 package 값을 고정 | 현재 서비스 capability 재검증 및 공급자 내부 복구 전체 감사는 별도; 변환 완료≠Atlas 완료 |
| Atlas import→Pilot 수신 | import identity/receipt/result hash 확인, 결과 로컬 저장 뒤 event ACK, 빈 tail cursor 보존 | ACK는 검토·채택이 아님. 수신 후 검토 배정과 실패/재개를 공통 실행기에 연결 |
| Pilot→Atlas 일반 질의→답변 | A1 별도 인증, 영속 요청과 원형 수신·검증, 별도 inbox/검토 경로 | 답변 저장에서 끝나는 followup 경로 존재. 원래 역할·현재 입력 버전에 반환하고 후속 판단을 실행해야 함 |
| Atlas 지식 반영 E | 별도 knowledge-jobs, answer/knowledge 단계 원형, partial→resume→persisted 및 replay의 격리 공동 시험 기록 | fake ask 기반 시험과 실제 모델/운영 활성화 구분. 일반 ask나 import 이벤트와 동일한 작업으로 취급 금지 |

## 직접 확인한 소비자 근거

- `researchclaw/codex/document_handoff_adapter.py:34`: Atlas instance/capability 확인.
- 같은 파일 `:75`: Documents instance/capability, operation별 영수증과 consumer/config 확인. `:98` 이후 supplier package_fingerprint/input_fingerprint를 사용하며 request_sha256을 대신 쓰지 않는다.
- `:142–149`: 소유한 이벤트 저장 후 cursor 저장. **현재 프로젝트에 매칭되지 않는 이벤트는 건너뛴다.** 프로젝트별 독립 관찰기 전제와 DOC-22의 공통 consumer 수신함 설계가 다르다. 신규/미연결 import가 cursor 이전에 나타나는 경우와 타 프로젝트 관찰기 부재에서 재분배·복구가 가능한지 추가 수락 시험이 필요하다. 이 정적 검사만으로 실제 이벤트 유실을 단정하지 않는다.
- `:165–171`: 저장·처리된 이벤트 ACK. `:175` 이후 result identity/hash와 completed/partial 필수 필드 검증. 실패 진단 수신은 과학 검토 착수를 뜻하지 않는다.
- `document_handoff_runner.py:30`: 접수 진행이 실패해도 이미 접수된 작업 관찰을 시도한다. `--watch`의 Pilot 60초 관찰과 Atlas의 Documents 600초 조회는 다른 주기다.
- `import_review_worker.py:33–35`: 토론 전체 완료 뒤 그래프 게시. `:54`의 게시 검사는 현재 질문/정책 버전 재확인까지 포함하지 않는다. 상세는 [Pilot 실행 감사](pilot-runtime.md).
- `knowledge_session.py:35–39`: 전용 capability/계약/프로젝트 허용 확인. 원형 회수·observe·revision resume는 별도 원장을 사용한다. 연구 채택을 자동 보증하는 API가 아니다.

## 공급자 기록과 검증 범위

읽은 원문:

- `/Users/jspark/orca/documents/doc/integrations/pilot-atlas/production-activation-2026-09-17.md`: 운영8010 활성화, 제출/회수자 분리, 인증/ACK 보호, 합성 운영 분리와 후속 웹 관리 정책.
- `/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/documents-atlas/production-deployment-2026-09-17.md`: 운영18765 documents_import_v1 활성화, 기존 A1 인증 유지, 당시 실제 인증 검증. OS 자동 시작은 포함하지 않음.
- `docs/integrations/documents-atlas/pilot-adapter-2026-09-17.md`: 소비자 접수/복구/ACK/관찰 구현과 당시 시험 한계.
- `docs/integrations/researchatlas/knowledge-update-live-check-2026-09-18.md`: E 격리 재시작/replay/오프라인 원형 검증; 실제 연구 품질·운영 수락 아님.

## 재설계 때 보존할 것과 추가할 것

이미 만든 receipt·멱등키·instance/project 바인딩·원형 hash·권한 분리·ACK 보호·단계별 결과를 보존한다. API를 무조건 다시 만들 사유는 없다. Pilot 공통 실행기에 각 프로토콜을 연결하는 어댑터를 둔다.

공통 경계는 `의뢰 기록→접수 확인→대기→원형 수신→입력 검사→담당 검토→채택/보류→후속 작업`이다. 각 단계마다 work/attempt/input revision과 원격 task/import/job/result_ref를 연결하고 UI에 상태·이유를 게시한다. 외부 completed, inbox ACK, 검토 종료, 연구 채택, M1 완료는 별도 상태로 유지한다.

추가 수락 사례: 접수 응답 유실, 원형 hash 불일치, ACK 유실/후 재시작, 타 프로젝트 이벤트, 늦은 결과 도착 전 질문 변경, partial이지만 유효한 근거 수신, 실패 진단만 수신, stopped 프로젝트에 완료 도착, 검토 완료 후 다음 작업 배정 실패, A1/E/import 서로 다른 인증·결과의 혼입. 기존 계약 시험의 재사용 범위와 새 공통 실행기 종단 시험을 구분한다.
