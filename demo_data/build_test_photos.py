"""Build web/test-photos.zip: photos that aren't in any post, for trying a search.

Run from the project folder: python demo_data/build_test_photos.py
"""
import json
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
PHOTOS = HERE / "photos"
OUT = HERE.parent / "web" / "test-photos.zip"

# (folder in the zip, photo, what it should find)
PICKS = [
    ("try-with-i-found-a-pet", "cat-larry-the-cat/3.jpg", "Larry, posted as lost"),
    ("try-with-i-found-a-pet", "cat-miyako-cat/3.jpg", "Miyako, posted as lost"),
    ("try-with-i-found-a-pet", "cat-caramel-red-tabby-cat/2.jpg", "Caramel, posted as lost"),
    ("try-with-i-found-a-pet", "cat-erik-the-cat-sk-lsk-r/3.jpg", "Erik, posted as lost"),
    ("try-with-i-lost-a-pet", "dog-eddi-dog/1.jpg", "Eddi, posted as found"),
    ("try-with-i-lost-a-pet", "dog-madsen-the-dog-esbjerg/1.jpg", "Madsen, posted as found"),
    ("opt-in-demo-try-with-i-lost-a-pet", "cat-doraemon-cat/1.jpg",
     "Doraemon, posted as found in the Opt-in demo group, so it only matches once that group is switched on"),
]

README = """Test photos for the Pet Match demo

Apart from Doraemon's, none of these photos are in any post, so each one is a fair test. Doraemon's photo comes from his owner's lost post, and the search compares it with found posts only.

try-with-i-found-a-pet: press I found a pet and upload one. Each cat's owner has a lost post, which should come up as the top match.

try-with-i-lost-a-pet: press I lost a pet and upload one. Someone has posted each dog as found, which should come up as the top match.

opt-in-demo-try-with-i-lost-a-pet: press I lost a pet and upload it. Doraemon was found by someone in the Opt-in demo group. With that group switched off, Doraemon's found post doesn't appear in the results; switch the group on and search again to see it come up.

The "where and when" box is optional. Photo credits are in CREDITS.txt.
"""


def main():
    credits = {c["file"]: c for c in json.loads((PHOTOS / "credits.json").read_text(encoding="utf-8"))}
    lines = []
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README)
        for folder, photo, finds in PICKS:
            name = f"{folder}/{photo.split('/')[0]}{Path(photo).suffix}"
            z.write(PHOTOS / photo, name)
            c = credits[photo]
            lines.append(f"{name}: {finds}. {c['author'] or 'Unknown author'}, {c['license']}, {c['page']}")
        z.writestr("CREDITS.txt", "\n".join(lines) + "\n")
    print(f"wrote {OUT} with {len(PICKS)} photos")


if __name__ == "__main__":
    main()
