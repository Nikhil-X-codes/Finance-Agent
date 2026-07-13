"""Pre-download SentenceTransformer model to the local cache folder."""

import os
import sys

# Ensure correct working directory context
current_dir = os.path.dirname(os.path.abspath(__file__))
cache_folder = os.path.join(current_dir, "data", "model_cache")

print("=" * 60)
print(f"Pre-downloading BAAI/bge-small-en model to:\n{cache_folder}")
print("=" * 60)

try:
    from sentence_transformers import SentenceTransformer
    
    # Download and compile model to cache folder
    SentenceTransformer("BAAI/bge-small-en", cache_folder=cache_folder)
    print("\n[OK] Model successfully downloaded and cached locally!")
    print("=" * 60)
except Exception as e:
    print(f"\n[Error] Failed to download model: {e}")
    sys.exit(1)
