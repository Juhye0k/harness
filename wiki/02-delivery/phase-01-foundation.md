# 1단계 — 프로젝트 구조와 최소 하네스

> 상태: 초기 설정 구현 완료 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../README.md) · [카테고리 목차](README.md)

## 목적

AI와 사람이 같은 환경·검사 명령을 사용하고 외부 구성 요소의 연결 문제를 빠르게 구분한다.

## 구현한 설계

- API와 워커는 같은 저장소의 코드를 사용하되 별도 프로세스로 실행한다.
- 업무 로직 폴더는 만들었지만 실제 기능은 넣지 않았다.
- DB 연결은 호출 시 생성하고 import 시 외부 통신을 수행하지 않는다.
- 일반 워커에 결과 backend를 두지 않는다. 진단 검사만 Redis에 임시 결과를 남긴다.
- 현재 API는 생존·의존성 점검뿐이다.

## 산출물과 근거

| 산출물 | 파일 |
|---|---|
| 작업 규칙 | [AGENTS.md](../../AGENTS.md) |
| 의존성 고정 | [pyproject.toml](../../pyproject.toml), [uv.lock](../../uv.lock) |
| 로컬 실행 | [compose.yaml](../../compose.yaml), [Dockerfile](../../Dockerfile) |
| 검사 진입점 | [verify.py](../../scripts/verify.py) |
| CI | [ci.yml](../../.github/workflows/ci.yml) |
| 구조 그림 | [아키텍처 SVG](../../docs/architecture.svg) |

## 검증 결과

기준 코드 `2989ee4`에서 기본 검사 6개, 통합 검사 2개, Docker 빌드를 확인했다. 통합 검사는 GitHub Linux 환경에서 수행했다. 로컬 Docker 엔진이 꺼져 있었던 실행 환경을 로컬 통합 성공으로 기록하지 않는다. 상세 근거는 [현황](../07-governance/status.md)을 참고한다.

## 완료 범위의 한계

API 준비 상태는 워커 생존을 보장하지 않는다. 업무 테이블, 영상 기능, 객체 저장소, 인증, 작업 복구, 자동 배포는 없다. CI 성공은 영상 품질이나 운영 준비 완료를 의미하지 않는다.

다음: [2단계 영상·작업 처리](phase-02-video-jobs.md).
