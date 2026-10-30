"""Host the demo on Modal: the API and page in one web app.

The database and photos live on the Modal volume pet-match-data, and the Meta
key comes from the Modal secret pet-match-meta (MODEL_API_KEY).

Deploy with: python -m modal deploy modal_web.py
"""
import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi", "uvicorn", "python-multipart", "openai", "modal", "numpy",
                 "pillow", "requests")
    .env({"PET_MATCH_DATA": "/data", "PET_MATCH_HOSTED": "1"})
    .add_local_dir("app", "/root/app")
    .add_local_dir("web", "/root/web")
    .add_local_file("demo_data/town.json", "/root/demo_data/town.json")
)
app = modal.App("pet-match-web", image=image)
volume = modal.Volume.from_name("pet-match-data", create_if_missing=True)


# One container, so the SQLite database on the volume has a single writer.
@app.function(
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("pet-match-meta")],
    max_containers=1,
    scaledown_window=900,
    timeout=600,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    from app import main

    main.after_write = volume.commit
    return main.app
