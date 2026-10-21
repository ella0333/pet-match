# Pet Match

A concept feature for Facebook that lets anyone search lost and found pet posts across every group that opts in, without joining those groups. Photos are matched with DINOv3, the pet is cut out of each photo with SAM 3.1, and Muse Spark reads each post and checks the top candidates side by side.

## Setup

Install the Python packages.

    pip install -r requirements.txt

The app reads the Meta Model API key from the file named in PET_MATCH_CREDENTIALS, or from the MODEL_API_KEY environment variable.

DINOv3 runs on Modal. Log in to Modal once, store a Hugging Face token that has access to facebook/dinov3-vitb16-pretrain-lvd1689m as the Modal secret pet-match-hf, then deploy the embedding app.

    python -m modal token new
    python -m modal secret create pet-match-hf HF_TOKEN=<token>
    python -m modal deploy modal_embed.py

## Demo data

Download the demo photos from Wikimedia Commons, build the fictional posts, then load them into the index. Loading uses Meta Model API credit for every post.

    python demo_data/fetch_photos.py
    python demo_data/build_seed.py
    python -m demo_data.seed

## Run

    python -m uvicorn app.main:app --port 8040

Then open http://localhost:8040.
