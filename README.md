# Pet Match

This is a mock integration showing how a lost and found pet search could work inside Facebook. It is not a real Facebook or Meta product. The groups, people and posts in the demo are simulated, and the photo matching is real.

Today, finding a lost pet on Facebook means joining every local lost and found group and scrolling through each one. Pet Match lets groups opt in to a shared index, so anyone can post a lost or found pet once and see likely matches from every participating group without joining them. When a new post matches an existing one, the owner of the existing post is notified.

## How matching works

Muse Spark 1.3 reads each post and its photos and returns structured details: lost or found, species, colours, markings, collar, where and when. SAM 3.1 finds the animal in each photo so the background doesn't affect the comparison. DINOv3, Meta's open-weights vision model, turns each cutout into an embedding, so photos of the same animal land close together.

Impossible pairs are removed first: the same post type, a different species, a pet found before it went missing, or one found farther away than it could plausibly have travelled. The rest are ranked by photo similarity, description agreement, distance and timing. Muse Spark then looks at the top ten side by side and gives a likelihood with the features that match and any conflicts, which are shown on each result.

## Setup

You need a Meta Model API key, a Modal account, and a Hugging Face account that has been granted access to facebook/dinov3-vitb16-pretrain-lvd1689m.

Install the Python packages.

    pip install -r requirements.txt

Set your Meta Model API key in the environment.

    export MODEL_API_KEY=<your key>

Log in to Modal, store your Hugging Face token as a Modal secret, and deploy the DINOv3 embedding app.

    python -m modal token new
    python -m modal secret create pet-match-hf HF_TOKEN=<your token>
    python -m modal deploy modal_embed.py

## Demo data

The demo photos come from Wikimedia Commons and are listed with their authors and licenses in demo_data/photos/credits.json. The people, places and posts are invented, and the town in demo_data/town.json is fictional.

Build the posts, load them into the index, run the accuracy check and save the result as the reset point for the demo. Loading uses Meta Model API credit for every post.

    python demo_data/build_seed.py
    python -m demo_data.seed
    python -m demo_data.accuracy
    python -c "from app import store; store.snapshot()"

To use photos of your own pets, put them in demo_data/my_pets named like Name_01.jpg, Name_02.jpg before building the posts. The first photo becomes a lost post and the rest a found post.

## Run locally

    python -m uvicorn app.main:app --port 8040

Then open http://localhost:8040.

## Host on Modal

Store your Meta key as a Modal secret, upload the loaded data to a Modal volume, and deploy the web app.

    python -m modal secret create pet-match-meta MODEL_API_KEY=<your key>
    python -m modal volume create pet-match-data
    python -m modal volume put pet-match-data data/pet_match.db /pet_match.db
    python -m modal volume put pet-match-data data/seed_snapshot.db /seed_snapshot.db
    python -m modal volume put pet-match-data data/uploads /uploads
    python -m modal deploy modal_web.py

The hosted demo limits spending: each visitor can add 3 posts a day, the site allows 60 new posts a day, and new posts switch off once the demo has spent 25 dollars of Meta credit (set PET_MATCH_SPEND_CEILING to change it). Browsing and searching existing posts stay free because match checks are saved.
