# 오프라인 앱 테스트 플랜

## 사전 준비

1. `build/school_law.db`가 존재하는지 확인
2. GGUF Q4 모델 파일 준비
3. 자산 반영 실행:

```powershell
.\.venv\Scripts\python.exe scripts/stage_android_assets.py --model models/gguf/<모델폴더>/model-q4_k_m.gguf
```

4. Android Studio에서 `vendor/llama.cpp/examples/llama.android` 실행

## 테스트 시나리오

### 시나리오 A: 조문 직접 조회

입력:
- `교육기본법 제1조를 찾아줘`

기대 결과:
- 도구 상태: `ARTICLE_LOOKUP`
- 상단 법령 원문 패널에 해당 조문 표시
- 답변 하단 `[근거]`에 `교육기본법 (법률) 제1조` 포함

### 시나리오 B: 일반 검색

입력:
- `고등학교 무상교육 근거 알려줘`

기대 결과:
- 도구 상태: `KEYWORD_SEARCH`
- 답변에 관련 법령 요지 포함
- `[근거]`에 1개 이상 법령/조문 표시

### 시나리오 C: 판례 요약 의도

입력:
- `학교폭력 관련 판례 요약해줘`

기대 결과:
- 도구 상태: `PRECEDENT_SUMMARY`
- 판례 원문이 없다는 고지 포함
- 법령 중심 요약 + `[근거]` 출력

### 시나리오 D: 미탑재 조문 요청

입력:
- `헌법 제1조 보여줘`

기대 결과:
- 조문 직접 조회 실패 후 자동 폴백
- 도구 상태는 `ARTICLE_LOOKUP` 유지
- 노트: 조문 미조회 고지
- 키워드 근거 기반으로 대체 응답

## 합격 기준

1. 네트워크 차단 상태에서도 질의 응답 가능
2. 각 응답에 `[근거]` 섹션이 존재
3. 앱 크래시 없이 연속 질의 10회 이상 처리
