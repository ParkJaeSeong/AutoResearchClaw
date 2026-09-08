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

## 전체 기준선 중단 결과

```sh
PYTHONPATH=/Users/jspark/orca/AutoResearchClaw \
  /Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/.venv/bin/python \
  -m pytest -q
```

unified execution session `63907`은 75%에서 SSL 읽기를 장시간 기다렸다. 사용자 지시에 따라 이 pytest 프로세스에만 Ctrl-C를 한 번 보내 요약을 받았다.

```text
=================================== FAILURES ===================================
FAILED tests/codex_native/test_execution_environment.py::test_generated_runner_revalidates_its_copied_venv_launcher_path
FAILED tests/codex_native/test_stage13_multi_agent_e2e.py::test_stage13_council_cli_e2e_refines_selects_and_preserves_baseline
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/opt/homebrew/Cellar/python@3.12/3.12.14/Frameworks/Python.framework/Versions/3.12/lib/python3.12/ssl.py:1103: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
2 failed, 3639 passed, 43 skipped, 1 deselected in 2917.13s (0:48:37)
```

종료 코드: 2. 전체 suite는 완료되지 않았고 전체 통과로 주장하지 않는다. 중단된 출력에는 경고의 최종 count와 대기 중이던 테스트 이름이 없으므로 각각 미확인으로 남긴다. SSL 위치만으로 특정 테스트를 추정하지 않는다.

첫 실패의 핵심 stderr:

```text
ModuleNotFoundError: No module named 'yaml'
```

테스트가 `venv.EnvBuilder(with_pip=False, symlinks=False, system_site_packages=True)`로 만든 중첩 venv는 Homebrew base Python 환경을 사용한다. base `/opt/homebrew/bin/python3.12`에서는 `yaml` import가 실패했고 작업공간 `.venv`에서는 성공했다.

둘째 실패의 핵심 예외:

```text
FileNotFoundError: [Errno 2] No such file or directory: 'researchclaw-codex'
```

현재 shell의 `PATH`에는 `researchclaw-codex`가 없지만 실행 파일은 작업공간 `.venv/bin/researchclaw-codex`에 설치돼 있었다.

환경 원인 확인을 위해 원본 경로를 첫 `PYTHONPATH` 항목으로 유지하고, 작업공간 `.venv`의 site-packages와 `bin`을 추가한 뒤 실패한 두 테스트만 다시 실행했다.

```text
researchclaw=/Users/jspark/orca/AutoResearchClaw/researchclaw/__init__.py
yaml=/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph/.venv/lib/python3.12/site-packages/yaml/__init__.py
..                                                                       [100%]
2 passed in 15.26s
```

두 실패는 기준선 호출 환경 원인으로 확인됐다. 제품 수정은 하지 않았으며 새 전체 suite 재실행도 하지 않았다. 전체 기본 회귀 상태는 여전히 미완료다.

## 범위 확인

Task 01 소유 문서 외 파일은 수정하지 않는다. 작업공간에 동시에 생긴 UI 및 `researchclaw/core/m1/`, `tests/codex_native/m1/` 변경은 다른 작업의 소유이며 이 작업에서 추가·수정·커밋하지 않는다.
