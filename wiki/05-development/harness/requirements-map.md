# VIDEO-001 요구사항과 검사 연결

> 상태: 현재 구현·검사 대응표 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../../README.md) · [하네스 목차](README.md)

수치·입출력 정책의 기준은 [영상 추출 계약](../video-extraction.md)이다. 이 문서는 해당 계약을 어떤 코드와 검사로 확인하는지 연결한다. 테스트 개수는 품질 점수가 아니며 아래 미검증 부분까지 통과했다는 의미도 아니다.

| ID | 요구사항 | 구현 위치 | 자동 검사와 범위 |
|---|---|---|---|
| VIDEO-001-R01 | 단일 영상 링크·유효한 시작 시간 | [validate_url](../../../app/adapters/download.py), [validate_start](../../../app/domain/video.py) | [test_download.py](../../../tests/unit/test_download.py): `test_bad_url`, `test_youtube_canonical_url`; [test_video_rules.py](../../../tests/unit/test_video_rules.py): `test_invalid_range` |
| VIDEO-001-R02 | 원본을 넘는 구간 거부·정확한 경계 허용 | [validate_range](../../../app/domain/video.py) | [test_video_rules.py](../../../tests/unit/test_video_rules.py): `test_invalid_range`, `test_inclusive_boundaries` |
| VIDEO-001-R03 | 원본 보존·기존 파일 덮어쓰기 금지 | [extract](../../../app/adapters/media.py), [execute](../../../app/services/video.py) | [test_media_guards.py](../../../tests/unit/test_media_guards.py): `test_existing_output_untouched`; [test_extraction.py](../../../tests/media/test_extraction.py): `test_real_extract`의 원본 해시 비교 |
| VIDEO-001-R04 | 지정한 시작 위치부터 10초·허용 오차 준수 | [extract/probe](../../../app/adapters/media.py), [validate_output](../../../app/domain/video.py) | [test_extraction.py](../../../tests/media/test_extraction.py): `test_real_extract`의 색상 전환 시점·길이; [test_video_rules.py](../../../tests/unit/test_video_rules.py): `test_output_failure`, `test_container_duration_is_also_checked` |
| VIDEO-001-R05 | 영상 트랙 필수·음성 유지·무음 허용 | [probe/extract](../../../app/adapters/media.py) | [test_extraction.py](../../../tests/media/test_extraction.py): `test_real_extract`, `test_silent_video`, `test_audio_only`; [test_video_rules.py](../../../tests/unit/test_video_rules.py): `test_output_failure` |
| VIDEO-001-R06 | 입력 누락·손상·도구 실패를 구분 | [media](../../../app/adapters/media.py), [process](../../../app/adapters/process.py) | [test_media_guards.py](../../../tests/unit/test_media_guards.py): `test_missing_file`; [test_extraction.py](../../../tests/media/test_extraction.py): `test_corrupt_file`; [test_process.py](../../../tests/process/test_process.py): `test_process_failure`, `test_missing_tool` |
| VIDEO-001-R07 | 시간 초과 시 하위 프로세스까지 종료 | [run/terminate_tree](../../../app/adapters/process.py) | [test_process.py](../../../tests/process/test_process.py): `test_process_timeout`, `test_timeout_kills_descendants` |
| VIDEO-001-R08 | 다운로드 크기·작업 공간 제한 | [download_direct](../../../app/adapters/download.py), [download_youtube](../../../app/adapters/fetch_worker.py), [run](../../../app/adapters/process.py) | [test_download.py](../../../tests/unit/test_download.py): `test_size_limit`; [test_youtube.py](../../../tests/unit/test_youtube.py): `test_combined_download_size`; [test_process.py](../../../tests/process/test_process.py): `test_download_workspace_limit` |
| VIDEO-001-R09 | 사설 주소·우회 리디렉션 차단 | [public_address/open_connection](../../../app/adapters/download.py) | [test_download.py](../../../tests/unit/test_download.py): `test_private_address`, `test_connection_pins_validated_address`, `test_redirect_revalidates_destination` |
| VIDEO-001-R10 | 지원하지 않는 YouTube 입력·원본 길이 거부 | [download_youtube](../../../app/adapters/fetch_worker.py) | [test_youtube.py](../../../tests/unit/test_youtube.py): `test_youtube_rejections`, `test_youtube_configuration`; 실제 서버 대신 대역 사용 |
| VIDEO-001-R11 | 검증 후 출력·결과 기록, 실패 출력 정리 | [execute](../../../app/services/video.py) | [test_extraction.py](../../../tests/media/test_extraction.py): `test_use_case_publishes_validated_result`; [test_video_service.py](../../../tests/unit/test_video_service.py): `test_failure_cleans_output_but_preserves_source`, `test_failed_report_is_sanitized` |

## 자동 검사로 보장하지 않는 범위

- 공개 YouTube·MP4 서버의 접근 가능성은 수동 실행 증거다. [현황 기록](../../07-governance/status.md)의 과거 성공이 현재 모든 링크의 성공을 보장하지 않는다.
- CLI 인자 누락·파싱·종료 코드 자체, 저장 권한 오류, 종료 실패 오류 분기는 전용 자동 검사가 아직 없다. 함수 수준 검사를 CLI 전체 검사로 표현하지 않는다.
- 전체 디코딩은 성공 경로에서 실행하지만, 길이 검사를 통과하고 디코딩에서만 실패하는 출력의 전용 회귀 사례는 없다.
- 동시 생성 경로 충돌, 모든 컨테이너·코덱·가변 프레임률, 모든 DNS/리디렉션 조합을 검증한 것은 아니다.
- 원본 최대 길이는 YouTube 대역으로 검사한다. 직접 링크 원본의 20분 초과에 대한 전용 사례는 아직 없다.

요구사항 변경 시 이 식별자를 유지하고 계약·구현·검사를 함께 검토한다. 실패를 발견하면 [개선 기록](changes/README.md)에 재현 조건과 검사 함수를 연결한다. 이번 정리는 기존 검사를 이동한 작업이며 위 미검증 부분을 새 기능으로 구현하지 않는다.

## 비동기 확장

VIDEO-002는 [별도 요구사항 연결표](video-002-requirements.md)에서 API·상태 전이·중복·실패·다운로드를 관리한다.

VIDEO-003은 [웹 사용자 흐름과 검사 연결표](../web-video-extraction.md)에서 새로고침·통신 오류·브라우저 다운로드를 관리한다.

SNS-006은 [YouTube 확인·중복·미확정 처리 연결표](changes/sns-006-upload.md)에서 OAuth·출력 버전·최종 확인·전송과 상태 조회를 관리한다.
