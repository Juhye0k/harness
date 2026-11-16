# SNS-006 — 확인된 출력만 한 번 업로드하기

> 상태: 로컬 통합 검증 완료 / 실계정 업로드 미검증 · 기준일: 2026-11-16 · 유지관리: 프로젝트 개발자

[위키 홈](../../../README.md) · [개선 기록 목차](README.md)

## 작업 범위와 기준

사용자 요청은 지정한 분리 작업 트리에 6단계 SNS 업로드를 구현하는 것이다. 시작 커밋은 `228282dde8d5fb07a6df01c6313939fbeb6de373`, 브랜치는 `feat/sns-upload`다. 종료 커밋은 없으며 커밋·푸시·병합·Wiki 게시를 수행하지 않는다. 기존 개발 스택과 별도 프로젝트·이미지·볼륨으로 검증한다. 원본 작업 트리의 미커밋 전사 변경과 비밀값을 가져오지 않는다.

완료 기준은 [YouTube 실행 계약](../../youtube-upload.md)과 같다. GPT-6.1 Sol/high 요청을 받았으나 현재 세션의 모델·추론 강도를 확인하거나 변경하는 도구는 제공되지 않았다. 관측 가능한 도구는 파일 편집·PowerShell·uv·Docker·pytest·Playwright와 공식 문서 조회다. 모델 토큰 사용량·비용은 도구가 제공하지 않아 알 수 없음이다. 실제 외부 게시·유료 AI 호출은 수행하지 않는다.

## 요구사항과 실행 가능한 검사

| ID | 조건·영향 | 구현 | 회귀 검사 |
|---|---|---|---|
| SNS-006-R01 | OAuth state 재사용·다른 브라우저 연결 방지 | [SNS API](../../../../app/api/sns.py), [저장소](../../../../app/adapters/sns_repository.py) | `test_state_is_owner_bound_expiring_and_single_use`, `test_http_approval_duplicate_and_oauth_security` |
| SNS-006-R02 | 확인한 계정·출력·제목·공개 범위·아동용 여부 고정 | [서비스](../../../../app/services/sns.py) | `test_approval_is_bound_to_exact_fields`, `test_stale_approval_is_rejected`, `test_stale_or_unapproved_upload_never_calls_provider` |
| SNS-006-R03 | 비공개 기본값·토큰 유출 방지 | [YouTube HTTP](../../../../app/adapters/youtube_upload.py), [로그 필터](../../../../app/adapters/sns_logging.py) | `test_http_adapter_sets_private_and_never_redirects_or_retries`, `test_session_capability_cannot_redirect_credentials`, `test_oauth_and_capability_logs_are_redacted` |
| SNS-006-R04 | 중복 확인·메시지 재전달·발행 경쟁에서 한 번만 전송 | [저장소](../../../../app/adapters/sns_repository.py) | `test_concurrent_confirmation_reuses_one_upload`, `test_sns_claim_waits_for_confirmation_dispatch_commit`, `test_redelivery_does_not_publish_again` |
| SNS-006-R05 | 불명확한 실패를 재전송하지 않고 상태만 확인 | [서비스](../../../../app/services/sns.py) | `test_ambiguous_result_only_probes_existing_session`, `test_probe_dispatch_claim_is_single_use_and_cannot_resend`, `test_duplicate_new_title_is_not_a_new_upload_and_interruption_is_unknown` |
| SNS-006-R06 | 브라우저의 동의·중복 클릭·새로고침·조회 오류 | [화면](../../../../app/static/sns.js) | `test_browser_explicit_confirmation_reload_and_query_error` |

검사는 [기본 대역](../../../../tests/unit/test_sns.py), [실제 DB](../../../../tests/integration/test_sns_database.py), [실제 HTTP·워커·브라우저](../../../../tests/integration/test_sns_flow.py)에 둔다. 테스트 수는 실제 플랫폼 품질 점수가 아니다.

## 발견과 수정

