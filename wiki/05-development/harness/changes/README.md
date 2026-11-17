# 하네스 개선 기록

> 상태: 수동 기록 기준 · 기준일: 2026-11-15 · 유지관리: 프로젝트 개발자

[위키 홈](../../../README.md) · [하네스 목차](../README.md)

같은 실패를 다시 잡을 수 있도록 검사·지침·실행 환경을 개선한 경우 기록한다. 단순 파일명 수정마다 문서를 만들지는 않는다. 제품 실행 JSON이나 원본 대화를 이곳에 복사하지 않는다.

- [기록 양식](template.md)
- [RECO-EVAL-001: 선택 피드백과 종료 조건 기반 개선 루프](recommendation-improvement-loop.md)
- [TR-001: 전사 검수 자동 분류와 판정 저장](transcript-review-v1.md)
- [TR-001 후속: 실제 전사 응답 복구와 SNS 선점 경쟁 수정](transcription-response-recovery.md)
- [전사 평가·단어 정렬 통합과 실제 샘플 품질](transcript-quality-integration.md)
- [자막·SNS 변경 통합과 검사 환경 복구](integration-subtitles-sns.md)
- [VIDEO-001: 시간 초과 후 자식 프로세스가 남는 문제](video-001-process-timeout.md)
- [VIDEO-005: Groq 무료 모드와 통합 이미지 검사](video-005-groq-free.md)
- [VIDEO-005-SUBTITLES: 긴 전사 구간의 표시 자막 분리](video-005-subtitles.md)
- [SNS-006: 확인된 출력만 한 번 업로드하기](sns-006-upload.md)

새 기록은 작업 ID를 파일명에 포함하고 이 목차에 추가한다. 목적·실패 재현·원인·수정·관측 결과·남은 제한을 구분한다. 현황 문서에는 요약과 링크만 남긴다. 커밋·모델·비용 등 확인할 수 없는 값은 미확인으로 적는다.
