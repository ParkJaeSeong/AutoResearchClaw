# Pilot–Atlas E 격리 HTTP 공동 시험

상태: Pilot 실접수·partial 회수·resume·persisted·replay·오프라인 조회 통과. Atlas terminal 재시작 후 Pilot 재조회·replay·오프라인 원장 재검증 통과. 합성 자료/fake ask/고정 제안/합성 임베딩이며 실제 모델 품질·운영 수락 아님.

- instance: 2f835149-3547-452b-9998-1a719b8cf0e5
- project: project-ad72aa6670694977
- consumer: pilot-e-isolated
- URL: http://127.0.0.1:18769
- request_key: pilot-e-isolated-20260918-01
- job: knowledge-b29d857c04ae456f8231a8d741baf8ac
- Pilot 증거: output/evaluations/atlas-knowledge-live-20260918/ (비밀 정보 없음)

전용0600 연결의 url/token을 기존 안전한 AtlasClient HTTP transport로 사용했다. 토큰은 원장·로그에 저장하지 않았다. 별도 A1 info의 동일 instance 대조 후 source 원형1건154bytes를 회수해 manifest hash와 일치 확인했다.

revision4 partial에서 QA/page/manifest 및 answer·knowledge 결과를 SQLite objects/results에 저장했다. Atlas 제어 해제 후 expected_revision4로 resume를 제출해 attempt2/accepted_revision5를 받았다. revision6 persisted에서 answer hash 불변, 과거 partial 포함 단계3건을 확인했다. 완료 뒤 같은 revision4는 replay=true와 기존 영수증, 같은 request payload/key는 같은 job을 반환했다. 새 KnowledgeSession(client=None)으로 saved 상태와 전체 단계 결과를 조회해 원형 hash를 재검증했다.

Atlas 별도 보고: ask1회/제안1회, 페이지hash·mtime/answer/기존 단계2개 불변, 세 색인 current. 이는 Atlas 담당 측 관측이며 Pilot의 독립 프로세스 계수 측정으로 표시하지 않는다.

생산 코드: knowledge_session.py — 명시 submit/observe/resume, 영속 요청 intent, instance/project/consumer binding, 결과·artifact 저장. 공통 에이전트 inbox/UI/자동 resume와 아직 연결하지 않았다. 재개는 명시 호출만 수행한다. 운영18765/기존 연구job 미사용.

재시작 후 독립 Pilot 확인: info 동일 instance, GET 전체 body 재시작 전과 동일(revision6/persisted), revision4 resume replay 동일 영수증, client=None 재개에서 단계 원형3개 hash 검증 통과. 증거 restart-verification.json. 이 격리 시나리오의 공동 왕복 검사 완료이며 운영/실제 모델 검증은 별도다.