- Windows 공용 pytest 임시 폴더의 접근 제한으로 테스트 준비가 실패했다. worktree 안에 임시 부모 폴더를 생성하고 `--basetemp`를 지정해 기본 SNS 검사 29개를 통과했다. 테스트 assertion은 유지했다.
- 격리 통합 환경은 SNS를 의도적으로 켜므로, 환경 변수를 그대로 읽은 기본 비활성화 검사가 실패했다. 해당 검사만 환경 변수를 제거한 상태에서 설정 기본값을 확인하도록 수정했다.
- 로컬 필수 검사에서는 FFmpeg·FFprobe가 준비되지 않아 기존 영상 검사들이 실패했다. 해당 검사를 제외하지 않고 FFmpeg가 포함된 격리 이미지에서 동일 검사 진입점을 실행한다.
- 첫 전체 통합 검사는 51개 통과·SNS 브라우저 1개 실패였다. 테스트 호스트에서 `crypto.randomUUID()`를 사용할 수 없어 미리보기 제출이 멈췄다. `crypto.getRandomValues()`로 UUID를 생성하고 실패 시 버튼을 복구하도록 수정했다. 이후 브라우저 검사는 CSP를 우회하려는 문자열 평가 대신 영상의 실제 메타데이터를 직접 검사한다. 제품의 CSP는 약화하지 않았다.
- 수정 이미지 재빌드 중 Docker의 BuildKit·containerd 저장소가 `input/output error`를 반환했고 Windows 검사에서도 `WinError 112`(디스크 공간 부족)가 발생했다. 전역 캐시 정리·Docker 재시작·기존 개발 스택 변경은 하지 않았다. 이 작업에서 생성한 임시 폴더·Python/Ruff 캐시 약 26MB만 정리했다.
- 기존 설치된 FFmpeg·FFprobe 실행 파일을 프로세스 PATH에서 읽기 전용으로 참조해 최종 기본 검사를 수행했다. 원본 코드·전사 변경·비밀값을 복사하거나 수정하지 않았다.

## 검증 결과와 남은 제한

후속 통합에서 Docker를 복구하고 전체 코드 기준 기본 235개·격리 통합 56개를 통과했다. 워커 로그 보호·만료 초안 재작성 회귀도 추가했다. [통합 검증 기록](integration-subtitles-sns.md)을 최신 근거로 삼으며 아래 수치·차단 사유는 개별 워크트리 당시 이력이다.

- `uv sync --locked` 통과. `cryptography` 외 기존 의존성 버전 변경 없음.
- 최종 `uv run python scripts/verify.py`: Ruff·서식·기본 검사 **149개**·Alembic SQL 생성 통과. 통합 53개 제외. 캐시 생성을 끄고 worktree 전용 pytest 임시 경로를 지정했다. 이전 네트워크 차단·읽기 전용 격리 실행도 당시 기본 147개를 통과했다.
- SNS 기본 검사만 최종 **31개** 통과했다. 실제 PostgreSQL의 당시 SNS 경쟁 검사 16개는 전체 통합 실행에서 통과했다. 뒤에 추가한 요청 번호 재사용 DB 검사 1개는 Docker 오류로 실행하지 못했다.
- 수정 후 브라우저 회귀 함수 `test_browser_explicit_confirmation_reload_and_query_error`를 별도 로컬 API와 설치된 Chrome에서 통과했다. 실제 SNS API·화면·합성 MP4·출력 고정 서비스에 메모리 저장소와 가짜 제공자를 주입했다. 미리보기·동의 전 전송 금지·중복 클릭·새로고침·조회 오류·390px 화면을 검사하고 데스크톱/모바일 이미지를 확인했다. 이 실행은 PostgreSQL·Redis·Celery 전체 재검증을 대신하지 않는다. 이미지·합성 영상·로컬 보조 실행 파일은 Git 제외 산출물이다.
- 최종 Ruff·서식·`git diff --check`와 변경 문서의 상대 링크를 확인한다. 기존 Starlette/httpx 사용 중단 예정 경고는 남아 있다.
- 격리 프로젝트는 `shortform-sns-84ae`, 전용 이미지는 `shortform-harness:sns-84ae-integration`이다. Docker 무응답으로 최종 전체 통합 53개 재실행과 테스트 리소스 정리 완료를 확인하지 못했다. 저장 공간 확보와 Docker 복구 후 이 프로젝트만 다시 검사·정리해야 한다. 엔진 재시작은 다른 개발 작업과 조율해야 한다.

실제 OAuth·게시·토큰 철회·플랫폼 업로드 제한·부하·운영 배포는 미실행이다. 자동 중단 감지·재시도·실패 작업의 재전송·다중 사용자 인증은 제공하지 않는다. 실제 SNS 계정·영상·제목·공개 범위를 승인받기 전에는 실계정 검증을 진행하지 않는다.
