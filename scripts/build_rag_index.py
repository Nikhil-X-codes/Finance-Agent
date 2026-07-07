"""Build FAISS index from scraped regulatory documents.

Chunks text files, embeds with sentence-transformers, and builds
a FAISS index with SQLite metadata.

Usage:
    python scripts/build_rag_index.py --refresh        # full pipeline
    python scripts/build_rag_index.py --build-only     # index from existing .txt
    python scripts/build_rag_index.py --build-only --docs-dir docs/ --output-dir ai-service/data/vector_store/
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "ai-service" / "data" / "vector_store"
DEFAULT_MODEL_CACHE = PROJECT_ROOT / "ai-service" / "data" / "model_cache"
EMBEDDING_MODEL = "BAAI/bge-small-en"
EMBEDDING_DIM = 384

# Chunking parameters
CHUNK_SIZE_CHARS = 2000       # ~512 tokens at ~4 chars/token
CHUNK_OVERLAP_CHARS = 256     # ~64 tokens overlap

# Sentence boundary pattern
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    parts = _SENTENCE_END.split(text)
    return [s.strip() for s in parts if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[dict[str, Any]]:
    """Split text into overlapping chunks at sentence boundaries.

    Returns list of {text, char_start, char_end, chunk_index}.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[dict[str, Any]] = []
    current_chars: list[str] = []
    current_len = 0
    chunk_start = 0
    char_offset = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        if current_len + sentence_len > chunk_size and current_chars:
            # Emit current chunk
            chunk_text_str = " ".join(current_chars)
            chunks.append({
                "text": chunk_text_str,
                "char_start": chunk_start,
                "char_end": chunk_start + len(chunk_text_str),
                "chunk_index": len(chunks),
            })

            # Overlap: keep last few sentences that fit within overlap
            overlap_chars: list[str] = []
            overlap_len = 0
            for s in reversed(current_chars):
                if overlap_len + len(s) > overlap:
                    break
                overlap_chars.insert(0, s)
                overlap_len += len(s)

            current_chars = overlap_chars
            current_len = overlap_len
            chunk_start = char_offset - overlap_len

        current_chars.append(sentence)
        current_len += sentence_len
        char_offset += sentence_len + 1  # +1 for space

    # Final chunk
    if current_chars:
        chunk_text_str = " ".join(current_chars)
        chunks.append({
            "text": chunk_text_str,
            "char_start": chunk_start,
            "char_end": chunk_start + len(chunk_text_str),
            "chunk_index": len(chunks),
        })

    return chunks


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_text_files(docs_dir: Path) -> list[dict[str, str]]:
    """Find all .txt files in docs/sebi, docs/amfi, docs/rbi."""
    files: list[dict[str, str]] = []
    for source in ["sebi", "amfi", "rbi"]:
        source_dir = docs_dir / source
        if not source_dir.exists():
            continue
        for txt_file in sorted(source_dir.glob("*.txt")):
            files.append({
                "path": str(txt_file),
                "source": source,
                "filename": txt_file.name,
            })
    return files


