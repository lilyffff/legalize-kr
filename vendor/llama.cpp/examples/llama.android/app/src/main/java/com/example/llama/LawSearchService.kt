package com.example.llama

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.util.Locale

data class ArticleHit(
    val lawName: String,
    val docType: String,
    val articleNo: String,
    val articleTitle: String?,
    val articleText: String
)

data class ChunkHit(
    val lawName: String,
    val docType: String,
    val articleNo: String?,
    val chunkText: String
)

class LawSearchService(private val context: Context) {
    private var db: SQLiteDatabase? = null

    fun initialize(): Boolean {
        val dst = ensureDatabaseFile()
        if (!dst.exists()) {
            Log.w(TAG, "school_law.db not found in assets/db")
            return false
        }

        if (db?.isOpen == true) {
            return true
        }

        db = SQLiteDatabase.openDatabase(dst.path, null, SQLiteDatabase.OPEN_READONLY)
        return true
    }

    fun close() {
        db?.close()
        db = null
    }

    fun findArticle(lawNameQuery: String, articleNo: String): ArticleHit? {
        val database = db ?: return null

        val normalizedLawName = normalizeLawName(lawNameQuery)
        val normalizedArticleNo = normalizeArticleNo(articleNo)

        val sql = """
            SELECT law_name, doc_type, article_no, article_title, article_text
            FROM articles
            WHERE REPLACE(law_name, ' ', '') LIKE ?
              AND article_no = ?
            ORDER BY CASE doc_type WHEN '법률' THEN 0 ELSE 1 END, article_order ASC
            LIMIT 1
        """.trimIndent()

        database.rawQuery(sql, arrayOf("%$normalizedLawName%", normalizedArticleNo)).use { cursor ->
            if (!cursor.moveToFirst()) return null
            return ArticleHit(
                lawName = cursor.getString(0),
                docType = cursor.getString(1),
                articleNo = cursor.getString(2),
                articleTitle = cursor.getString(3),
                articleText = cursor.getString(4)
            )
        }
    }

    fun searchChunks(query: String, limit: Int = 6): List<ChunkHit> {
        val database = db ?: return emptyList()
        val ftsQuery = buildFtsQuery(query)
        if (ftsQuery.isBlank()) return emptyList()

        val sql = """
            SELECT law_name, doc_type, article_no, chunk_text
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
            LIMIT ?
        """.trimIndent()

        val out = mutableListOf<ChunkHit>()
        database.rawQuery(sql, arrayOf(ftsQuery, limit.toString())).use { cursor ->
            while (cursor.moveToNext()) {
                out += ChunkHit(
                    lawName = cursor.getString(0),
                    docType = cursor.getString(1),
                    articleNo = cursor.getString(2),
                    chunkText = cursor.getString(3)
                )
            }
        }

        return out
    }

    private fun ensureDatabaseFile(): File {
        val dbDir = File(context.filesDir, DB_DIRECTORY).also {
            if (!it.exists()) it.mkdirs()
        }
        val dst = File(dbDir, DB_FILENAME)
        if (dst.exists()) return dst

        try {
            context.assets.open("db/$DB_FILENAME").use { input ->
                FileOutputStream(dst).use { output ->
                    input.copyTo(output)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to copy DB from assets", e)
        }
        return dst
    }

    private fun normalizeLawName(value: String): String {
        return value.replace(" ", "")
            .replace("·", "ㆍ")
            .trim()
    }

    private fun normalizeArticleNo(value: String): String {
        val cleaned = value.replace(" ", "")
            .replace("제", "")
            .replace("조", "")

        return if (cleaned.contains("의")) {
            val parts = cleaned.split("의")
            "제${parts[0]}조의${parts.getOrElse(1) { "" }}"
        } else {
            "제${cleaned}조"
        }
    }

    private fun buildFtsQuery(query: String): String {
        val normalized = query.lowercase(Locale.KOREAN)
            .replace("·", " ")
            .replace("ㆍ", " ")
            .replace(Regex("[^가-힣a-z0-9\\s]"), " ")

        val tokens = normalized.split(Regex("\\s+"))
            .map { it.trim() }
            .filter { it.length >= 2 }
            .distinct()
            .take(6)

        return tokens.joinToString(" AND ")
    }

    companion object {
        private const val TAG = "LawSearchService"
        private const val DB_DIRECTORY = "db"
        private const val DB_FILENAME = "school_law.db"
    }
}
