# 전 과정 UI·평가·수용 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전 과정 UI·평가·수용를 독립 검토 가능한 작은 작업으로 구현한다.

**Architecture:** 공통 append-only 기록 위에 마일스톤별 adapter를 연결한다. 기존 엔진의 경로·승인을 유지하고 신규 프로젝트에서만 확장 정책을 적용한다.

**Tech Stack:** Python >=3.11, pytest, node:test, vanilla JS, 기존 wheel 패키징.

**Spec:** [설계 목차](../specs/2026-09-09-research-governance-design.md).

## 읽는 방법

이 파일은 묶음 목차다. 아래에서 현재 작업서 하나를 열고, 그 작업서에 지정된 공통 계약과 관련 설계만 읽는다. 구현 상태의 기준은 [전체 작업판](2026-09-09-research-governance.md)이다. 완료된 작업의 상세 보고서는 새 작업에 필요할 때만 읽는다.

## Task E01: 전 과정 읽기 전용 조회·CLI 서버

[작업서 열기](research-governance/tasks/E01.md)

## Task E02: 마일스톤 지도와 공통 쟁점 타임라인

[작업서 열기](research-governance/tasks/E02.md)

## Task E03: 결정·입장 변화·주장과 원천 탐색

[작업서 열기](research-governance/tasks/E03.md)

## Task E04: 신규 프로젝트 전체 연구 경로

[작업서 열기](research-governance/tasks/E04.md)

## Task E05: 동시성·중단 복구·기존 프로젝트 보존

[작업서 열기](research-governance/tasks/E05.md)

## Task E06: 실제 역할·브라우저 수용

[작업서 열기](research-governance/tasks/E06.md)

## Task E07: 단일·다중 에이전트 품질 평가

[작업서 열기](research-governance/tasks/E07.md)

## Task E08: 설치본·사용 안내·최종 작업판

[작업서 열기](research-governance/tasks/E08.md)