def _extract_title(text: str, filename: str) -> str:
    """Extract title from file content header or fallback to filename."""
    for line in text.splitlines()[:5]:
        if line.startswith("# ") and not line.startswith("# Source:") and not line.startswith("# Date:"):
            return line.lstrip("# ").strip()
    return filename.replace(".txt", "").replace("-", " ").title()


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def load_embedding_model(model_name: str, cache_folder: Path):
    """Load sentence-transformers model."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed.")
        print("Run: pip install sentence-transformers")
        sys.exit(1)

    cache_folder.mkdir(parents=True, exist_ok=True)
    print(f"Loading embedding model: {model_name}")
    print(f"  Cache folder: {cache_folder}")
    model = SentenceTransformer(model_name, cache_folder=str(cache_folder))
    print(f"  Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")
    return model


def embed_texts(model, texts: list[str], batch_size: int = 64) -> np.ndarray:
    """Embed texts and L2-normalize for cosine similarity via inner product."""
    print(f"  Embedding {len(texts)} chunks (batch_size={batch_size})...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,  # L2 normalize for cosine sim via IP
    )
    return np.array(embeddings, dtype=np.float32)


# ---------------------------------------------------------------------------
# FAISS index
# ---------------------------------------------------------------------------

def build_faiss_index(embeddings: np.ndarray, output_path: Path) -> None:
    """Build and save a FAISS IndexFlatIP."""
    try:
        import faiss
    except ImportError:
        print("ERROR: faiss-cpu not installed.")
        print("Run: pip install faiss-cpu")
        sys.exit(1)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # Inner product for normalized vectors = cosine
    index.add(embeddings)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(output_path))
    print(f"  FAISS index saved: {output_path}")
    print(f"  Dimensions: {dim}, Vectors: {index.ntotal}")


# ---------------------------------------------------------------------------
# SQLite metadata
# ---------------------------------------------------------------------------

def build_metadata_db(
    chunks: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Build SQLite metadata DB for chunk lookup."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing DB to rebuild
    try:
        if output_path.exists():
            output_path.unlink()
    except Exception:
        pass

    conn = sqlite3.connect(str(output_path))
    conn.execute("DROP TABLE IF EXISTS chunk_metadata")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunk_metadata (
            chunk_id    INTEGER PRIMARY KEY,
            source      TEXT NOT NULL,
            filename    TEXT NOT NULL,
            title       TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text        TEXT NOT NULL,
            char_start  INTEGER NOT NULL,
            char_end    INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX idx_source ON chunk_metadata(source)")

    conn.executemany(
        """INSERT INTO chunk_metadata
           (chunk_id, source, filename, title, chunk_index, text, char_start, char_end)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                i,
                c["source"],
                c["filename"],
                c["title"],
                c["chunk_index"],
                c["text"],
                c["char_start"],
                c["char_end"],
            )
            for i, c in enumerate(chunks)
        ],
    )
    conn.commit()
    conn.close()
    print(f"  Metadata DB saved: {output_path} ({len(chunks)} rows)")


