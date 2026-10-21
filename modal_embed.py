"""DINOv3 image embeddings on Modal.

Deploy with: python -m modal deploy modal_embed.py
The app calls Embedder.embed with a list of JPEG/PNG bytes and gets back one
L2-normalised vector per image.
"""
import modal

MODEL_ID = "facebook/dinov3-vitb16-pretrain-lvd1689m"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch", "torchvision", "transformers>=4.56", "accelerate", "pillow", "huggingface_hub")
)
app = modal.App("pet-match-embed", image=image)
weights = modal.Volume.from_name("pet-match-hf-cache", create_if_missing=True)


@app.cls(
    cpu=4.0,
    memory=4096,
    secrets=[modal.Secret.from_name("pet-match-hf")],
    volumes={"/cache": weights},
    scaledown_window=300,
)
class Embedder:
    @modal.enter()
    def load(self):
        import os
        os.environ["HF_HOME"] = "/cache"
        import torch
        from transformers import AutoImageProcessor, AutoModel

        self.torch = torch
        self.processor = AutoImageProcessor.from_pretrained(MODEL_ID)
        self.model = AutoModel.from_pretrained(MODEL_ID).eval()
        weights.commit()

    @modal.method()
    def embed(self, images: list[bytes]) -> list[list[float]]:
        import io
        from PIL import Image

        pics = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
        inputs = self.processor(images=pics, return_tensors="pt")
        with self.torch.inference_mode():
            pooled = self.model(**inputs).pooler_output
        pooled = self.torch.nn.functional.normalize(pooled.float(), dim=-1)
        return pooled.cpu().tolist()
