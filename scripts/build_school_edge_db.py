#!/usr/bin/env python3
"""Build a mobile-friendly SQLite DB from markdown laws in the school folder.

Outputs:
- build/school_law.db
- build/school_laws.jsonl
- build/school_articles.jsonl
- build/school_chunks.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ARTICLE_HEADING_RE = re.compile(r"^#{3,6}\s*(제\s*\d+조(?:의\d+)?)\s*(?:\((.*?)\))?\s*$")
FRONTMATTER_DELIM = "---"


@dataclass
class Article:
    article_no: str | None
    article_title: str | None
    article_order: int
    article_text: str


@dataclass
class LawDoc:
    law_name: str
    doc_type: str
    file_path: str
    title: str | None
    law_mst: str | None
    law_id: str | None
    law_kind: str | None
    promulgation_date: str | None
    enforcement_date: str | None
    status: str | None
    source_url: str | None
    ministries: list[str]
    body_text: str
    content_hash: str
    articles: list[Article]


def clean_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and ((value[0] == "'" and value[-1] == "'") or (value[0] == '"' and value[-1] == '"')):
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != FRONTMATTER_DELIM:
        return {}, text

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == FRONTMATTER_DELIM:
            end = i
            break
    if end is None:
        return {}, text

    meta: dict[str, object] = {}
    current_list_key: str | None = None

    for line in lines[1:end]:
        if not line.strip():
            continue

        if line.startswith("- ") and current_list_key is not None:
            current = meta.get(current_list_key)
            if isinstance(current, list):
                current.append(clean_value(line[2:]))
            continue

        if ":" not in line:
            current_list_key = None
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "":
            meta[key] = []
            current_list_key = key
        else:
            meta[key] = clean_value(value)
            current_list_key = None

    body = "\n".join(lines[end + 1 :]).strip() + "\n"
    return meta, body


def normalize_article_no(article_no: str) -> str:
    return article_no.replace(" ", "")


def split_articles(body_text: str) -> list[Article]:
    lines = body_text.splitlines()
    articles: list[Article] = []

    current_no: str | None = None
    current_title: str | None = None
    current_lines: list[str] = []
    order = 0

    for line in lines:
        match = ARTICLE_HEADING_RE.match(line.strip())
        if match:
            if current_no is not None:
                order += 1
                articles.append(
                    Article(
                        article_no=current_no,
                        article_title=current_title,
                        article_order=order,
                        article_text="\n".join(current_lines).strip(),
                    )
                )
            current_no = normalize_article_no(match.group(1))
            current_title = match.group(2).strip() if match.group(2) else None
            current_lines = []
            continue

        if current_no is not None:
            current_lines.append(line)

    if current_no is not None:
        order += 1
        articles.append(
            Article(
                article_no=current_no,
                article_title=current_title,
                article_order=order,
                article_text="\n".join(current_lines).strip(),
            )
        )

    if not articles:
        text = body_text.strip()
        if text:
            articles.append(Article(article_no=None, article_title=None, article_order=1, article_text=text))

    return articles


def iter_law_markdown_files(school_dir: Path) -> Iterable[Path]:
    candidates: dict[tuple[str, str], Path] = {}

    for md_path in school_dir.rglob("*.md"):
        rel = md_path.relative_to(school_dir)
        if len(rel.parts) < 2:
            continue

        law_name = rel.parts[0]
        doc_type = md_path.stem
        key = (law_name, doc_type)

        current = candidates.get(key)
        if current is None:
            candidates[key] = md_path
            continue

        current_depth = len(current.relative_to(school_dir).parts)
        new_depth = len(rel.parts)

        if new_depth < current_depth:
            candidates[key] = md_path
        elif new_depth == current_depth and str(md_path) < str(current):
            candidates[key] = md_path

    for _, path in sorted(candidates.items(), key=lambda item: (item[0][0], item[0][1])):
        yield path


def parse_law_doc(school_dir: Path, md_path: Path) -> LawDoc:
    rel = md_path.relative_to(school_dir)
    law_name = rel.parts[0]
    doc_type = md_path.stem

    text = md_path.read_text(encoding="utf-8")
    meta, body_text = parse_frontmatter(text)
    articles = split_articles(body_text)

    body_hash = hashlib.sha256(body_text.encode("utf-8")).hexdigest()

    ministries = meta.get("소관부처", [])
    if not isinstance(ministries, list):
        ministries = []

    return LawDoc(
        law_name=law_name,
        doc_type=doc_type,
        file_path=str(md_path).replace("\\", "/"),
        title=meta.get("제목") if isinstance(meta.get("제목"), str) else None,
        law_mst=meta.get("법령MST") if isinstance(meta.get("법령MST"), str) else None,
        law_id=meta.get("법령ID") if isinstance(meta.get("법령ID"), str) else None,
        law_kind=meta.get("법령구분") if isinstance(meta.get("법령구분"), str) else None,
        promulgation_date=meta.get("공포일자") if isinstance(meta.get("공포일자"), str) else None,
        enforcement_date=meta.get("시행일자") if isinstance(meta.get("시행일자"), str) else None,
        status=meta.get("상태") if isinstance(meta.get("상태"), str) else None,
        source_url=meta.get("출처") if isinstance(meta.get("출처"), str) else None,
        ministries=[str(m) for m in ministries],
        body_text=body_text,
        content_hash=body_hash,
        articles=articles,
    )


def make_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    value = text.strip()
    if not value:
        return []

    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    chunks: list[str] = []
    start = 0
    length = len(value)

    while start < length:
        end = min(length, start + chunk_size)
        chunk = value[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = end - overlap

    return chunks


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA foreign_keys=ON;

        DROP TABLE IF EXISTS chunks_fts;
        DROP TABLE IF EXISTS article_fts;
        DROP TABLE IF EXISTS law_fts;

        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS articles;
        DROP TABLE IF EXISTS laws;

        CREATE TABLE laws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            law_name TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            title TEXT,
            law_mst TEXT,
            law_id TEXT,
            law_kind TEXT,
            promulgation_date TEXT,
            enforcement_date TEXT,
            status TEXT,
            source_url TEXT,
            ministries_json TEXT NOT NULL,
            body_text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            UNIQUE (law_name, doc_type)
        );

        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            law_fk INTEGER NOT NULL,
            law_name TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            article_no TEXT,
            article_title TEXT,
            article_order INTEGER NOT NULL,
            article_text TEXT NOT NULL,
            FOREIGN KEY (law_fk) REFERENCES laws(id) ON DELETE CASCADE
        );

        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            law_fk INTEGER NOT NULL,
            article_fk INTEGER,
            law_name TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            article_no TEXT,
            chunk_order INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_chars INTEGER NOT NULL,
            FOREIGN KEY (law_fk) REFERENCES laws(id) ON DELETE CASCADE,
            FOREIGN KEY (article_fk) REFERENCES articles(id) ON DELETE SET NULL
        );

        CREATE INDEX idx_laws_name_type ON laws(law_name, doc_type);
        CREATE INDEX idx_articles_law_fk ON articles(law_fk, article_order);
        CREATE INDEX idx_chunks_law_fk ON chunks(law_fk, chunk_order);

        CREATE VIRTUAL TABLE law_fts USING fts5(
            law_id UNINDEXED,
            law_name,
            doc_type,
            title,
            body_text,
            tokenize='unicode61'
        );

        CREATE VIRTUAL TABLE article_fts USING fts5(
            article_id UNINDEXED,
            law_name,
            doc_type,
            article_no,
            article_title,
            article_text,
            tokenize='unicode61'
        );

        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            law_name,
            doc_type,
            article_no,
            chunk_text,
            tokenize='unicode61'
        );
        """
    )


