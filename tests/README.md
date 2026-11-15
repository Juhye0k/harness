# 검사 코드 안내

제품 코드는 `app/`, 제품의 동작을 확인하는 코드는 이 폴더에 둡니다. 작업 규칙·리뷰·실패 기록은 [하네스 안내](../wiki/05-development/harness/README.md)에서 찾습니다.

| 위치 | 목적 | 필요한 자원 |
|---|---|---|
| unit/ | 규칙·환경 설정·HTTP/downloader 대역·실패 결과 검사 | Python, 임시 파일; DB·네트워크·FFmpeg 실행 없음 |
| process/ | 외부 프로세스 실패·시간 초과·자식 종료 | 실제 로컬 Python 하위 프로세스 |
| media/ | 영상 추출 구간·길이·트랙·원본 보존·결과 저장 | 실제 FFmpeg·FFprobe, 테스트가 생성하는 영상 |
| integration/ | DB·Redis 연결과 Celery 진단 작업 소비 | 전용 PostgreSQL·Redis·실제 진단 워커 |

저장소 루트에서 실행합니다.

```powershell
uv run python scripts/verify.py
uv run python -m pytest tests/unit -q
uv run python -m pytest tests/process -q
uv run python -m pytest tests/media -q
uv run python -m pytest --collect-only -q
```

공통 검사는 단위·프로세스·영상 검사를 포함하고 `integration` 마커가 있는 검사를 제외합니다. 폴더만 옮겨서는 마커가 자동으로 생기지 않습니다. 인프라 검사는 [전용 실행 절차](../wiki/05-development/harness/verification.md)에 따라 환경과 `RUN_INTEGRATION=1`을 준비해야 합니다.

단위 검사의 대역은 외부 호출을 대신하는 가짜 응답입니다. 실제 외부 링크 가용성은 일반 CI에서 검사하지 않습니다. 영상 검사에 필요한 도구가 없으면 건너뛰지 않고 실패합니다. 합성 영상 fixture는 `media/test_extraction.py`, HTTP 대역은 `unit/test_download.py`, YouTube 대역은 `unit/test_youtube.py` 가까이에 둡니다. 공통 사용이 생기기 전에는 도우미를 별도 프레임워크로 추출하지 않습니다.

검사를 추가할 때는 [요구사항 연결표](../wiki/05-development/harness/requirements-map.md)에 관련 요구사항·함수·한계를 함께 갱신합니다. 영상·임시 파일은 pytest 임시 경로에 생성하고 Git에 넣지 않습니다.
