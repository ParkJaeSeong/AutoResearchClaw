# M2 실험·해석·방향 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** M2 실험·해석·방향를 독립 검토 가능한 작은 작업으로 구현한다.

**Architecture:** 공통 append-only 기록 위에 마일스톤별 adapter를 연결한다. 기존 엔진의 경로·승인을 유지하고 신규 프로젝트에서만 확장 정책을 적용한다.

**Tech Stack:** Python >=3.11, pytest, node:test, vanilla JS, 기존 wheel 패키징.

**Spec:** [설계 목차](../specs/2026-09-09-research-governance-design.md).

## 읽는 방법

이 파일은 묶음 목차다. 아래에서 현재 작업서 하나를 열고, 그 작업서에 지정된 공통 계약과 관련 설계만 읽는다. 구현 상태의 기준은 [전체 작업판](2026-09-09-research-governance.md)이다. 완료된 작업의 상세 보고서는 새 작업에 필요할 때만 읽는다.

## Task C01: M2 인계 수락과 설계 질문 배정

[작업서 열기](research-governance/tasks/C01.md)

## Task C02: 설계·판정 기준 고정과 독립 심사

[작업서 열기](research-governance/tasks/C02.md)

## Task C03: 기존 구현·실행 준비 계약 연결

[작업서 열기](research-governance/tasks/C03.md)

## Task C04: 실행 성공·실패와 결과 무결성 등록

[작업서 열기](research-governance/tasks/C04.md)

## Task C05: 독립 분석·대안 설명·쟁점 판정

[작업서 열기](research-governance/tasks/C05.md)

## Task C06: 연구 방향·복귀·M3 인계

[작업서 열기](research-governance/tasks/C06.md)
