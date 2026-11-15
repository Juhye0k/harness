# 구현 현황과 검증 기록

> 상태: 2026-11-15 기준 스냅샷 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../README.md) · [카테고리 목차](README.md)

## 현재 상태

업무 기능 개발 전 초기 하네스 단계다. 기능이 없는 것을 샘플 AI 서비스가 운영 중인 것으로 소개하지 않는다.

| 항목 | 상태 | 근거 |
|---|---|---|
| FastAPI 생존·준비 점검 | 구현 | [main.py](../../app/main.py) |
| DB 연결·migration 환경 | 구현 | [db.py](../../app/db.py), [migrations](../../migrations) |
| Redis·Celery 진단 | 구현 | [worker.py](../../app/worker.py) |
| Compose·CI·검사 | 구현 | [compose.yaml](../../compose.yaml), [CI](../../.github/workflows/ci.yml) |
| 업무 테이블·API | 미구현 | 모델·명세 초안만 존재 |
| 영상 업로드·FFmpeg | 미구현 | 후속 adapter 예정 |
| 실제 AI 분석·추천 | 미구현 | 실험 계획만 존재 |
| 웹 편집·다운로드 연결 | 미구현 | 별도 기존 프로토타입과 미연결 |
| 인증·SNS·운영 배포·자동 복구 | 미구현 | 후속 결정 필요 |
| 카테고리형 프로젝트 위키 | 작성 | [위키 홈](../README.md) |

## 확인된 검증 증거

- 기준 코드 커밋: [2989ee4](https://github.com/Juhye0k/short-form/commit/2989ee45f27b8c26804058b7ce17458cd0d42d48).
- [CI 실행 43672654952](https://github.com/Juhye0k/short-form/actions/runs/43672654952): checks와 integration 성공.
- 기본 검사 6개, 실제 인프라 통합 검사 2개, Alembic 설정·접속, Compose 설정, Docker 빌드 확인.
- 통합 실행은 GitHub Linux 환경의 결과다. 당시 로컬 Docker 엔진이 꺼져 있어 로컬 통합 성공 증거는 없다.

이는 해당 커밋의 증거이며 이후 커밋의 성공을 자동으로 보장하지 않는다. 최신 변경은 해당 커밋 CI를 별도로 확인한다.

## 하네스 개선 이력

첫 CI에서 `uv run pytest`가 app을 찾지 못했다. 기본 검사에서 쓰던 `python -m pytest`와 실행 경로가 달랐기 때문이다. pytest의 pythonpath를 명시해 두 진입점이 같은 루트를 사용하도록 수정했고 재실행으로 확인했다. 테스트를 제거하거나 실패를 무시하지 않았다.

CI 액션 런타임 경고를 정리하고 runner를 Ubuntu 24.04로 고정했다. 현재 잠금 파일은 패키지 버전을 기록하지만 Docker 기본 이미지 태그까지 불변 digest로 고정한 구성은 아니다.

## 다음 작업

[2단계](../02-delivery/phase-02-video-jobs.md)의 영상 입력·출력 계약과 업무 작업 모델을 먼저 확정한다. 이 문서화 작업 자체는 후속 기능 구현 지시가 아니다.
