from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.config.settings import settings
from src.services.embedding_service import get_embedding_service
from src.services.rag_service import RAGService

router = APIRouter()


# Schema for RAG retrieval
class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = 5
    min_score: float = 0.65


# Initialize RAGService
try:
    rag_service = RAGService.get_instance()
except Exception as e:
    # Set to None, can retry initialization or fail gracefully in route
    print(f"Warning: RAGService initialization deferred or failed: {e}")
    rag_service = None


@router.post("/v1/rag")
async def rag_retrieve(payload: RAGRequest) -> dict:
    global rag_service
    # Lazy initialization retry if it failed at import time (e.g. if index wasn't built yet)
    if rag_service is None:
        try:
            rag_service = RAGService.get_instance()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"RAG service is unavailable: {e}"
            )

    try:
        # Get embedding service
        embed_service = get_embedding_service(
            model_name=settings.embedding_model_name,
            cache_folder=settings.embedding_cache_folder,
        )
        
        # Embed query text
        query_vector = await embed_service.embed(payload.query)
        
        # Query FAISS index
        results = rag_service.search(
            embedding=query_vector,
            top_k=payload.top_k,
            min_score=payload.min_score,
        )
        
        return {"results": results}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"RAG retrieval failed: {str(e)}"
        )
