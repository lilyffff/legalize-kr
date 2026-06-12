package com.example.llama

enum class ToolType {
    ARTICLE_LOOKUP,
    KEYWORD_SEARCH,
    PRECEDENT_SUMMARY
}

data class ToolSelection(
    val toolType: ToolType,
    val lawName: String? = null,
    val articleNo: String? = null,
    val reason: String
)

data class RetrievalContext(
    val selection: ToolSelection,
    val articleHit: ArticleHit? = null,
    val chunkHits: List<ChunkHit> = emptyList(),
    val notes: List<String> = emptyList()
)

class ToolOrchestrator {
    fun selectTool(userQuery: String): ToolSelection {
        val normalized = userQuery.replace("ㆍ", " ").replace("·", " ")
        val articlePattern = Regex("([가-힣ㆍ·\\s]{2,})\\s+제\\s*(\\d+)\\s*조(?:의\\s*(\\d+))?")
        val articleMatch = articlePattern.find(normalized)
        if (articleMatch != null) {
            val lawName = articleMatch.groupValues[1].trim()
            val major = articleMatch.groupValues[2].trim()
            val minor = articleMatch.groupValues.getOrNull(3)?.trim().orEmpty()
            val articleNo = if (minor.isBlank()) "제${major}조" else "제${major}조의${minor}"
            return ToolSelection(
                toolType = ToolType.ARTICLE_LOOKUP,
                lawName = lawName,
                articleNo = articleNo,
                reason = "조문 직접 조회 패턴 감지"
            )
        }

        val precedentKeywords = listOf("판례", "판결", "헌재", "요약", "사건번호", "대법원")
        val lawKeywords = listOf("법", "시행령", "시행규칙", "조문", "조항", "근거")

        val precedentScore = precedentKeywords.count { normalized.contains(it) }
        val lawScore = lawKeywords.count { normalized.contains(it) }

        if (precedentScore >= 1 && lawScore == 0) {
            return ToolSelection(
                toolType = ToolType.PRECEDENT_SUMMARY,
                reason = "판례/요약 키워드 우세"
            )
        }

        return ToolSelection(
            toolType = ToolType.KEYWORD_SEARCH,
            reason = if (lawScore > 0) "법령/조문 키워드 기반 검색" else "일반 키워드 검색"
        )
    }

    fun retrieve(userQuery: String, lawSearchService: LawSearchService): RetrievalContext {
        val selection = selectTool(userQuery)
        return when (selection.toolType) {
            ToolType.ARTICLE_LOOKUP -> {
                val hit = lawSearchService.findArticle(
                    lawNameQuery = selection.lawName ?: "",
                    articleNo = selection.articleNo ?: ""
                )
                val fallbackChunks = if (hit == null) {
                    lawSearchService.searchChunks(userQuery, limit = 4)
                } else {
                    emptyList()
                }
                val notes = if (hit == null) {
                    listOf("요청한 조문을 로컬 DB에서 찾지 못해 키워드 근거로 대체합니다.")
                } else {
                    emptyList()
                }
                RetrievalContext(
                    selection = selection,
                    articleHit = hit,
                    chunkHits = fallbackChunks,
                    notes = notes
                )
            }

            ToolType.PRECEDENT_SUMMARY -> {
                val chunks = lawSearchService.searchChunks(userQuery, limit = 5)
                RetrievalContext(
                    selection = selection,
                    chunkHits = chunks,
                    notes = listOf("현재 오프라인 DB에는 판례 원문이 없어 법령 중심으로 요약합니다.")
                )
            }

            ToolType.KEYWORD_SEARCH -> {
                val chunks = lawSearchService.searchChunks(userQuery, limit = 6)
                val notes = if (chunks.isEmpty()) {
                    listOf("질문과 일치하는 법령 근거를 찾지 못했습니다.")
                } else {
                    emptyList()
                }
                RetrievalContext(selection = selection, chunkHits = chunks, notes = notes)
            }
        }
    }

    fun buildAugmentedPrompt(userQuery: String, retrieval: RetrievalContext): String {
        val contextBuilder = StringBuilder()
        contextBuilder.appendLine("[사용자 질문]")
        contextBuilder.appendLine(userQuery)
        contextBuilder.appendLine()

        contextBuilder.appendLine("[검색 도구]")
        contextBuilder.appendLine("- 도구: ${retrieval.selection.toolType}")
        contextBuilder.appendLine("- 선택 사유: ${retrieval.selection.reason}")

        retrieval.notes.forEach { note ->
            contextBuilder.appendLine("- 참고: $note")
        }

        retrieval.articleHit?.let { hit ->
            contextBuilder.appendLine()
            contextBuilder.appendLine("[법령 원문 조회 결과]")
            contextBuilder.appendLine("- 법령: ${hit.lawName} (${hit.docType}) ${hit.articleNo}")
            hit.articleTitle?.takeIf { it.isNotBlank() }?.let { title ->
                contextBuilder.appendLine("- 조문명: $title")
            }
            contextBuilder.appendLine(hit.articleText)
        }

        if (retrieval.chunkHits.isNotEmpty()) {
            contextBuilder.appendLine()
            contextBuilder.appendLine("[법령 검색 근거]")
            retrieval.chunkHits.forEachIndexed { index, chunk ->
                contextBuilder.appendLine(
                    "${index + 1}) ${chunk.lawName} (${chunk.docType}) ${chunk.articleNo ?: "조문미상"}"
                )
                contextBuilder.appendLine(chunk.chunkText)
                contextBuilder.appendLine()
            }
        }

        contextBuilder.appendLine("[답변 지침]")
        contextBuilder.appendLine("1. 반드시 위 근거에 기반해 한국어로 답변한다.")
        contextBuilder.appendLine("2. 핵심 답변 후 근거 법령(법령명, 조문)을 목록으로 명시한다.")
        contextBuilder.appendLine("3. 근거가 부족하면 추측하지 말고 부족하다고 명시한다.")
        contextBuilder.appendLine("4. 판례 요약 요청이지만 판례 원문이 없으면 그 사실을 먼저 고지한다.")

        return contextBuilder.toString()
    }

    fun renderToolStatus(retrieval: RetrievalContext): String {
        val hitCount = (if (retrieval.articleHit != null) 1 else 0) + retrieval.chunkHits.size
        return "도구: ${retrieval.selection.toolType} | 근거 ${hitCount}건"
    }

    fun renderLawViewer(retrieval: RetrievalContext): String {
        val hit = retrieval.articleHit ?: return "법령 원문 보기: 조회 결과 없음"
        val title = hit.articleTitle?.takeIf { it.isNotBlank() }?.let { " ($it)" } ?: ""
        return buildString {
            appendLine("법령 원문 보기")
            appendLine("${hit.lawName} ${hit.articleNo}$title")
            appendLine()
            appendLine(hit.articleText)
        }
    }

    fun renderReferences(retrieval: RetrievalContext): String {
        val refs = mutableListOf<String>()
        retrieval.articleHit?.let { hit ->
            refs += "- ${hit.lawName} (${hit.docType}) ${hit.articleNo}"
        }
        retrieval.chunkHits.take(5).forEach { hit ->
            refs += "- ${hit.lawName} (${hit.docType}) ${hit.articleNo ?: "조문미상"}"
        }

        if (refs.isEmpty()) {
            return "\n\n[근거]\n- 조회된 근거 없음"
        }

        return buildString {
            appendLine()
            appendLine("[근거]")
            refs.distinct().forEach { appendLine(it) }
        }
    }
}
