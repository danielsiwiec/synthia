from typing import Any, cast

from loguru import logger

_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class _EmbeddingModel:
    _instance: Any = None

    @classmethod
    def get(cls) -> Any:
        if cls._instance is None:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {_EMBEDDING_MODEL}")
            cls._instance = SentenceTransformer(_EMBEDDING_MODEL)
        return cls._instance


def generate_embedding(text: str) -> list[float]:
    model = _EmbeddingModel.get()
    truncated_text = text[:2000]
    embedding = model.encode(truncated_text, normalize_embeddings=True)
    return cast(list[float], embedding.tolist())
