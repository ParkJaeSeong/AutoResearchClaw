# Task 04 report — 그래프·역할·스키마 순수 계약

작성일: 2026-09-08 (Asia/Seoul)

## 결과

- `workflow_version="m1-graph-v1"`, `schema_version=1`인 열 개 노드의 닫힌 그래프를 추가했다.
- 정상 전진선과 노드별 복귀 허용 목록을 고정했다. `review`는 `scope`부터 `hypothesize`까지만 복귀할 수 있으며 실행 노드는 M1 계약에 없다.
- `describe_graph()`, `allowed_return_targets(node_id)`, `describe_roles(node_id)`를 파일·프로젝트 상태에 의존하지 않는 순수 조회로 제공한다.
- 노드 ID와 표시 제목을 분리하고, 각 노드의 목적·입력·출력·담당 페르소나·필수 질문·권한을 조회할 수 있게 했다.
- 판단 노드는 `domain`, `methodology`, `critical_reproducibility`의 세 역할을 사용한다. 조정자는 비투표이고 다른 입장을 대신 쓰거나 차단 쟁점을 무시할 수 없다. 작성자는 자기 산출물을 승인하거나 독립 검토할 수 없다.
- 반환된 중첩 dict/list를 바꿔도 다음 조회에는 남지 않는다. 알 수 없는 노드는 `m1_node_unknown`으로 거부한다.

## A 확인 지점과 정책 결합

Task 01 정책 커밋 `680e722`와 총괄 계획의 임시 정책을 기준으로 다음 항목을 그래프 계약에 기록했다.

- 신규 프로젝트 전용이며 자동 legacy 이전은 없다.
- 세 판단 역할의 최종 입장이 모두 필요하고 차단 쟁점이 해소돼야 한다. 진행 권고는 `ready` 또는 `ready_with_limits`다.
- 기본 응답은 한 라운드, 추가 복귀는 2회, 등록 전 초안 수정은 2회다. 이 기본값은 특정 연구 승인이 아니다.
- 첫 UI는 읽기 전용이다.
- 선택 가설 요구는 `review`와 `handoff`에만 적용한다. `scope`부터 `synthesize`까지의 앞 단계 협의에는 적용하지 않는다.

Task 02의 읽기 전용 UI와 Task 03의 호스트 확인 기록은 선행 검토가 승인된 상태다. 이 작업은 그 화면이나 호스트 기록을 수정하지 않았고 CLI·저장·실제 연구 실행도 추가하지 않았다.

## 노드 계약

| 노드 | 역할 구성 | 대표 입력 → 출력 | 허용 복귀 |
| --- | --- | --- | --- |
| `scope` | 작성자 + 세 판단 역할 + 조정자 | 사용자 목적·제약 → 목표·제약 | `scope` |
| `questions` | 작성자 + 세 판단 역할 + 조정자 | 목표·제약 → 연구 질문 | `scope`, `questions` |
| `search` | 작성자 + 세 판단 역할 + 조정자 | 연구 질문 → 검색 계획 | `questions`, `search` |
| `collect` | 작성자 + 독립 재현성 확인 | 검색 계획 → 후보·검색 기록 | `search`, `collect` |
| `screen` | 작성자 + 세 판단 역할 + 조정자 | 후보·질문 → 선별 목록·사유 | `search`, `collect`, `screen` |
| `extract` | 작성자 + 독립 재현성 확인 | 승인된 선별 목록 → 추출·manifest | `screen`, `extract` |
| `synthesize` | 작성자 + 세 판단 역할 + 조정자 | 추출·manifest → 종합 JSON·문서 | `search`~`synthesize` |
| `hypothesize` | 작성자 | 종합 → 가설 JSON·문서 | `synthesize`, `hypothesize` |
| `review` | 세 판단 역할 + 비투표 조정자 | 가설·근거 결합 → 최종 입장·결정 | `scope`~`hypothesize` |
| `handoff` | 비투표 조정자 | 결정·가설·근거 결합 → manifest·보고서 | `review` |

## TDD와 검증 증거

첫 실행은 패키지 부재로 테스트 수집 중 2개의 `ModuleNotFoundError`가 발생했다. import 가능한 명시적 stub을 둔 뒤 같은 명령에서 `17 failed, 1 passed, 1 skipped`를 확인해 행위 검사가 구현 부재 때문에 실패함을 확인했다. 역할별 질문 전문화와 handoff 역할 보정도 각각 실패를 먼저 확인한 뒤 최소 구현으로 통과시켰다.

```sh
.venv/bin/python -m pytest \
  tests/codex_native/m1/test_contracts.py \
  tests/codex_native/m1/test_roles.py -q
```

```text
29 passed in 0.02s
```

```sh
.venv/bin/python -m pytest tests/codex_native/test_agent_roles.py -q
```

```text
123 passed in 0.06s
```

Python bytecode compile과 `git diff --check`도 종료 코드 0이었다. 격리 환경에는 `ruff`가 설치돼 있지 않아 ruff 검사는 실행하지 못했다.

## 사용자 확인과 제한

Python에서 `describe_graph()`를 조회하면 노드·전진선·복귀선·정책을, `describe_roles(node_id)`를 조회하면 해당 노드의 목적·질문·입출력·권한을 읽을 수 있다. 반환값은 조회 전용 계약이며 프로젝트 상태를 열거나 바꾸지 않는다.

저장소, 패킷, CLI, 실제 협의 등록, 전이 실행, M2 실행은 이 작업 범위가 아니다. Task 05와 06은 이 닫힌 카탈로그를 저장·패킷 경계에 연결하고, 이후 작업이 실제 협의와 상태 전이를 추가한다.