def build_metadata_json(
    chunks: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Build JSON metadata file for chunk lookup in RAGService."""
    metadata_dict = {}
    for i, c in enumerate(chunks):
        metadata_dict[str(i)] = {
            "source": c["source"],
            "title": c["title"],
            "doc_title": c["title"],
            "text": c["text"],
            "chunk_index": c["chunk_index"],
            "filename": c["filename"],
        }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
    print(f"  Metadata JSON saved: {output_path} ({len(chunks)} entries)")


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_discover() -> None:
    """Run discover_docs.py as a subprocess."""
    script = PROJECT_ROOT / "scripts" / "discover_docs.py"
    print("\n" + "=" * 60)
    print("STEP 1: Discovering documents...")
    print("=" * 60)
    subprocess.run(
        [sys.executable, str(script), "--all"],
        check=True,
        cwd=str(PROJECT_ROOT),
    )


def run_scrape() -> None:
    """Run scrape_content.py as a subprocess."""
    script = PROJECT_ROOT / "scripts" / "scrape_content.py"
    print("\n" + "=" * 60)
    print("STEP 2: Scraping content...")
    print("=" * 60)
    subprocess.run(
        [sys.executable, str(script)],
        check=True,
        cwd=str(PROJECT_ROOT),
    )


def run_build(docs_dir: Path, output_dir: Path, model_cache: Path) -> None:
    """Chunk, embed, and build FAISS index."""
    print("\n" + "=" * 60)
    print("STEP 3: Building FAISS index...")
    print("=" * 60)

    # 1. Discover text files
    files = discover_text_files(docs_dir)
    if not files:
        print(f"ERROR: No .txt files found in {docs_dir}/[sebi|amfi|rbi]/")
        print("Run with --refresh to discover and scrape documents first.")
        return

    print(f"\nFound {len(files)} text files:")
    for source in ["sebi", "amfi", "rbi"]:
        count = sum(1 for f in files if f["source"] == source)
        if count:
            print(f"  {source.upper()}: {count}")

    # 2. Chunk all files
    print("\nChunking documents...")
    all_chunks: list[dict[str, Any]] = []

    for file_info in files:
        path = Path(file_info["path"])
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                raw = path.read_bytes()
                try:
                    import chardet
                    detected = chardet.detect(raw)
                    encoding = detected.get("encoding", "utf-8") or "utf-8"
                except ImportError:
                    encoding = "utf-8"
                text = raw.decode(encoding, errors="ignore")
            except Exception as e:
                print(f"ERROR reading {path}: {e}")
                continue
        title = _extract_title(text, file_info["filename"])

        chunks = chunk_text(text)
        for chunk in chunks:
            chunk["source"] = file_info["source"]
            chunk["filename"] = file_info["filename"]
            chunk["title"] = title
            all_chunks.append(chunk)

    print(f"Total chunks: {len(all_chunks)}")

    if not all_chunks:
        print("ERROR: No chunks generated. Check that text files have content.")
        return

    # 3. Embed
    print("\nEmbedding chunks...")
    model = load_embedding_model(EMBEDDING_MODEL, model_cache)
    texts = [c["text"] for c in all_chunks]
    embeddings = embed_texts(model, texts)

    # 4. Build FAISS index
    print("\nBuilding FAISS index...")
    faiss_path = output_dir / "index.faiss"
    build_faiss_index(embeddings, faiss_path)

    # 5. Build metadata DB
    print("\nBuilding metadata DB...")
    meta_path = output_dir / "meta.db"
    build_metadata_db(all_chunks, meta_path)

    # 5b. Build metadata JSON
    print("\nBuilding metadata JSON...")
    meta_json_path = output_dir / "meta.json"
    build_metadata_json(all_chunks, meta_json_path)

    # 6. Summary
    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print(f"  Files processed:  {len(files)}")
    print(f"  Chunks created:   {len(all_chunks)}")
    print(f"  Embedding dim:    {embeddings.shape[1]}")
    print(f"  Total vectors:    {embeddings.shape[0]}")
    print(f"  FAISS index:      {faiss_path}")
    print(f"  Metadata DB:      {meta_path}")
    print(f"  Metadata JSON:    {meta_json_path}")
    print(f"  FAISS index size: {faiss_path.stat().st_size / 1024:.1f} KB")
    print(f"  Metadata DB size: {meta_path.stat().st_size / 1024:.1f} KB")
    print(f"  Metadata JSON size: {meta_json_path.stat().st_size / 1024:.1f} KB")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build FAISS index from regulatory documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline: discover → scrape → build
  python scripts/build_rag_index.py --refresh

  # Build index from existing .txt files only
  python scripts/build_rag_index.py --build-only

  # Custom paths
  python scripts/build_rag_index.py --build-only --docs-dir docs/ --output-dir ai-service/data/vector_store/
        """,
    )
    parser.add_argument("--refresh", action="store_true", help="Full pipeline: discover + scrape + build")
    parser.add_argument("--build-only", action="store_true", help="Skip discovery/scraping, build from existing .txt")
    parser.add_argument("--docs-dir", type=str, default=str(DOCS_DIR), help="Path to docs directory")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Output directory for FAISS index")
    parser.add_argument("--model-cache", type=str, default=str(DEFAULT_MODEL_CACHE), help="Cache directory for embedding model")
    args = parser.parse_args()

    if not (args.refresh or args.build_only):
        parser.print_help()
        print("\nError: specify --refresh (full pipeline) or --build-only (index existing files)")
        return

    docs_dir = Path(args.docs_dir)
    output_dir = Path(args.output_dir)
    model_cache = Path(args.model_cache)

    start = time.monotonic()

    if args.refresh:
        run_discover()
        run_scrape()

    run_build(docs_dir, output_dir, model_cache)

    elapsed = time.monotonic() - start
    print(f"\nTotal time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
