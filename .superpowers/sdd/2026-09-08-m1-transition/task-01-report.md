# Task 01 report — 범위·정책·개발 기준선

작성일: 2026-09-08 (Asia/Seoul)

## 결과

- 정책 계약: `docs/superpowers/specs/2026-09-08-m1-contracts-design.md`
- 검증 기록: `docs/superpowers/plans/2026-09-08-m1-a-verification.md`
- 제품 코드 변경: 없음
- 기존 프로젝트 변경: 없음
- v1 기본값: 신규 프로젝트 전용, 세 역할 모두 진행 가능하고 차단 쟁점 해소, 응답 한 라운드와 추가 복귀 2회, 첫 UI 읽기 전용
- 승인 경계: 위 값은 개발 기본값이며 특정 연구의 문헌·가설·복귀 예산 승인이 아님

## 환경 원문

```text
python3: /usr/bin/python3 — Python 3.9.6
python3.11: NOT FOUND
python3.12: /opt/homebrew/bin/python3.12 — Python 3.12.14
python3.13: NOT FOUND
uv: NOT FOUND
node: /opt/homebrew/bin/node — v26.8.1
```

`.venv/bin/python -m pip install -e '.[dev]'`는 성공했다. 핵심 설치 결과는 다음과 같다.

```text
researchclaw-codex 0.1.0
Editable project location: /Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph
pytest 9.1.1
pytest-asyncio 1.4.0
```

## 원본 소스 결합 확인 원문

명령은 `/Users/jspark/orca/AutoResearchClaw`에서 명시적 `PYTHONPATH=/Users/jspark/orca/AutoResearchClaw`로 실행했다.

```text
python=3.12.14 (main, Aug 12 2026, 13:57:54) [Clang 21.0.0 (clang-2100.1.1.101)]
executable=/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/.venv/bin/python
researchclaw.__file__=/Users/jspark/orca/AutoResearchClaw/researchclaw/__init__.py
```

원본 체크아웃은 기준선 실행 중 `main...origin/main`이며 변경 파일이 없는 상태로 확인했다.

## 지정 기준선 출력

```text
........................................................................ [ 43%]
........................................................................ [ 86%]
......................                                                   [100%]
166 passed in 19.22s
```

종료 코드: 0. 실패 0, 건너뜀 0, 경고 0.

## 전체 기준선 진행 상태

```sh
PYTHONPATH=/Users/jspark/orca/AutoResearchClaw \
  /Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/.venv/bin/python \
  -m pytest -q
```

2026-09-08 21:50:52 KST 현재 unified execution session `63907`에서 계속 실행 중이다. 마지막 확인은 75%, 실패 마커 2개다. skip 마커도 보였으나 완료 전이므로 정확한 수를 제시하지 않는다. `-q` 출력 특성상 실패 테스트 이름과 traceback은 최종 요약 전에는 확인되지 않았다.

관측된 진행 출력의 마지막 구간:

```text
...F.... [ 35%]
........................................................................ [ 37%]
...........................................s............................ [ 38%]
...
........................................................................ [ 72%]
...
....................................... [ 75%]
```

이 발췌는 전체 실행의 완료 출력이 아니다. 현재 상태를 통과로 주장하지 않으며 통과·실패·건너뜀·경고의 최종 count도 아직 없다. 실행 완료 뒤 pytest 최종 출력과 실패 이름을 후속 반영하고, 실패 원인은 환경 범위에서만 조사한다. Task 01은 legacy 제품 수정을 하지 않는다.

## 범위 확인

Task 01 소유 문서 외 파일은 수정하지 않는다. 작업공간에 동시에 생긴 UI 및 `researchclaw/core/m1/`, `tests/codex_native/m1/` 변경은 다른 작업의 소유이며 이 작업에서 추가·수정·커밋하지 않는다.
