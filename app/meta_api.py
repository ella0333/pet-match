"""Calls to the Meta Model API: SAM 3.1 for cutting the pet out of a photo,
Muse Spark for reading posts and comparing two posts side by side."""
import base64
import io
import json
import re

from openai import OpenAI
from PIL import Image

from . import config

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=config.META_BASE_URL, api_key=config.meta_api_key())
    return _client


def _log_usage(model: str, resp):
    """Append token counts per call to data/usage.jsonl to track credit spend."""
    u = getattr(resp, "usage", None)
    row = {"model": model,
           "input": getattr(u, "input_tokens", None),
           "output": getattr(u, "output_tokens", None)}
    with open(config.DATA / "usage.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def data_url(image_bytes: bytes) -> str:
    mime = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


def _image_part(image_bytes: bytes) -> dict:
    return {"type": "input_image", "image_url": data_url(image_bytes)}


# SAM 3.1 -------------------------------------------------------------------

BOX = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)")


def find_pet_boxes(image_bytes: bytes, species: str) -> list[tuple[int, int, int, int]]:
    """Boxes in original pixel coordinates for every animal SAM finds."""
    prompt = species if species in ("cat", "dog") else "animal"
    resp = client().responses.create(
        model=config.SAM_MODEL,
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            _image_part(image_bytes),
        ]}],
    )
    _log_usage(config.SAM_MODEL, resp)
    width, height = Image.open(io.BytesIO(image_bytes)).size
    boxes = []
    for x1, y1, x2, y2, w, h in BOX.findall(resp.output_text or ""):
        sx, sy = width / int(w), height / int(h)
        boxes.append((int(int(x1) * sx), int(int(y1) * sy), int(int(x2) * sx), int(int(y2) * sy)))
    return boxes


def crop_pet(image_bytes: bytes, species: str) -> tuple[bytes, int]:
    """Crop to the largest animal SAM finds, with a little margin.

    Returns the JPEG crop and how many animals were found. With no animal
    found the whole photo is kept so the post still gets an embedding.
    """
    boxes = find_pet_boxes(image_bytes, species)
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if boxes:
        x1, y1, x2, y2 = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        pad_x, pad_y = int((x2 - x1) * 0.08), int((y2 - y1) * 0.08)
        img = img.crop((max(0, x1 - pad_x), max(0, y1 - pad_y),
                        min(img.width, x2 + pad_x), min(img.height, y2 + pad_y)))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue(), len(boxes)


# Muse Spark ----------------------------------------------------------------

def _structured(prompt: str, images: list[bytes], name: str, schema: dict) -> dict:
    content = [{"type": "input_text", "text": prompt}] + [_image_part(b) for b in images]
    resp = client().responses.create(
        model=config.CHAT_MODEL,
        input=[{"type": "message", "role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
    )
    _log_usage(config.CHAT_MODEL, resp)
    return json.loads(resp.output_text)


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props),
            "additionalProperties": False}


STR = {"type": "string"}
STR_LIST = {"type": "array", "items": STR}

POST_SCHEMA = _obj({
    "post_type": {"type": "string", "enum": ["lost", "found", "unknown"]},
    "species": {"type": "string", "enum": ["cat", "dog", "other"]},
    "pet_name": STR,
    "colors": STR_LIST,
    "pattern": STR,
    "markings": STR_LIST,
    "collar": STR,
    "sex": {"type": "string", "enum": ["male", "female", "unknown"]},
    "size": {"type": "string", "enum": ["small", "medium", "large", "unknown"]},
    "location_text": STR,
    "location_precision": {"type": "string", "enum":
                           ["address", "street", "neighbourhood", "city", "region", "unknown"]},
    "event_date": STR,
    "summary": STR,
})

POST_PROMPT = """You read lost and found pet posts from local community groups.
Today is {today}. The post was written on {posted}.

Post text:
\"\"\"{text}\"\"\"

The photos attached are of the pet in this post. Fill every field:
- post_type: lost if the writer's own pet is missing, found if they found or are holding someone else's pet.
- colors, pattern, markings: what you can see in the photos and read in the text. Markings are distinctive features like a white paw, a notched ear, a kinked tail.
- collar: describe it, or "none" if clearly absent, or "unknown".
- pet_name: the name if given, else "".
- location_text: where the pet went missing or was found, copied as written, else "".
- location_precision: how specific that location is.
- event_date: the date it went missing or was found as YYYY-MM-DD, resolving words like "yesterday" against the post date; "" if not stated.
- summary: one short line describing the pet."""

VERDICT_SCHEMA = _obj({
    "same_pet_likelihood": {"type": "integer"},
    "matching_features": STR_LIST,
    "conflicts": STR_LIST,
    "summary": STR,
})

VERDICT_PROMPT = """Two posts from local pet groups. Decide how likely it is that they show the same individual animal.

The first {n_a} photo(s) belong to post A, the remaining {n_b} photo(s) to post B.

Post A ({type_a}): {text_a}
Post B ({type_b}): {text_b}

Compare the animals themselves: coat colour and pattern, markings, eye colour, ear and tail shape, build. Lighting, background, pose and collars can change between a home photo and a photo taken outside. Be strict about breeds or colours that look alike but differ in a specific marking.

Return same_pet_likelihood from 0 to 100, the features that match, any conflicts, and a one-line summary a pet owner can read."""


def read_post(text: str, images: list[bytes], posted: str, today: str) -> dict:
    prompt = POST_PROMPT.format(text=text, posted=posted, today=today)
    return _structured(prompt, images[:4], "pet_post", POST_SCHEMA)


def compare_posts(a: dict, b: dict, images_a: list[bytes], images_b: list[bytes]) -> dict:
    images_a, images_b = images_a[:2], images_b[:2]
    prompt = VERDICT_PROMPT.format(
        n_a=len(images_a), n_b=len(images_b),
        type_a=a["post_type"], type_b=b["post_type"],
        text_a=a["text"], text_b=b["text"])
    verdict = _structured(prompt, images_a + images_b, "match_verdict", VERDICT_SCHEMA)
    verdict["same_pet_likelihood"] = max(0, min(100, int(verdict["same_pet_likelihood"])))
    return verdict
