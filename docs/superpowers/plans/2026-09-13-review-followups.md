# 개발 검토 → 후속 작업 계획

기존 회차/검토 설계의 다음 작은 구현이다. 검토 저장과 후속 계획 저장을 같은 graph commit에 묶는다. 계획은 실제 작업 회차가 아니므로 실행 순번을 소비하지 않고 에이전트를 실행하지 않는다.

## 계약

신규 work_followups 컬렉션. 새 episode.review 명령이 검토당 정확히 하나를 생성한다. 이미 저장된 과거 검토는 소급 생성하지 않는다. 동일 command 재전송은 기존 receipt를 반환한다.

각 계획은 id, source_episode_id, source_conclusion_sha256, source_review_sha256, kind(followup|revision), title, purpose, depends_on[], return_to(null|id), return_reason(null|string), status(planned|blocked)를 가진다.

- continue: title=원 결론 next_action, purpose=next_reason, depends_on=[원 회차], return_to=null. 원 실행이 finished이면 planned, failed면 blocked. 과학적 수용으로 해석하지 않는다.
- revise: title='재검토: '+원 title, purpose=사용자 feedback, depends_on=[], return_to=원회차, return_reason=feedback, status=planned. 수정 대상의 결과가 차단 중이어도 재검토 계획 자체는 가능하다.
- ID는 project/id/결론hash/검토hash를 포함한 canonical SHA256 기반. 결론과 검토는 불변 원 기록과 대조한다.
- stage·담당·도구·실행 상태는 계획만으로 추정하지 않는다. 실제 회차로 시작할 때 조정자가 지정한다.
- view.work_followups는 해당 HEAD에 저장된 계획만 반환하고 source_episode/해시/파생필드를 확인한다. 미래 또는 현재 계획을 과거 HEAD에 섞지 않는다.

## 작업

1. work_followups.py helper + work_episodes.review_episode atomic patch + views projection. TDD: continue/revise/failedcontinue, original result unchanged, retry oneplan, oldHEAD/oldreview none, tamperedbinding rejection.
2. episodes.js에 원 회차별 접힌 '후속 작업 계획' 표시. 계획됨/선행 작업 확인 필요를 작업 실행과 구분. 원문feedback textContent보존. 기존 UI 스타일 재사용.
3. HTTP review부터 계획 생성까지 실제 합성viewer 검사. 사용자 예시root와 실제 연구 변경 금지, 새 검증root에서 시연. 기존 사용자 URL55383은 서버만 갱신해 pending검토 유지.

별도 실행자 연결·단계 선택·작업 배정·자동 실행은 다음 범위다. 저장된 계획이 실행되는 것처럼 상태를 만들지 않는다.

## 결과

구현 완료. backend48(신규계획17/HTTP13/회차18), Node50 통과. 별도 기존 view9개도 통과했다. 실제 합성 UI 제출2건에서 계획2개/회차2개/동일 순번, 새로고침 보존, 390px 넘침 없음을 확인했다. 독립 리뷰 차단 없음. 두 검증 계획은 합성 예시로 별도 화면을 열었으며 사용자 예시55383과 실제 연구8771 HEAD는 유지했다.

증거: output/evaluations/review-followups/. 실제 배정·실행은 수행하지 않았다.
