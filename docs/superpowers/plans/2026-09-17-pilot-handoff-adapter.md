# Pilot 인계 어댑터 구현 계획

사용자가 승인한 Documents→Atlas 연결 구현을 기존 worktree에서 진행한다. 규범은 `docs/integrations/documents-atlas/contract-v1.md`, schema 차이는 `pilot-consumer-review-2026-09-17.md`를 따른다.

- [x] journal: Atlas 전송 payload/key 고정, 관측 snapshot 저장, 가변 ACK 필드 분리. 기존 기록 호환 유지.
- [x] 어댑터: capability/instance 확인, Documents operation별 영수증 복구, 공급자 package 값 검증, Atlas 접수/조회.
- [x] 결과: canonical hash 검증, 원형 결과 저장 후 ACK, 유실/재조회 안전성, 타 프로젝트 이벤트 ACK 제외.
- [x] 로컬 실행 진입점: 별도 0600 연결 파일, 단발/60초 관찰, 연구 상태 불변. 실제 접수는 명시적으로 준비한 journal 요청만 사용.
- [x] UI: 최신 관측 snapshot을 반영하고 결과 수신 상태 표시. 운영 빈 상태 유지.
- [x] 임시 HTTP 서비스의 응답 유실/진행/결과/ACK 시험, 기존 회귀 및 구현 경계 기록.

새 운영 요청은 제출하지 않는다. Documents capability가 비활성인 동안 실제 송신은 차단한다. 테스트용 supplier capability는 합성 서비스에서만 선언한다. 두 서비스의 비밀은 journal/UI에 저장하지 않는다.
