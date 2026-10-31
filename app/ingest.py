"""Turn a raw post (text, photos, contact details) into an indexed post."""
import io
from datetime import datetime

from PIL import Image, ImageOps

from . import config, embed, geo, matching, meta_api, store

MAX_SIDE = 1280


def normalise(image_bytes: bytes) -> bytes:
    """Shrink to MAX_SIDE and re-encode, which also drops EXIF and GPS data."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def prepare_upload(text: str, images: list[bytes], post_type: str) -> tuple[dict, object, list[bytes]]:
    """Read and embed a visitor's upload without storing anything.

    Returns a post-shaped dict (id -1), its embeddings and the pet crops."""
    today = datetime.now().date().isoformat()
    images = [normalise(b) for b in images]
    fields = meta_api.read_post(text, images, posted=today, today=today)
    fields["post_type"] = post_type
    species = fields["species"]
    crops = [meta_api.crop_pet(img, species)[0] for img in images]
    vectors = embed.embed(crops)
    where = geo.locate(fields["location_text"], fields["location_precision"])
    lat, lon, radius = where if where else (None, None, None)
    me = {"id": -1, "post_type": post_type, "species": species, "fields": fields,
          "text": text or "(no details given)", "lat": lat, "lon": lon, "radius_km": radius,
          "event_date": fields["event_date"] or None}
    return me, vectors, crops


def ingest_post(text: str, images: list[bytes], poster: str, *,
                post_type: str | None = None, group_id: str | None = None,
                contact_messenger: str = "", contact_phone: str = "",
                contact_email: str = "", created_at: str | None = None,
                today: str | None = None, demo_pet: str | None = None,
                credits: list[dict | None] | None = None, notify: bool = True) -> int:
    created_at = created_at or datetime.now().isoformat(timespec="seconds")
    today = today or created_at[:10]
    images = [normalise(b) for b in images]

    fields = meta_api.read_post(text, images, posted=created_at[:10], today=today)
    if post_type in ("lost", "found"):
        fields["post_type"] = post_type
    species = fields["species"]

    crops, counts = [], []
    for img in images:
        crop, n = meta_api.crop_pet(img, species)
        crops.append(crop)
        counts.append(n)
    vectors = embed.embed(crops)

    where = geo.locate(fields["location_text"], fields["location_precision"])
    lat, lon, radius = where if where else (None, None, None)

    post_id = store.add_post({
        "group_id": group_id, "poster": poster, "text": text,
        "post_type": fields["post_type"], "species": species, "fields": fields,
        "lat": lat, "lon": lon, "radius_km": radius,
        "event_date": fields["event_date"] or None, "created_at": created_at,
        "contact_messenger": contact_messenger, "contact_phone": contact_phone,
        "contact_email": contact_email, "demo_pet": demo_pet,
    })

    folder = config.UPLOADS / str(post_id)
    folder.mkdir(parents=True, exist_ok=True)
    credits = credits or [None] * len(images)
    for i, (img, crop, n, vec) in enumerate(zip(images, crops, counts, vectors)):
        ext = ".png" if img[:4] == b"\x89PNG" else ".jpg"
        original = folder / f"{i + 1}{ext}"
        cropped = folder / f"{i + 1}_crop.jpg"
        original.write_bytes(img)
        cropped.write_bytes(crop)
        store.add_photo(post_id, original.relative_to(config.DATA).as_posix(),
                        cropped.relative_to(config.DATA).as_posix(), n, vec, credits[i])

    if notify:
        matching.notify_matches(post_id, created_at)
    return post_id
