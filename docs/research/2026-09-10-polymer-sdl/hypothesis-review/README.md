# 가설을 검증 가능한 질문으로 좁힌 대화

먼저 [결론과 다음 작업](decision.md)을 읽으면 된다. 아래는 그 결론을 만든 실제 검토자의 원응답이다. 조정자의 설명과 원래 발언은 구별해 보존했다.

세 역할이 같은 지정 입력으로 초기 의견을 작성했고, 전원 제출 후 의견을 공개했다. 이어 질문에 답한 뒤 모든 답변을 공개하여 최종 재판단했다. 미공개 파일 접근을 지침으로 제한했으며 운영체제 수준으로 격리하지는 않았다. 모델 다양성이나 통계적 독립성을 주장하지 않는다.

| 역할 | 1 · 독립 의견 | 2 · 상대 질문에 답변 | 3 · 답변을 읽고 재판단 |
| --- | --- | --- | --- |
| 소재 전문가 | [초기 의견](domain-initial.md) | [질문 응답](domain-response.md) | [최종 판단](domain-final.md) |
| 평가 방법 검토자 | [초기 의견](methodology-initial.md) | [질문 응답](methodology-response.md) | [최종 판단](methodology-final.md) |
| 실행 검토자 | [초기 의견](execution-initial.md) | [질문 응답](execution-response.md) | [최종 판단](execution-final.md) |

## 어떤 질문이 오갔는가

| 질문 | 질문한 역할 → 답한 역할 | 응답 위치 |
| --- | --- | --- |
| 제조 효과와 방향 차이를 중복 성공으로 세지 않으려면? | 소재 → 평가 방법 | [domain-initial-q1 답변](methodology-response.md) |
| 관측하지 않은 구조를 이유로 설명을 끝없이 유지하지 않으려면? | 소재 → 실행 | [domain-initial-q2 답변](execution-response.md) |
| 구조 차이가 없을 때 반증인지 측정 한계인지 어떻게 구별하나? | 평가 방법 → 소재 | [methodology-initial-q1 답변](domain-response.md) |
| 설명들이 공존하면 에이전트 선택법의 성공은 무엇인가? | 평가 방법 → 실행 | [methodology-initial-q2 답변](execution-response.md) |
| 첫 구조 지표를 무엇으로 좁힐 것인가? | 실행 → 소재 | [execution-initial-q1 답변](domain-response.md) |
| 접촉 변경의 기여를 어떤 차이와 반복 단위로 판단하나? | 실행 → 평가 방법 | [execution-initial-q2 답변](methodology-response.md) |

여섯 질문 모두 실제 응답이 있다. 그중 구조 측정의 판별 능력을 묻는 질문은 실제 감도·관측 대표성이 없어 `unresolved`로 남았다. 나머지 다섯 응답의 `answered`는 설계 질문에 답했다는 뜻이며 장비·원료·통계 기준의 미확인을 해결했다는 뜻은 아니다.

## 입력과 기록의 경계

- [공통 입력](input.md) → [최종 검토에 제공한 수정안](decision-before-final.md) → [조정자의 최종 정리](decision.md).
- 이전 원문 연결은 [6단계 근거 종합](../stage6-synthesis.md)과 [구조화 인용](../stage6-synthesis.json)에 있다. 이번에 새 문헌 검색은 하지 않았다.
- [실행 확인 기록](receipt.json)에 입력·응답의 해시와 공개 시점, 실제 도구의 에이전트 식별자, 확인 범위를 남긴다. 같은 폴더의 `*-prompt.txt`는 역할별 전달 지시다.
- 이번 9개 발언은 Codex 협업 도구로 수행한 실제 연구 검토다. 기존 연구 엔진의 council 제출 81개에 더해 등록한 것은 아니다. UI에는 조정자 요약을 제공하고, 이번 대화 원문은 이 문서에서 확인한다.
- 정식 단계 등록에는 기존 수집·추출의 필수 기록과 이번 입력 묶음 연결이 남았다. 승인·쟁점 해소·M1 완료를 대신 생성하지 않는다.
