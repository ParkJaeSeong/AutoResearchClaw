# Atlas 요청 회차 자동 기록

목표: 정식 연구 질문의 ask-question→advance 경로를 하나의 회차로 표시한다. 기존 Atlas 계약·요청 키·import 절차를 유지한다. 임의 일반 ask를 소급 변환하지 않는다.

1. atlas_request_episode.py에 어댑터를 추가한다. episode ID/command ID는 key와 작업 내용으로 결정하며 내용 변경은 충돌로 처리한다. 기존 apply_command HEAD 잠금·멱등 재요청을 사용한다.
2. atlas_question.py: 정식 질문 확인 후 요청 전 회차 시작, 송신 목적 기록. 접수 성공/불확실한 전송 오류를 구분한다. 원래 예외의 비밀 내용은 공개하지 않고 일반 오류 보고만 남긴다. 알 수 없는 질문/키 충돌은 회차를 만들지 않는다.
3. atlas_advance.py: research_context가 있는 요청만 자동 기록. waiting_for_atlas/needs_attention/수신 성공 및 진단용 부분 결과를 구분한다. 같은 상태 반복 조회로 회차/보고가 중복되지 않는다. 완료 후 재조회는 graph 불변. 미확보/오류 중에는 재개 가능한 같은 회차 유지; 유효 검토 입력이 고정되면 종료한다.
4. 정보 수신 회차는 review_required=false로 시작한다. 연구 판단은 후속 검토 회차의 개발 검토 대상으로 유지하며 수신을 과학적 승인으로 바꾸지 않는다.
5. 공개 기록은 요청 목적·job ID/status·고정 입력/evidence 참조만. token, raw exception, 원응답 본문이나 미공개 의견은 자동 복사하지 않는다.
6. 기존 완료 요청에 회차가 없으면 소급 생성하지 않는다. 새 요청의 전송 실패→동일 키 재개, 저장 후 receipt 유실, queued/running→partial/failed QA 또는 completed, key 충돌·권한 오류와 비밀 미노출을 테스트한다.

검증은 합성 remote client로 수행하고 실제 연구 요청을 새로 보내지 않는다. 실행 결과는 새 합성 프로젝트 viewer에서 열어 사용자에게 보여준다. UI는 기존 카드 컴포넌트를 재사용한다. 일반 poll/receive 직접 명령과 전체 request journal의 자동 사건 기록은 이번 연결 범위 밖이다.

## 검증 결과

2026-09-13: 구현 및 통합 검사76개 통과. 질문/advance/회차/council/outcome/CLI/reviewer 경로를 함께 확인했다. 같은 대기 상태는 중복 기록하지 않으며, 전송 결과 유실·start/수신 완료 receipt 유실·일부/진단 답변·권한 오류 비밀 미노출을 포함한다. 공개 JSON은 키 순서를 고정해 디스크 복구 전후 명령 fingerprint가 달라지지 않는다.

합성 요청1개가 회차2개(요청5기록 + 검토11기록)로 연결됨을 실제 viewer에서 확인했다. 1440px·390px 넘침 없음, 브라우저 오류/쓰기0건. Orca에 새 결과 화면을 열고 요청 카드를 펼쳤다. 검증 자료: `output/evaluations/atlas-request-episodes/`. 실제 연구와 Atlas 운영 자료는 변경하지 않았다.

독립 검토: 차단 문제 없음. 출력·종료 저장 후 receipt 유실과 수신 중 HEAD 변경을 별도 합성 검사로 확인했다. 첫 실패를 보존하며 재개 후 회차 하나를 완료하고 반복 조회 시 HEAD를 유지했다.
