"""Turn a raw post (text, photos, contact details) into an indexed post."""
from datetime import datetime

from . import config, embed, geo, matching, meta_api, store


def ingest_post(text: str, images: list[bytes], poster: str, *,
                post_type: str | None = None, group_id: str | None = None,
                contact_messenger: str = "", contact_phone: str = "",
                contact_email: str = "", created_at: str | None = None,
                today: str | None = None, demo_pet: str | None = None,
                credits: list[dict | None] | None = None, notify: bool = True) -> int:
    created_at = created_at or datetime.now().isoformat(timespec="seconds")
    today = today or created_at[:10]

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
        store.add_photo(post_id, original.relative_to(config.ROOT).as_posix(),
                        cropped.relative_to(config.ROOT).as_posix(), n, vec, credits[i])

    if notify:
        matching.notify_matches(post_id, created_at)
    return post_id
