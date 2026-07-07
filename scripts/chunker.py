"""Lightweight CLI wrapper for chunking files.

Usage:
    python scripts/chunker.py --input docs/sebi/xyz.txt --output test_chunks.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to python path to import build_rag_index
sys.path.append(str(Path(__file__).resolve().parents[1]))
from scripts.build_rag_index import chunk_text, _extract_title


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk text files and output JSON")
    parser.add_argument("--input", required=True, help="Input text file path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist")
        sys.exit(1)

    try:
        text = input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            raw = input_path.read_bytes()
            try:
                import chardet
                detected = chardet.detect(raw)
                encoding = detected.get("encoding", "utf-8") or "utf-8"
            except ImportError:
                encoding = "utf-8"
            text = raw.decode(encoding, errors="ignore")
        except Exception as e:
            print(f"Error reading input file: {e}")
            sys.exit(1)
    title = _extract_title(text, input_path.name)
    chunks = chunk_text(text)

    output_chunks = []
    for c in chunks:
        output_chunks.append({
            "title": title,
            "chunk_index": c["chunk_index"],
            "text": c["text"],
            "char_start": c["char_start"],
            "char_end": c["char_end"]
        })

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output_chunks, f, indent=2, ensure_ascii=False)

    print(f"Successfully chunked {input_path} into {len(output_chunks)} chunks -> {output_path}")


if __name__ == "__main__":
    main()
