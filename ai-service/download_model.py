"""Pre-download SentenceTransformer model to the configured cache folder."""

import os
import sys

# Ensure correct working directory context and project root is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from src.config.settings import settings
    from src.services.embedding_service import get_embedding_service
    
    print("=" * 60)
    print(f"Pre-downloading embedding model: {settings.embedding_model_name}")
    print(f"Target cache folder: {settings.embedding_cache_folder}")
    print("=" * 60)
    
    # Initialize the service, triggering download if not present
    get_embedding_service(
        model_name=settings.embedding_model_name,
        cache_folder=settings.embedding_cache_folder
    )
    
    print("\n[OK] Model successfully downloaded and cached locally!")
    print("=" * 60)
except Exception as e:
    print(f"\n[Error] Failed to download model: {e}")
    sys.exit(1)
