# M1 A 검증 기록 — Task 01 기준선

검증일: 2026-09-08 (Asia/Seoul)

- 설계: [M1 범위·진행 정책 계약 v1](../specs/2026-09-08-m1-contracts-design.md)
- 총괄 계획: [M1 Research Graph Implementation Plan](2026-09-08-m1-transition.md)
- 작업 브랜치: `feature/m1-research-graph`
- 기준 커밋: `ea3b62dced58d99edd13a76dabc50cdcd99e08bd`
- 격리 작업공간: `/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph`
- 기준선 소스: `/Users/jspark/orca/AutoResearchClaw`

## 정책 검토

신규 프로젝트 전용 적용, 세 판단 역할의 진행 조건, 기본 한 응답 라운드와 추가 복귀 2회, 읽기 전용 첫 UI를 v1 개발 기본값으로 기록했다. 이 값들은 총괄 계획 시작 허용에 포함된 되돌릴 수 있는 기본값이며 특정 연구의 승인으로 취급하지 않는다. 구체적인 진행 차단 사례와 사용자 조정 경계는 설계 문서에 있다.

## 실행 환경

요청된 명령을 실제로 조회한 결과다.

| 명령 | 경로 | 버전 |
| --- | --- | --- |
| `python3` | `/usr/bin/python3` | 3.9.6 — 프로젝트 요구사항 미충족 |
| `python3.11` | 없음 | 확인 불가 |
| `python3.12` | `/opt/homebrew/bin/python3.12` | 3.12.14 |
| `python3.13` | 없음 | 확인 불가 |
| `uv` | 없음 | 확인 불가 |
| `node` | `/opt/homebrew/bin/node` | 26.8.1 |

기존 문서에 쓰였던 `/opt/homebrew/bin/python3.11`은 이 환경에서 발견되지 않았다. 확인된 Python 3.12.14로 작업공간의 `.venv`를 사용했고 다음 명령으로 개발 의존성을 설치했다.

```sh
.venv/bin/python -m pip install -e '.[dev]'
```

설치는 성공했다. `researchclaw-codex 0.1.0`은 작업공간을 editable project로 가리키고, 검사 도구는 `pytest 9.1.1`, `pytest-asyncio 1.4.0`이다. 아래의 `python`은 모두 `/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/.venv/bin/python`을 뜻한다.

## 기준선 격리 확인

기준선은 원본 체크아웃을 작업 디렉터리와 `PYTHONPATH`로 명시해 실행했다.

```text
python=3.12.14 (main, Aug 12 2026, 13:57:54) [Clang 21.0.0 (clang-2100.1.1.101)]
executable=/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/.venv/bin/python
researchclaw.__file__=/Users/jspark/orca/AutoResearchClaw/researchclaw/__init__.py
```

따라서 작업공간에서 동시에 진행되는 M1 UI 변경은 이 기준선이 가져온 `researchclaw` 소스가 아니다.

## 변경 전 검사 결과

지정된 여섯 파일 기준선:

```sh
PYTHONPATH=/Users/jspark/orca/AutoResearchClaw python -m pytest \
  tests/codex_native/test_foundation_e2e.py \
  tests/codex_native/test_knowledge_extraction.py \
  tests/codex_native/test_synthesis.py \
  tests/codex_native/test_hypothesis_generation.py \
  tests/codex_native/test_approval.py \
  tests/codex_native/test_plugin_package.py -q
```

```text
166 passed in 19.22s
```

실패 0, 건너뜀 0, 경고 0이다.

전체 기본 회귀:

```sh
PYTHONPATH=/Users/jspark/orca/AutoResearchClaw python -m pytest -q
```

2026-09-08 21:50:52 KST 현재 실행 중이다. 실행 세션은 `63907`이며 마지막으로 확인된 진행률은 75%다. pytest 진행 출력에서 실패 마커 `F` 2개와 skip 마커가 관측됐지만, `-q`가 최종 요약까지 테스트 이름과 traceback을 내지 않았으므로 실패 이름·원인, 정확한 통과·건너뜀·경고 수는 아직 확인되지 않았다. 이 상태를 통과로 기록하지 않는다.

```text
...F... [약 15%]
...F.... [35%]
...
................................... [75%]
```

위 블록은 장시간 실행의 관측 지점을 요약한 것이며 완료 출력이 아니다. 전체 실행이 끝나면 같은 문서에 최종 pytest 요약과 환경 원인 조사 결과를 후속 기록한다. 현재 확인된 실패 마커는 M1 변경 실패로 분류하지 않았고, 제품 수정도 하지 않았다.

이 실행의 현재 수치를 과거의 `4,797 passed` 기록으로 대체하지 않는다. 기존 실패가 나오면 M1 기능 실패와 분리하고 환경 원인만 조사한다.

## Task 01 범위와 다음 작업

Task 01은 정책과 개발 기준선만 확정한다. 제품 코드, UI, 기존 프로젝트, 상태·승인·증거 레코드를 변경하지 않았다. Task 02는 이 읽기 전용 경계를 사용해 합성 예시 UI를 만들고, Task 03은 실제 호스트 배정의 관측 가능한 독립 실행 수준을 별도로 확인한다.
