# Atlas E HTTP fixture 소비자 교차 검증

상태: 합성 HTTP 캡처 검증 통과, 운영/실제 모델/전체 API adapter 수락 아님.

fixture SHA-256: ee6d11cdc9a1739604d1320e17f93ea6e4bf4ab1684fdf35e44eb8769fc0e934

Pilot knowledge_protocol 검증 함수에서 instance/job/contract, 요청 canonical fingerprint·consumer receipt, 단계 결과 canonical hash/이력 참조, resume receipt를 대조했다. QA/page/전체 단계 artifact를 기존 chunk 검사기로 복원했다. answer ready는 partial/persisted 사이 동일하고 이전 partial 결과도 회수된다. submit replay 동일 job, 완료 뒤 resume replay 동일 receipt, 충돌409, invalid range400, past EOF416, 빈 EOF를 확인했다. 신규7개와 기존 패키지9개 총16개 테스트 통과. 검사 범위에서 생산자 불일치 없음.

제한: 캡처 재생이며 Pilot 네트워크 전송/인증/영속 관찰 원장 전체를 구현한 것은 아니다. info의 capability/한도와 오류 캡처는 확인했지만 운영 인증 왕복은 미실행. source는 별도 A1 실회수 미실행, package failure/restart는 생산자 시험 보고만 확인. 실제 Codex/임베딩 품질, 운영 배포/연구 수락을 뜻하지 않는다. 다음은 전용 연결 설정·HTTP 송수신·단계 원장 연결 후 격리 양방향 시험이다.
