# 1단계: 데이터 전처리 및 로컬 DB 구축

이 문서는 `school` 폴더 법령만 사용해 엣지(안드로이드)용 로컬 데이터셋을 만드는 방법입니다.

## 생성 산출물

- `build/school_law.db`: SQLite 본 DB
- `build/school_laws.jsonl`: 법령 메타데이터
- `build/school_articles.jsonl`: 조문 단위 레코드
- `build/school_chunks.jsonl`: 벡터 인덱싱용 chunk 데이터

## 실행

프로젝트 루트에서 실행:

```powershell
c:/Users/WJ/AppData/Roaming/uv/python/CPYTHON-3.12.13-WINDOWS-X86_64-NONE/python.exe scripts/build_school_edge_db.py
```

옵션 예시:

```powershell
c:/Users/WJ/AppData/Roaming/uv/python/CPYTHON-3.12.13-WINDOWS-X86_64-NONE/python.exe scripts/build_school_edge_db.py --chunk-size 800 --chunk-overlap 100
```

## SQLite 스키마

- `laws`: 법령 문서 단위(`법률.md`, `시행령.md` 등)
- `articles`: 조문 단위 분해 결과
- `chunks`: 임베딩용 분할 텍스트
- `law_fts`, `article_fts`, `chunks_fts`: FTS5 전문검색 인덱스

## 안드로이드 적용 가이드

### SQLite 직접 사용 (권장 시작점)

1. 빌드된 `build/school_law.db`를 앱 `assets`에 포함
2. 앱 최초 실행 시 내부 저장소로 복사
3. Room 또는 `SupportSQLiteDatabase`로 조회
4. 질의 예:

```sql
SELECT law_name, doc_type, article_no, snippet(article_fts, 5, '[', ']', '...', 20)
FROM article_fts
WHERE article_fts MATCH '고등교육 AND 등록금'
LIMIT 20;
```

### ObjectBox/모바일 벡터DB로 확장

1. `build/school_chunks.jsonl`를 읽어 임베딩 생성
2. `chunk_id`, `law_name`, `article_no`, `chunk_text`, `embedding` 저장
3. 질의 시:
- 사용자 질문 임베딩 생성
- 벡터 유사도 Top-K chunk 검색
- 검색된 chunk를 LLM 컨텍스트로 주입(RAG)

## 참고

- 중복 폴더(`법령명/법령명/파일.md`)가 있어도 스크립트가 동일 `(법령명, 문서종류)` 조합을 1개로 정규화합니다.
- 조문 헤더는 `##### 제N조 (...)` 패턴을 기준으로 파싱합니다.
