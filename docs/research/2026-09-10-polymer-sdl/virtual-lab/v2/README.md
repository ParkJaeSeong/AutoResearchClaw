# 제조 실행과 측정 시도를 잇는 CSV v2

D3는 기존 네 파일을 유지하면서 **어느 제조 실행의 시편인지, 어느 측정 시도에 적용한 조건인지**를 명시한다. v1 파일은 그대로 보존하고 자동 변환하지 않는다. 이번 구현은 로컬 파일 검사이며 업로드·장비 제어·연구 그래프 등록 기능은 포함하지 않는다.

[빈 양식 폴더](templates/tasks.csv)와 [합성 예시](examples/tasks.csv)는 UTF-8 BOM CSV다. 예시는 M0·M1 제조 두 조건, 시편 두 개, 누락된 측정과 그 재시도를 보여 준다. 예시 값과 원자료는 파일 검사 전용 임의값이며 실험·물성 시뮬레이션·환산 결과가 아니다.

## 추가 열

| 파일 | 추가 열 | 뜻 |
| --- | --- | --- |
| tasks.csv | manufacturing_run_id, block_id, condition_level | 제조 실행, 대응 블록, 배정된 M0/M1. 측정 작업도 원래 제조 실행과 배정을 유지 |
| tasks.csv | sequence_index, started_at, ended_at, parent_task_id | 실행 순서, 시간대 포함 ISO 시작·종료 시각, 재작업 부모. 제조 작업의 재시작과 측정 재시도는 구분 |
| specimens.csv | manufacturing_run_id | 시편을 생산한 제조 실행 |
| conditions.csv | condition_id, scope_type, scope_id, method_id | 조건 행 ID, 적용 대상 종류(task/specimen/attempt), 대상 ID, 방법 버전 |
| results.csv | manufacturing_run_id, condition_id | 원래 제조 실행과 해당 결과에 적용한 조건 행 |
| results.csv | parent_attempt_id, raw_sha256 | 재시도 부모와 원자료 파일 SHA-256 |

조건 하나가 모든 환경·치수를 대신하지 않는다. 같은 scope_type/scope_id를 가진 조건 행을 여러 개 써서 적용 조건들을 묶는다. results.condition_id는 대표 조건 행을 가리킨다. 이 연결이 실제로 측정한 조건의 완전성이나 방법 적합성을 증명하지 않는다. 모든 필수 매개변수·단위의 방법별 사전은 [D2 측정 명세](../../experiment-design/measurement-method.md)와 착수 때 확정할 수치에 연결한다.

작업은 같은 plan_id·schema_version·data_origin을 사용한다. 수행한 제조·측정 작업에는 작업자·시각·제조 실행 연결이 필요하다. planned 행의 아직 없는 실제값은 비울 수 있다. 같은 제조 실행의 시편과 재시도를 독립 제조 반복으로 세지 않는다.

## 실패·재시도·정정

- 실패·누락 시에도 원래 작업·시편·시도 ID와 원인 notes를 남긴다. results의 missing/below_limit 값은 빈칸이며 0으로 보충하지 않는다.
- 측정 재시도는 새 attempt_id와 parent_attempt_id를 사용한다. 새 제조 실행은 새 작업·배치·run을 만들고 parent_task_id로 관계를 남긴다.
- 오기 정정은 새 measurement_id와 supersedes_measurement_id로 원래 지표 행을 연결한다. 같은 시도의 정정이며 재측정으로 세지 않는다. 원행은 삭제하지 않는다.
- 과거 전달 폴더를 덮어쓰지 않고 개정마다 별도 폴더로 보존한다. 파일 해시와 검사 보고서를 함께 저장한다. 이번 검증기는 파일을 수정하거나 변경 이력을 대신 생성하지 않는다.
- 다른 묶음의 과거 부모를 참조하려면 필요한 원행·연결 파일을 현재 검토 묶음에도 포함한다. 외부 경로를 따라 읽거나 누락 부모를 추정하지 않는다.

## 검사 실행

저장소의 기존 가상환경에서 실행한다.

```sh
.venv/bin/python -m researchclaw.codex.lab_csv docs/research/2026-09-10-polymer-sdl/virtual-lab/v2/examples
```

Python에서는 `from researchclaw.codex.lab_csv import validate_bundle` 후 폴더 Path를 전달한다. 종료 코드 0은 **파일 구조 검사 통과**, 2는 오류다. 오류에는 파일·행·내용이 포함된다. 템플릿은 내용이 없는 양식으로 구분한다.

검사는 버전/출처 혼합, 중복 ID, 작업·시편·배치·제조 실행·조건 적용 범위, 재시도·정정 연결, 수치·지표 단위, 수행 시각·작업자, 묶음 밖 경로·심볼릭 링크 탈출, 원자료 존재와 해시를 확인한다. 제출 묶음 밖 파일은 읽지 않는다.

`structural_valid`와 `scientific_usable`을 분리한다. 파일이 통과해도 자료 사용 판단은 수행되지 않았으므로 scientific_usable과 m1_ready는 false다. 장비·배합·방법·실제 조건·품질·상태 이력·자원·권한 검토가 별도로 필요하다. raw_file이 비었으면 원자료를 검증한 것으로 보지 않는다. 미지원 지표의 과학적 단위 검증이나 조건 완전성 검사도 수행하지 않는다.

## 완료 경계

D3에서 완료할 것은 v2 양식, 실제 검증기, 정상·누락·오연결·재시도·무결성 실패 검사다. 이 검증기는 M2 분석기나 M1 최종 인계 정책이 아니다. 계획·실제 변경 이력 자동 저장, UI 업로드, 외부 근거 인계 계약과 실제 착수 판정은 후속 구현·확인 항목으로 남긴다.
