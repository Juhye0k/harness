# 기술 의사결정

> 기술 의사결정에 속한 문서를 찾는 목차입니다. 아래 글의 설명을 읽고 필요한 주제로 이동하세요.

[위키 홈](../README.md)


채택한 기술과 대안, 절충 및 재검토 조건을 기록한다.

- [ADR-001 — Python과 FastAPI 선택](adr-001-python-runtime.md) — 영상 도구와 AI 연동을 작은 코드 기반에서 연결하기 위해 Python과 FastAPI를 선택했습니다
- [ADR-002 — PostgreSQL과 파일 저장 분리](adr-002-postgresql-storage.md) — 업무 상태와 큰 영상 파일은 저장·조회·삭제 방식이 다릅니다
- [ADR-003 — Redis 브로커와 Celery 워커](adr-003-redis-celery.md) — 작업 실행기를 직접 만드는 대신 Celery와 Redis로 영상 처리를 전달합니다
- [ADR-004 — 전사 기반 추천과 제공자 분리](adr-004-transcript-recommendations.md) — 첫 추천 방식은 영상 전체를 이해하는 모델 대신 한국어 음성 전사를 사용합니다
