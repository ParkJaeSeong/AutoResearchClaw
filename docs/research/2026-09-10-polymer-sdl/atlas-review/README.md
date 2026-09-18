# Atlas 근거를 이용한 가설 교차 검토

[이번 결론](decision.md) → [최소 가상 실험 설계](minimal-design.md) → [공통 근거](atlas-qa.md)

## 실제 원응답

| 역할 | 독립 초기 의견 | 질문·반박 | 최종 재판단 |
| --- | --- | --- | --- |
| 소재·분야 | [1차](domain-initial.md) | [2차](domain-response.md) | [3차](domain-final.md) |
| 방법론·반증 | [1차](method-initial.md) | [2차](method-response.md) | [3차](method-final.md) |
| 실험·실행 | [1차](execution-initial.md) | [2차](execution-response.md) | [3차](execution-final.md) |

원응답은 각 역할 에이전트가 직접 작성했다. [공통 범위](brief.md)와 [입력·해시](input-manifest.json)를 읽고 전원 초기 제출 이후 공개했다. 공유 파일의 접근을 기술적으로 차단한 것은 아니며 지시 수준 격리다. 모델 다양성이나 통계적 독립성을 주장하지 않는다.

2차에서 기존 CSV 계약을 추가 공개했다. 실행 역할은 직접 읽었고 소재·방법 역할은 미열람을 명시했다. 최종 역할들은 [조정자 결정안](decision-draft.md)과 전원의 응답을 읽었다. 조정자는 방법·실행의 최종 필수 보완을 [결정](decision.md)과 [설계](minimal-design.md)에 반영했다. 최종 결과 문서는 조정자가 작성했으며 별도 네 번째 에이전트 검토를 수행한 것으로 세지 않는다.

첫 검토는 실제 협업 에이전트 /root/atlas_domain, /root/atlas_method, /root/atlas_execution을 사용했다. 에이전트가 원문을 재독하거나 실험한 것은 아니다. [이전 결정](previous-decision.md)과 [이전 실행 명세](previous-execution-spec.md)를 보존했다.

정식 런타임 등록은 [별도 상태](runtime-boundary.json)이며, 이 대화를 native council 제출 수에 합산하지 않는다. 전체 M1 완료나 UI 반영을 뜻하지 않는다.

[검사 기록](verification.json)에서 입력 해시·원응답·링크·기존 연구 상태 보존을 확인할 수 있다. 동결된 이전 문서는 바이트 보존을 위해 상대 링크도 그대로 두었다. 그 안의 링크 기준 위치는 input-manifest.json의 origin이며, 현재 설계와 대화는 위 탐색 링크를 사용한다.
