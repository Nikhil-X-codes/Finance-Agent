"""RAG service backed by a pre-built FAISS index loaded with mmap."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np

try:
    import faiss
except Exception:
    faiss = None


@dataclass(slots=True)
class Citation:
    source: str
    doc_title: str
    section: str
    date: str | None
    relevant_text: str
    score: float


class RAGService:
    _instance: "RAGService | None" = None

    @classmethod
    def get_instance(
        cls,
        index_path: str | None = None,
        metadata_path: str | None = None,
        index: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "RAGService":
        if cls._instance is None:
            from ..config.settings import settings
            idx_path = index_path or settings.faiss_index_path
            meta_path = metadata_path or settings.faiss_metadata_path
            cls._instance = cls(
                index_path=idx_path,
                metadata_path=meta_path,
                index=index,
                metadata=metadata,
            )
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def __init__(
        self,
        index_path: str,
        metadata_path: str | None = None,
        index: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index = index or self._load_index(index_path)
        self.metadata = metadata or self._load_metadata(metadata_path)

    def _load_index(self, index_path: str):
        if faiss is None:
            raise RuntimeError("faiss is not installed")
        path = Path(index_path)
        if not path.exists():
            # Try fallback to index.faiss
            alt = path.parent / "index.faiss"
            if alt.exists():
                path = alt
            else:
                raise FileNotFoundError(index_path)
        return faiss.read_index(str(path), faiss.IO_FLAG_MMAP | faiss.IO_FLAG_READ_ONLY)

    def _load_metadata(self, metadata_path: str | None) -> dict[str, Any]:
        if not metadata_path:
            return {}
        path = Path(metadata_path)
        if not path.exists():
            # Try fallback to meta.json
            alt = path.parent / "meta.json"
            if alt.exists():
                path = alt
            else:
                return {}

        # Detect SQLite database file (by suffix or signature)
        is_sqlite = False
        if path.suffix.lower() in [".db", ".sqlite", ".sqlite3"]:
            is_sqlite = True
        else:
            try:
                with path.open("rb") as f:
                    header = f.read(16)
                    if header.startswith(b"SQLite format 3"):
                        is_sqlite = True
            except Exception:
                pass

        if is_sqlite:
            import sqlite3
            conn = sqlite3.connect(str(path))
            try:
                cursor = conn.cursor()
                # Check if chunk_metadata table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_metadata'")
                if not cursor.fetchone():
                    return {}
                cursor.execute("SELECT chunk_id, source, filename, title, chunk_index, text FROM chunk_metadata")
                rows = cursor.fetchall()
                metadata = {}
                for row in rows:
                    chunk_id, source, filename, title, chunk_index, text = row
                    metadata[str(chunk_id)] = {
                        "source": source,
                        "filename": filename,
                        "title": title,
                        "doc_title": title,
                        "chunk_index": chunk_index,
                        "text": text,
                    }
                return metadata
            except Exception as e:
                print(f"Failed to load metadata from SQLite DB: {e}")
                return {}
            finally:
                conn.close()

        # Try utf-8 JSON loading first
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except UnicodeDecodeError:
            pass
        except json.JSONDecodeError:
            pass

        # Detect encoding fallback
        try:
            raw_bytes = path.read_bytes()
            encoding = "utf-8"
            try:
                import chardet
                detected = chardet.detect(raw_bytes)
                encoding = detected.get("encoding", "utf-8") or "utf-8"
            except ImportError:
                pass
            return json.loads(raw_bytes.decode(encoding, errors="ignore"))
        except Exception as e:
            print(f"Failed to load metadata JSON: {e}")
            return {}

    def search(
        self,
        embedding: list[float] | np.ndarray | None = None,
        top_k: int = 5,
        min_score: float = 0.65,
        vector: list[float] | np.ndarray | None = None,
    ) -> list[dict[str, Any]]:
        """Search the FAISS index using query vector or embedding."""
        if self.index is None:
            return []

        target = embedding if embedding is not None else vector
        if target is None:
            return []

        query = np.asarray(target, dtype="float32").reshape(1, -1)
        scores, indexes = self.index.search(query, top_k)
        results: list[dict[str, Any]] = []
        for score, index in zip(scores[0], indexes[0]):
            if index < 0 or float(score) < min_score:
                continue
            payload = self.metadata.get(str(index), {})
            results.append(
                {
                    "chunk_id": int(index),
                    "score": float(score),
                    "source": payload.get("source", "unknown"),
                    "doc_title": payload.get("doc_title", payload.get("title", "unknown")),
                    "section": payload.get("section", payload.get("section_heading", "unknown")),
                    "date": payload.get("date"),
                    "text": payload.get("text", ""),
                }
            )
        return results

    @staticmethod
    def format_citation(result: dict[str, Any]) -> Citation:
        return Citation(
            source=str(result.get("source", "unknown")),
            doc_title=str(result.get("doc_title", "unknown")),
            section=str(result.get("section", "unknown")),
            date=result.get("date"),
            relevant_text=str(result.get("text", "")),
            score=float(result.get("score", 0.0)),
        )