def build_dataset(
    school_dir: Path,
    db_path: Path,
    laws_jsonl_path: Path,
    articles_jsonl_path: Path,
    chunks_jsonl_path: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> dict[str, int]:
    docs = [parse_law_doc(school_dir, p) for p in iter_law_markdown_files(school_dir)]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        init_db(conn)

        law_count = 0
        article_count = 0
        chunk_count = 0

        with (
            laws_jsonl_path.open("w", encoding="utf-8") as laws_out,
            articles_jsonl_path.open("w", encoding="utf-8") as articles_out,
            chunks_jsonl_path.open("w", encoding="utf-8") as chunks_out,
        ):
            for doc in docs:
                cur = conn.execute(
                    """
                    INSERT INTO laws (
                        law_name, doc_type, file_path, title, law_mst, law_id, law_kind,
                        promulgation_date, enforcement_date, status, source_url,
                        ministries_json, body_text, content_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc.law_name,
                        doc.doc_type,
                        doc.file_path,
                        doc.title,
                        doc.law_mst,
                        doc.law_id,
                        doc.law_kind,
                        doc.promulgation_date,
                        doc.enforcement_date,
                        doc.status,
                        doc.source_url,
                        json.dumps(doc.ministries, ensure_ascii=False),
                        doc.body_text,
                        doc.content_hash,
                    ),
                )
                law_id = int(cur.lastrowid)
                law_count += 1

                conn.execute(
                    "INSERT INTO law_fts (law_id, law_name, doc_type, title, body_text) VALUES (?, ?, ?, ?, ?)",
                    (law_id, doc.law_name, doc.doc_type, doc.title or "", doc.body_text),
                )

                laws_out.write(
                    json.dumps(
                        {
                            "law_id": law_id,
                            "law_name": doc.law_name,
                            "doc_type": doc.doc_type,
                            "file_path": doc.file_path,
                            "title": doc.title,
                            "law_mst": doc.law_mst,
                            "law_id_code": doc.law_id,
                            "law_kind": doc.law_kind,
                            "promulgation_date": doc.promulgation_date,
                            "enforcement_date": doc.enforcement_date,
                            "status": doc.status,
                            "source_url": doc.source_url,
                            "ministries": doc.ministries,
                            "content_hash": doc.content_hash,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

                for art in doc.articles:
                    a_cur = conn.execute(
                        """
                        INSERT INTO articles (
                            law_fk, law_name, doc_type, article_no, article_title, article_order, article_text
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            law_id,
                            doc.law_name,
                            doc.doc_type,
                            art.article_no,
                            art.article_title,
                            art.article_order,
                            art.article_text,
                        ),
                    )
                    article_id = int(a_cur.lastrowid)
                    article_count += 1

                    conn.execute(
                        """
                        INSERT INTO article_fts (
                            article_id, law_name, doc_type, article_no, article_title, article_text
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            article_id,
                            doc.law_name,
                            doc.doc_type,
                            art.article_no or "",
                            art.article_title or "",
                            art.article_text,
                        ),
                    )

                    articles_out.write(
                        json.dumps(
                            {
                                "article_id": article_id,
                                "law_id": law_id,
                                "law_name": doc.law_name,
                                "doc_type": doc.doc_type,
                                "article_no": art.article_no,
                                "article_title": art.article_title,
                                "article_order": art.article_order,
                                "article_text": art.article_text,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

                    base_text = "\n".join(
                        x
                        for x in [
                            f"{doc.law_name} {doc.doc_type}",
                            art.article_no or "",
                            art.article_title or "",
                            art.article_text,
                        ]
                        if x
                    )

                    chunks = make_chunks(base_text, chunk_size=chunk_size, overlap=chunk_overlap)
                    for chunk_order, chunk in enumerate(chunks, start=1):
                        c_cur = conn.execute(
                            """
                            INSERT INTO chunks (
                                law_fk, article_fk, law_name, doc_type, article_no, chunk_order, chunk_text, chunk_chars
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                law_id,
                                article_id,
                                doc.law_name,
                                doc.doc_type,
                                art.article_no,
                                chunk_order,
                                chunk,
                                len(chunk),
                            ),
                        )
                        chunk_id = int(c_cur.lastrowid)
                        chunk_count += 1

                        conn.execute(
                            """
                            INSERT INTO chunks_fts (chunk_id, law_name, doc_type, article_no, chunk_text)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                chunk_id,
                                doc.law_name,
                                doc.doc_type,
                                art.article_no or "",
                                chunk,
                            ),
                        )

                        chunks_out.write(
                            json.dumps(
                                {
                                    "chunk_id": chunk_id,
                                    "law_id": law_id,
                                    "article_id": article_id,
                                    "law_name": doc.law_name,
                                    "doc_type": doc.doc_type,
                                    "article_no": art.article_no,
                                    "chunk_order": chunk_order,
                                    "chunk_text": chunk,
                                    "chunk_chars": len(chunk),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )

        conn.commit()

    return {
        "laws": law_count,
        "articles": article_count,
        "chunks": chunk_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build SQLite/JSONL dataset from school laws")
    parser.add_argument(
        "--school-dir",
        default="school",
        help="Directory containing school law markdown folders (default: school)",
    )
    parser.add_argument(
        "--out-db",
        default="build/school_law.db",
        help="Output SQLite DB path (default: build/school_law.db)",
    )
    parser.add_argument(
        "--out-laws-jsonl",
        default="build/school_laws.jsonl",
        help="Output JSONL for laws metadata",
    )
    parser.add_argument(
        "--out-articles-jsonl",
        default="build/school_articles.jsonl",
        help="Output JSONL for article-level records",
    )
    parser.add_argument(
        "--out-chunks-jsonl",
        default="build/school_chunks.jsonl",
        help="Output JSONL for chunk-level records",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=900,
        help="Chunk size in characters for vector indexing (default: 900)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=120,
        help="Chunk overlap in characters (default: 120)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    school_dir = Path(args.school_dir).resolve()
    if not school_dir.exists() or not school_dir.is_dir():
        raise SystemExit(f"school directory not found: {school_dir}")

    out_db = Path(args.out_db).resolve()
    out_laws_jsonl = Path(args.out_laws_jsonl).resolve()
    out_articles_jsonl = Path(args.out_articles_jsonl).resolve()
    out_chunks_jsonl = Path(args.out_chunks_jsonl).resolve()

    out_laws_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_articles_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_chunks_jsonl.parent.mkdir(parents=True, exist_ok=True)

    stats = build_dataset(
        school_dir=school_dir,
        db_path=out_db,
        laws_jsonl_path=out_laws_jsonl,
        articles_jsonl_path=out_articles_jsonl,
        chunks_jsonl_path=out_chunks_jsonl,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    print(f"school_dir={school_dir}")
    print(f"sqlite={out_db}")
    print(f"laws_jsonl={out_laws_jsonl}")
    print(f"articles_jsonl={out_articles_jsonl}")
    print(f"chunks_jsonl={out_chunks_jsonl}")
    print(f"laws={stats['laws']}")
    print(f"articles={stats['articles']}")
    print(f"chunks={stats['chunks']}")


if __name__ == "__main__":
    main()
