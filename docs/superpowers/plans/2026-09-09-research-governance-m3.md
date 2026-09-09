# M3 주장·심사·최종화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** M3 주장·심사·최종화를 독립 검토 가능한 작은 작업으로 구현한다.

**Architecture:** 공통 append-only 기록 위에 마일스톤별 adapter를 연결한다. 기존 엔진의 경로·승인을 유지하고 신규 프로젝트에서만 확장 정책을 적용한다.

**Tech Stack:** Python >=3.11, pytest, node:test, vanilla JS, 기존 wheel 패키징.

**Spec:** [설계 목차](../specs/2026-09-09-research-governance-design.md).

## 읽는 방법

이 파일은 묶음 목차다. 아래에서 현재 작업서 하나를 열고, 그 작업서에 지정된 공통 계약과 관련 설계만 읽는다. 구현 상태의 기준은 [전체 작업판](2026-09-09-research-governance.md)이다. 완료된 작업의 상세 보고서는 새 작업에 필요할 때만 읽는다.

## Task D01: 최종 주장과 근거 범위 연결

[작업서 열기](research-governance/tasks/D01.md)

## Task D02: 본문·도표·재현 안내 버전 등록

[작업서 열기](research-governance/tasks/D02.md)

## Task D03: 독립 심사와 쟁점별 수정·역방향 복귀

[작업서 열기](research-governance/tasks/D03.md)

## Task D04: 최종 출처·무결성·재현 감사

[작업서 열기](research-governance/tasks/D04.md)

## Task D05: 사용자 최종 결정과 로컬 보관

[작업서 열기](research-governance/tasks/D05.md)
