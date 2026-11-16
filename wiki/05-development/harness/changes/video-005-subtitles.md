# VIDEO-005-SUBTITLES: 긴 전사 구간의 표시 자막 분리

후속 통합에서 Docker를 복구하고 전체 코드 기준 기본 235개·실제 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 56개를 통과했다. [통합 검증 기록](integration-subtitles-sns.md)을 최신 근거로 삼으며 아래 개별 워크트리의 Docker 차단은 당시 이력이다. 실제 음성 정렬 품질은 별도 평가 대상이다.

[위키 홈](../../../README.md) · [하네스 개선 기록](README.md)

목적은 원문 전사와 표시 자막을 분리하는 것이다. 완료 기준은 원문 문자 보존, 검증된 단어 시각 사용, 구버전 시각 추정 금지, 웹 확인·SRT 다운로드와 실패 회귀 검사다. 시작 코드는 VIDEO-005 Groq 미커밋 기준선이며 커밋·푸시·Wiki 게시는 하지 않는다.

사용자가 보고한 최대 21초·173자 구간의 긴 자막을 같은 길이·글자 수의 합성 사례로 재현했다. 실제 사용자 전사·영상은 복사하지 않았다. 제공자 전사 구간이 표시 가독성의 단위가 아니라는 점을 원인으로 보고 표시 계산을 분리했다.

수정은 word+segment 요청, 전사 캐시 v2, 문자·시각 일치 검증, 표시 버전 `ko-display-v1`, JSON/SRT와 원문 펼쳐보기다. 긴 단어·빠른 말·단어 시각 없음은 검토 필요로 드러낸다. [제품 초안과 제한](../../subtitle-segmentation.md)을 기준으로 한다.

일반 CI는 AI 대역만 사용한다. [단위 검사](../../../../tests/unit/test_subtitles.py), [Groq 대역](../../../../tests/unit/test_groq_provider.py), [통합·브라우저 검사](../../../../tests/integration/test_analysis_flow.py)로 회귀를 연결한다. 실제 품질·요금은 미평가이고 비용·토큰 사용량은 알 수 없음이다. 모델·환경·실행 증거와 실패 복구는 로컬 완료 보고서, 결과 요약은 [현황](../../../07-governance/status.md)에 기록한다.
