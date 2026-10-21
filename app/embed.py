"""DINOv3 embeddings, computed by the Modal app in modal_embed.py."""
import modal
import numpy as np

from . import config

_embedder = None


def embed(images: list[bytes]) -> np.ndarray:
    global _embedder
    if not images:
        return np.zeros((0, 0), dtype=np.float32)
    if _embedder is None:
        _embedder = modal.Cls.from_name(config.EMBED_APP, "Embedder")()
    return np.asarray(_embedder.embed.remote(images), dtype=np.float32)
