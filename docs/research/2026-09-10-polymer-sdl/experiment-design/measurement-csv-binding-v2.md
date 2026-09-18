# 전극 배치 v2를 CSV에 연결하는 방법

[배치 v2](electrode-layout-v2.md)의 기록 사전이다. [기존 CSV v2](../virtual-lab/v2/README.md)의 열을 변경하지 않는다. 실제 시편·시도·측정 행은 아직 만들지 않았다. 조건 사전과 첨부 검토는 설계이며 자동 검사 기능 추가가 아니다.

## 기존 열을 사용하는 규칙

`conditions.csv`에서 `parameter`는 아래 이름, `planned_value`는 계획, `actual_value`는 실제 확인값이다. `condition_id`는 각 행의 고유 ID다. `method_id=PILOT-EC-LONGITUDINAL-4T-v2`로 연결한다. 미정 수치는 빈칸과 `value_status=unknown`으로 남긴다. 계획만 제공한 값은 `provided`와 계획 열을 쓰고 실제값은 비운다. `provided`를 실행 완료로 읽지 않는다.

| scope_type | scope_id | 기록할 정보 | parameter 예시 |
| --- | --- | --- | --- |
| task | 해당 측정 작업 ID | 방법·배치 버전, 공통 준비 절차와 계획 구동·판정 기준 | layout_version, contact_protocol_ref, drive_protocol_ref, acceptance_rule_ref |
| specimen | 그 작업의 시편 ID | 좌표계·게이트/채취 위치, 형상·치수 측정 위치와 이력 | coordinate_frame_ref, sampling_location_ref, width_cm, thickness_cm, geometry_measurement_ref |
| attempt | 실제 측정 시도 ID | 당시 실제 접점 범위, 접촉 회차, 구동·환경·제한 상태와 적용 조건 | contact_cycle_ref, contact_geometry_ref, voltage_plus_x_start_cm, voltage_plus_x_end_cm, voltage_minus_x_start_cm, voltage_minus_x_end_cm, lv_geom_cm, lv_eff_cm, lv_adoption_ref, temperature_c, humidity_pct, drive_log_ref, layout_manifest_file, layout_manifest_sha256 |

단위는 숫자와 분리해 cm·A·V·s·°C·%처럼 명시한다. 버전·경로·해시는 범주형 값으로 단위 없이 둔다. 원시 시간별 I·V·극성·기기 제한은 원자료 파일에 두며 조건행에 임의 대표값으로 줄이지 않는다. 폭·두께가 시도 사이 바뀌면 해당 시도의 조건 묶음에서 새 계측 기록을 지정한다.

specimen·attempt 조건행에도 해당 작업의 `task_id`가 필요하다. 같은 시편을 다른 작업에서 측정하면 그 작업의 task_id와 새 condition_id로 연결한다. 결과에 적용되는 조건행의 method_id는 결과와 일치시킨다. 접촉 조건의 contact_cycle_ref와 결과의 contact_cycle_id가 같은 회차를 가리키는지도 첨부에서 확인한다.

기존 검증기에서 attempt는 `results.csv`의 실제 시도 ID로 확인한다. 아직 실행하지 않은 계획은 task 범위에서 작성하며, 검사를 통과시키려고 가짜 results 행이나 미실행 attempt를 생성하지 않는다.

## 적용 조건 묶음과 첨부

결과의 `condition_id`는 같은 방법·시도에 적용되는 대표 조건 한 행이다. 한 행만으로 모든 형상·접촉·환경을 확인한 것으로 보지 않는다. 각 시도의 `layout_manifest_file`에 제출 묶음 내부 상대 경로를 선언하고 `layout_manifest_sha256`에 전체 파일 해시를 적는다. 첨부에는 다음을 포함한다.

- 방법·배치·계획 버전과 시편/제조 실행/작업/시도/접촉 회차 ID.
- 실제 적용한 task·specimen·attempt 조건행의 ID 목록. 값이 충돌하면 자동 우선순위로 덮어쓰지 않고 적용 사유와 제외 행을 명시한다.
- 전류 접점의 면·실제 피복, 전압 띠의 면·경계·폭·옆면 번짐을 담은 도면/사진 참조와 해시.
- Lv_geom의 계측값·불확실성과 Lv_eff 채택 여부, 모델·근거·판정자·적용 범위. 미정 Lv_eff를 Lv_geom으로 자동 채우지 않는다.
- 환산 사용/보류 이유, 원시 파일과 해시, 해당 시도에 적용한 판정 기준.

`layout_manifest`는 연구 전달 첨부 설계다. 현재 검증기는 conditions에 적힌 이 파일의 존재·해시·의미·필수항목을 자동 확인하지 않는다. 제출 묶음에 보존한 뒤 실행/방법 담당이 수동 검토한다. `results.raw_file/raw_sha256`의 실제 파일 무결성 검사와 구분한다. 첨부 자동 검사를 구현한 것으로 보고하지 않는다.

## 원자료와 실패를 잃지 않는 결과 기록

실제 시도를 했다면 I–V 원시 파일을 별도로 보존한다. 정량 사용이 보류돼도 파일과 해시·시도 ID·이유는 남긴다. 유효한 R이나 전도도를 계산하지 못한 값을 임의 수치로 채우지 않는다.

- 기존 CSV에서 `valid`와 `unverified`는 수치가 필수다. 빈 전도도를 `unverified`로 저장하면 구조 검사에 실패한다.
- 실제 수행한 시도에 대해 요구한 전도도 결과를 내지 못했다면 `quality_status=missing`, value 빈칸, notes에 ‘원시 I–V 있음, 기하 조건 미확인으로 환산하지 않음’처럼 사유를 적을 수 있다. 원자료 유실·미실행과 혼동하지 않는다. 검출한계 이하일 때만 `below_limit`를 사용한다.
- 측정 전에는 결과 행을 만들지 않는다. `missing` 행으로 아직 하지 않은 실험을 수행한 것처럼 표시하지 않는다.
- R·절편·적합 구간은 분석 첨부에 남긴다. 현 CSV 검증기가 모든 저항 지표·과학적 단위·선형성을 검증한다고 가정하지 않는다.
- 재측정은 새 attempt_id와 parent_attempt_id, 재접촉은 새 contact_cycle_id, 오기 정정은 새 measurement_id와 supersedes_measurement_id로 연결한다. 이전 파일·행을 보존한다.

현재 CSV 검증은 구조와 참조·원시 파일 해시 검사다. 이 기록 사전의 완전성·측정 적합성·M1 준비 완료는 별도 판단한다. 새 자동 업로드·실험 실행·CSV 데이터 생성은 이번 작업에 포함하지 않았다.
