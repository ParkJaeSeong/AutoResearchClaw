# Pilot 개별 검토 관찰기

기존 완료 이벤트 수신 → 고정 입력 준비 → 전문가 토론 → 검토 결과 영속 저장을 `researchclaw.codex.import_review_worker`로 연결했다. 명시 실행한 동안만 60초 간격으로 관찰한다. 컴퓨터 로그인 자동 시작/서비스 등록은 하지 않았다.

CLI 인자: 프로젝트 ROOT, --context JSON, --documents-connection, --import-connection, --a1-connection, --host, 선택 --watch. 연결 파일은 기존 0600 비밀 파일을 사용한다.

context는 기존 review-context의 질문·버전·목적·정책에 프로젝트 내부 상대 경로 question_source를 추가한다. 파일 해시와 질문 본문을 매 실행 대조하며 변경 시 자동 실행을 멈춘다. 새 질문의 검토는 새 버전으로 명시 등록한다.

기존 검토 결과를 버전 대조 후 저장해 완료 토론은 다시 실행하지 않는다. 실패·질문 변경은 관련 기록을 보존하며 오류 시 관찰 명령은 종료한다. 이미 저장된 결과와 ACK를 재대조할 수 있다. 프로젝트별 worker.lock은 이 실행기의 중복 실행을 막으며 모든 수동 연구 명령을 통합 직렬화하지는 않는다.

새 토론은 .document-handoff/review-runs/작업ID 아래에 입력·회차·응답·활동·결과를 보존한다. 검토 결과는 journal의 task에 해시와 함께 저장한다. 가설 채택, 수집 실행, 묶음 종합, UI 표시 및 M1 완료는 별도 후속 기능이다.

실제 PC/CNT 확인: 기존 토론 1건 재사용, 모델 재실행 0, 오류 0, HEAD 불변. 새 역할 프롬프트로 기존 토론을 반복하지 않았다. 운영 관찰기의 활성 상태는 프로세스 실행 여부와 observations.jsonl로 확인한다.
