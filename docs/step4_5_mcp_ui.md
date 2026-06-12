# 4-5단계: MCP 로직 앱 이식 + UI 오케스트레이션

이 문서는 안드로이드 앱 내부에서 Node.js MCP 서버 역할을 대체하는 구조를 설명합니다.

## 구현 위치

- 도구 검색 서비스: vendor/llama.cpp/examples/llama.android/app/src/main/java/com/example/llama/LawSearchService.kt
- 오케스트레이터: vendor/llama.cpp/examples/llama.android/app/src/main/java/com/example/llama/ToolOrchestrator.kt
- 채팅/UI 연결: vendor/llama.cpp/examples/llama.android/app/src/main/java/com/example/llama/MainActivity.kt
- 도구 상태 UI: vendor/llama.cpp/examples/llama.android/app/src/main/res/layout/activity_main.xml

## 4단계 반영 내용

1. 앱 시작 시 assets/db/school_law.db를 앱 내부 저장소로 복사
2. SQLite 읽기 전용 연결 생성
3. 도구 함수 2종 제공
- 조문 직접 조회: 법령명 + 제N조 패턴
- FTS 키워드 검색: chunks_fts 기반 근거 검색
4. 질의 처리 흐름
- 사용자 질문 수신
- 오케스트레이터가 도구 선택
- 로컬 DB 검색 결과를 LLM 프롬프트에 주입
- LLM이 근거 중심 답변 생성

## 5단계 반영 내용

1. 채팅창 유지 + 도구 상태 텍스트 추가
2. 법령 원문 보기
- 조문 직접 조회 성공 시 상단 패널에 원문 표시
3. 판례 요약 의도 대응
- 판례/요약 키워드 감지 시 PRECEDENT_SUMMARY 도구 경로 선택
- 현재 DB는 법령 중심이므로 관련 고지 문구 포함
4. 오케스트레이터 정책
- ARTICLE_LOOKUP > PRECEDENT_SUMMARY > KEYWORD_SEARCH 순으로 라우팅
- 조문 조회 실패 시 키워드 검색 자동 폴백
- 점수 기반 키워드 분류(판례/법령)로 라우팅 안정성 보강
5. 답변 검증성 강화
- 모델 응답 완료 후 `[근거]` 섹션 자동 부착
- 사용자 테스트 시 답변과 근거 법령의 일치 여부를 즉시 확인 가능

## 오프라인 보안 특성

- 검색과 생성이 모두 기기 내부에서 수행됨
- 네트워크 요청 없이 작동 가능
- 질의 기록과 법령 조회 이력이 외부 서버로 전송되지 않음
