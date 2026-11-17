# VIDEO-001 요구사항과 검사 연결

> 요구사항이 실제 검사와 연결돼 있는지 확인하는 문서입니다. 영상 길이·필수 트랙·원본 보존과 후속 기능별 회귀 검사의 위치를 안내합니다.

[위키 홈](../../README.md) · [하네스 목차](README.md)

전사 검수는 [검수 계약](../transcript-review.md)을 단위·통합 `test_transcript_review.py`에 연결한다. 임계값/결측/표본/원본 보존, 판정 버전/동시 저장 충돌, 음성 경로 제한/Range, 브라우저 저장 실패/재생/새로고침/보고서와 AI 호출 0건 증가를 검사한다. 실제 오류 탐지율과 시간 절감은 별도 사람 평가다.



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

## 자막 포함 세로 출력의 첫 기술 확인

`2026-11-17-subtitle-render-spike`의 범위는 [고정 합성 샘플 CLI](../portrait-subtitle-sample.md)다. 편집 UI·DB·비동기 출력 작업은 후속이다.

| 요구사항 | 구현 | 검사 |
|---|---|---|
| 원본→클립 시간 이동, 경계 잘림·겹침 거절, 입력 보존 | `domain.portrait.clip_captions` | `unit/test_portrait.py` |
| 고정 평문과 ASS 제어문자 분리 | `domain.portrait` | `unit/test_portrait.py`의 제어문자·줄수·글자수 검사 |
| 720×1280·길이·음성·디코딩·원본 보존 | `adapters.portrait.render_portrait` | `media/test_portrait_render.py` |
| 실제 자막 표시 시간·두 줄·구간 시작·여백 | 같은 adapter | 같은 media 검사의 프레임 픽셀·색상 비교 |
| 기존 파일 보존·시간 초과/실패 정리·폰트 부재 | adapter·sample service | 단위 검사와 media 결과 파일 검사 |

한국어 글리프 모양은 별도 미리보기 확인이며, 실제 음성 정렬·가독성 품질은 위 자동 검사로 판정하지 않는다.

## FLOW-001 — 시작부터 끝까지

| 요구사항 | 구현 | 검사 |
|---|---|---|
| 자동 초안·수동 편집의 표시 제약·원 구간 누락 차단 | `domain.caption_edit`, `api.editor` | `unit/test_caption_edit.py`, `integration/test_caption_versions.py` |
| 원본 전사 보존·불변 버전·확인 전 출력 차단 | `CaptionRevision`, `caption_repository` | 같은 integration과 `test_complete_flow.py` |
| 동일 버전 출력 재사용·원본 추출 캐시 독립 | `caption_repository.export`, 기존 jobs 서비스 | 동시 접수와 원본 추출 검사 |
| 실제 세로 렌더링·다운로드·클립 SRT·SNS 파일 일치 | `services.final_export`, editor 웹 | `integration/test_complete_flow.py` |
| 저장·새로고침 중복 방지·편집 시 이전 출력 숨김 | `static/editor.js` | 같은 브라우저 전체 흐름 검사 |
| 사용자·후보 경계·만료·자산 삭제 시 자막 제거 | 기존 접근 경계·FK cascade | `integration/test_caption_versions.py` |

실제 AI·SNS와의 차이와 실패 trace 확인은 [전체 흐름 안내](../complete-flow.md)를 따른다.

## 비동기·인증·다른 확장

UPLOAD-001은 [파일 업로드 계약](../local-video-upload.md)을 따른다. `test_uploads.py`는 크기·해시·시간 제한과 원본 미공개를, `test_local_upload.py`는 실제 DB·브라우저·워커에서 바이트 제한·중복·소유권·원본 검증·추출·전사 재사용·새로고침 무재전송을 검사한다.

AUTH-DATA-001은 [인증·자료 관리 계약](../user-auth-data.md)을 따른다. `test_auth_data.py`가 실제 PostgreSQL에서 A/B 사용자 경계·로그인 승인·콜백 재사용·CSRF·로그아웃·만료·삭제·탈퇴·Range 다운로드와 실제 브라우저를 검사한다. `test_google_login.py`는 공식 검증 함수의 오류 전파·nonce·최근 재인증을, `test_auth_safety.py`는 관리 루트 밖 삭제 거부와 토큰 해시 경계를 확인한다. 실제 Google 로그인은 일반 CI와 분리한다.

VIDEO-002는 [별도 요구사항 연결표](video-002-requirements.md)에서 API·상태 전이·중복·실패·다운로드를 관리한다.

VIDEO-003은 [웹 사용자 흐름과 검사 연결표](../web-video-extraction.md)에서 새로고침·통신 오류·브라우저 다운로드를 관리한다.

VIDEO-005의 [Groq 무료 연동](../groq-free-ai.md)은 `test_groq_provider.py`에서 무료 확인·모드 충돌·단일 호출·오류·타임스탬프·JSON 계약을, `test_analysis_pipeline.py`에서 제공자 변경 거부·캐시 분리를 검증한다. 통합 검사는 실제 MP3 전처리·추천 대역·선택 추출 흐름을 확인한다. 실제 무료 잔량·추천 품질은 검사 대상이 아니다.

전사 전용 확장은 `test_transcription_only_never_calls_recommendation`과 `test_recommendation_disabled_fails_before_transcription`으로 호출 경계를, `test_transcript_get_does_not_read_incomplete_job`으로 조회 조건을 검증한다.

`test_transcription_only_then_recommendation_reuses_transcript`는 전사 1회 이후 추천만 추가하는 DB 기록을, `test_transcription_browser_refresh_does_not_resubmit`은 시간별 표시와 재접수 없는 새로고침을 검증한다.

VIDEO-005-SUBTITLES는 [표시 자막 계약](../subtitle-segmentation.md)을 `test_subtitles.py`의 21초·173자 무손실·문자/시간 오류·구버전 fallback·불가능한 제약·읽기 전용 SRT 검사와 연결한다. Groq 대역은 word/segment 동시 요청·v1 거절을, `test_analysis_flow.py`는 실제 DB·Celery 보존과 브라우저 SRT·재접수 방지를 검증한다. 실제 음성 정렬은 일반 CI 밖이다.

SNS-006은 [YouTube 확인·중복·미확정 처리 연결표](changes/sns-006-upload.md)에서 OAuth·출력 버전·최종 확인·전송과 상태 조회를 관리한다.
# 빠른 숏츠 표시 정책 추가 연결

SHORTS-001의 정책·완성본 차단·검증 화면은 [정책 계약](../shorts-display-policy.md)을 따른다. `test_shorts_policy.py`가 21초/9줄·짧은 표시·어절 내부 토큰·서버 차단·호환 API·이전 코드 검사 기록을 확인하고, `test_shorts_verification.py`가 실제 DB·워커·브라우저로 새 정책과 웹 상태를 확인한다. 단어 시간이 없는 원문을 생략하거나 타이밍을 추정해 검사를 통과시키지 않는다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 상태: 현재 구현·검사 대응표 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

</details>
