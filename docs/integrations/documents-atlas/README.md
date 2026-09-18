# Pilot–Documents–Atlas 문서 지식화 연계

- [v1 규범 본문](contract-v1.md): 책임·MCP/HTTP·접수·600초 조회·원형/변환 버전·회수·지식화·이벤트/ACK·보관·수락 시험.
- [공동 수용 기록](agreement-v1.md): 담당별 판정과 정확한 본문 해시. 구현·배포 상태와 구분한다.
- [초기 검토안](polling-handoff-proposal-2026-09-17.md): 논의 경과이며 최종 계약의 대체가 아니다.

Pilot이 Documents에 변환을 요청하고 Atlas에 해당 작업의 지식화를 의뢰한다. Atlas는 Documents를 600초 간격으로 조회한다. Pilot 서비스는 Atlas 이벤트를 60초 간격으로 조회하고 영속 저장 후 ACK한다. 현재 연구는 계약 구현과 검증 전까지 재개하지 않는다.

## Pilot 구현 현황 · 2026-09-17

첫 구현 단위인 `researchclaw/codex/document_handoff.py`의 `HandoffJournal`을 추가했다. 프로젝트·Atlas instance·consumer에 고정된 SQLite 파일에 Documents 요청, 변환 영수증, Atlas 접수 대기와 영수증, 이벤트 원형·처리 결과·ACK 여부를 저장한다. Documents 영수증과 Atlas 전송 대기 전환은 한 트랜잭션이며 같은 요청을 다시 기록해도 중복 행을 만들지 않는다. 오래된 이벤트는 보존하지만 최신 관측 상태를 덮어쓰지 않는다.

이는 **전송 어댑터가 사용할 내부 저장 기반**이다. 서버 영수증·결과 해시·권한 검증은 아직 연결하지 않았으며 저장 메서드 호출 자체가 외부 계약 검증을 뜻하지 않는다. 실제 프로젝트에 DB를 만들거나 연구 HEAD를 변경하지 않았다. 운영 HTTP/MCP·60초 조회기·cursor 재조정·UI는 아직 연결하지 않았다. 기존 A1 질답은 유지된다.

검증: 신규 영속성/중복/격리/원자적 ACK 테스트 7개와 기존 Atlas service/CLI 회귀 21개, 총 28개 통과. 합성 임시 DB만 사용했다. 다음 단위는 양 서비스의 실제 schema에 맞춘 capability·identity 확인 및 접수/영수증 복구 어댑터다. 이후 결과 검증·이벤트 처리/ACK와 서비스 조회기·UI를 연결하고, 공동 수락 시험 후 실제 논문을 처리한다.

- [저장 기반 구현 계획](../../superpowers/plans/2026-09-17-pilot-handoff-journal.md)

### Pilot UI 연결 추가

‘자료와 근거’에 인계 목록을 연결했다. `/api/document-handoffs`가 프로젝트별 `.document-handoff/journal.sqlite3`를 읽기 전용으로 조회한다. DB가 없으면 빈 목록이며 임의로 생성하지 않는다. UI는 60초마다 이 **로컬 API**를 확인한다. Atlas 원격 이벤트 조회/ACK 구현과 구분한다. 상태 필터·접힌 상세·접수 참조와 마지막 조회 실패 보존을 지원하며 운영 8771 빈 상태를 확인했다. 전송 어댑터는 동일 저장 위치를 사용해야 한다. 결과 파일 수신·사용 판단은 아직 연결하지 않았다.

- [Atlas 첫 구현 소비자 검토](pilot-consumer-review-2026-09-17.md): 공급자 package fingerprint, 별도 요청 키 대응, 가변 ACK/진행 snapshot 분리와 후속 모의 통합 시험. 운영 연계 완료 판정은 아니다.

- [Pilot 연결 어댑터 구현·실행 경계](pilot-adapter-2026-09-17.md): Documents 영수증 복구, 별도 Atlas key, 진행 snapshot, 결과 검증/ACK, 합성 HTTP 시험. 실제 제출과 운영 연계는 별도 수락 대상이다.
