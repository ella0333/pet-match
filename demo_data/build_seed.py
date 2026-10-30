"""Write seed_posts.json: fictional lost and found posts built from the photos.

Each downloaded pet gets a lost post (its first photos) and usually a found
post (its later photos) in a different group, so the right match is known.
People, contacts and places are invented; the town is in town.json.
Edit seed_posts.json by hand afterwards if a post should read differently.
"""
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
PHOTOS = HERE / "photos"
MY_PETS = HERE / "my_pets"
TODAY = date(2026, 10, 20)
random.seed(7)

GROUPS = [g["id"] for g in json.loads((HERE / "groups.json").read_text(encoding="utf-8"))]
TOWN_GROUPS = [g for g in GROUPS if g not in ("millbrook-lost-dogs", "granite-point-cats",
                                               "southgate-buy-sell")]
OFF_GROUP = "southgate-buy-sell"

NEIGHBOURHOODS = ["Old Mill", "Riverside", "Cedar Heights", "Downtown", "Fernwood",
                  "Lark Hill", "Southgate", "Birch Hollow"]
STREETS = {"Old Mill": "Pine Street", "Riverside": "Willow Lane", "Cedar Heights": "Maple Avenue",
           "Downtown": "Church Street", "Fernwood": "Oak Crescent", "Lark Hill": "Summit Drive",
           "Southgate": "Station Road", "Birch Hollow": "Hollow Way"}
NEARBY = {"Old Mill": ["Downtown", "Lark Hill"], "Riverside": ["Downtown", "Southgate"],
          "Cedar Heights": ["Birch Hollow", "Downtown"], "Downtown": ["Old Mill", "Riverside"],
          "Fernwood": ["Southgate", "Old Mill"], "Lark Hill": ["Old Mill", "Cedar Heights"],
          "Southgate": ["Riverside", "Fernwood"], "Birch Hollow": ["Cedar Heights", "Riverside"]}
GROUP_FOR = {"Old Mill": "old-mill-neighbours", "Riverside": "riverside-community",
             "Cedar Heights": "cedar-heights-pets", "Fernwood": "fernwood-parents"}

FIRST = ["Jordan", "Sam", "Riley", "Casey", "Morgan", "Avery", "Quinn", "Jamie", "Taylor",
         "Drew", "Rowan", "Skyler", "Reese", "Emerson", "Hayden", "Parker", "Blake", "Kendall",
         "Logan", "Sasha", "Robin", "Alex", "Charlie", "Dana", "Elliot", "Frankie", "Harper",
         "Jesse", "Kai", "Lane", "Marley", "Noel", "Oakley", "Peyton", "Remy", "Sage"]
LAST = "ABCDEFGHJKLMNPRSTVWY"

LOST_TEMPLATES = [
    "PLEASE SHARE. Our {species} {name} slipped out {day} near {where}. {pronoun_cap} is friendly but nervous with strangers. Please check sheds and garages!",
    "Went missing {day}: {name}, {age}. Last seen around {where}. We're heartbroken, any sightings at all please message me.",
    "Lost {species} in {area}. {name} got out through the back gate {day}. {pronoun_cap} answers to {name} and loves treats. Reward for safe return.",
    "Has anyone seen {name}? Went missing {day} from our place on {where}. Not microchipped. Photos attached, please keep an eye out.",
    "{name} didn't come home {day}. We live just off {where}. {pronoun_cap} has never been gone this long. Please share to local groups!",
]
FOUND_TEMPLATES = [
    "FOUND: {species} wandering near {where} {day}. Seems well cared for, no tag. Keeping {pronoun_obj} safe inside for now, owner please get in touch.",
    "This {species} has been hanging around our yard in {area}, first showed up {day}. Very friendly, looks like someone's pet. Does anyone recognise?",
    "Found {day} by {where}. No collar. Took {pronoun_obj} to get scanned, no microchip. Posting here hoping the owner sees it.",
    "Spotted this {species} near {where} {day} and managed to catch {pronoun_obj}. Is this your pet? Message me with a photo to claim.",
    "Found {species} in {area}, {day}. Clearly lost and hungry. Currently with us, please share so the owner can find {pronoun_obj}.",
]
AGES = ["2 years old", "about 5", "a senior at 11", "just under a year", "7 years old", "3 years old"]


def pet_name(pet_id: str) -> str:
    words = re.sub(r"^(cat|dog)-", "", pet_id).split("-")
    stop = {"cat", "dog", "the", "kitten", "puppy"}
    name = next((w for w in words if w not in stop and not w.isdigit()), words[0])
    return name.capitalize()


def day_phrase(event: date, posted: date) -> str:
    gap = (posted - event).days
    if gap == 0:
        return "today"
    if gap == 1:
        return "yesterday"
    return f"on {event.strftime('%A %B')} {event.day}"


def person(used: set) -> dict:
    while True:
        name = f"{random.choice(FIRST)} {random.choice(LAST)}."
        if name not in used:
            used.add(name)
            break
    slug = name.lower().replace(" ", ".").rstrip(".")
    contact = {"contact_messenger": name}
    if random.random() < 0.6:
        contact["contact_phone"] = f"555-01{random.randint(0, 99):02d}"
    if random.random() < 0.5:
        contact["contact_email"] = f"{slug}@example.com"
    return {"poster": name, **contact}


def make_post(kind, pet_id, species, files, credits, group, where, area, event, used):
    posted = event + timedelta(days=random.choice([0, 0, 1, 1, 2]))
    posted = min(posted, TODAY)
    pronoun = random.choice([("he", "him"), ("she", "her")])
    words = {"species": species, "name": pet_name(pet_id), "where": where, "area": area,
             "day": day_phrase(event, posted), "age": random.choice(AGES),
             "pronoun_cap": pronoun[0].capitalize(), "pronoun_obj": pronoun[1]}
    template = random.choice(LOST_TEMPLATES if kind == "lost" else FOUND_TEMPLATES)
    return {"post_type": kind, "group_id": group, "text": template.format(**words),
            "photos": files, "credits": credits, "demo_pet": pet_id,
            "created_at": f"{posted.isoformat()}T{random.randint(7, 22):02d}:{random.randint(0, 59):02d}:00",
            **person(used)}


def main():
    credits = json.loads((PHOTOS / "credits.json").read_text(encoding="utf-8"))
    pets: dict[str, list[dict]] = {}
    for c in credits:
        pets.setdefault(c["pet"], []).append(c)

    posts, used = [], set()
    pet_ids = sorted(pets)
    random.shuffle(pet_ids)
    for i, pet_id in enumerate(pet_ids):
        files = pets[pet_id]
        species = files[0]["species"]
        home = random.choice(NEIGHBOURHOODS)
        lost_day = TODAY - timedelta(days=random.randint(3, 25))
        found_day = lost_day + timedelta(days=random.randint(0, 9))
        found_day = min(found_day, TODAY)
        found_area = random.choice(NEARBY[home]) if random.random() < 0.7 else home

        lost_where = random.choice([f"{STREETS[home]}, {home}", home])
        found_where = random.choice([STREETS[found_area], f"{found_area}, Alder Falls", found_area])
        lost_group = GROUP_FOR.get(home, random.choice(TOWN_GROUPS))
        found_group = random.choice([g for g in TOWN_GROUPS if g != lost_group])

        # Roles: most pets have both sides; some only one side as noise;
        # one pair is found before it was lost; one found post sits in a
        # group that has not opted in.
        role = "pair"
        if i % 6 == 4:
            role = "lost_only"
        elif i % 6 == 5:
            role = "found_only"
        if i == 0:
            role = "found_before_lost"
        if i == 1:
            role = "off_group"
        if len(files) < 2:
            role = "lost_only"

        split = max(1, len(files) // 2)
        lost_files, found_files = files[:split], files[split:]
        if role in ("pair", "lost_only", "found_before_lost", "off_group"):
            posts.append(make_post("lost", pet_id, species, ["photos/" + f["file"] for f in lost_files],
                                   lost_files, lost_group, lost_where, home, lost_day, used))
        if role in ("pair", "found_only", "found_before_lost", "off_group"):
            if role == "found_before_lost":
                found_day = lost_day - timedelta(days=6)
            group = OFF_GROUP if role == "off_group" else found_group
            posts.append(make_post("found", pet_id, species, ["photos/" + f["file"] for f in found_files],
                                   found_files, group, found_where, found_area, found_day, used))

    # Gabriella's own cats: demo_data/my_pets/<Name>_01.jpg and so on. The
    # first photo is the lost post, the rest the found post. Both cats go
    # missing in the same area a day apart, so only the photos can tell
    # the two grey tabbies apart.
    if MY_PETS.exists():
        mine: dict[str, list[str]] = {}
        for f in sorted(MY_PETS.rglob("*")):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                name = f.parent.name if f.parent != MY_PETS else f.stem.split("_")[0]
                mine.setdefault(name.lower(), []).append(f.relative_to(HERE).as_posix())
        lost_day = TODAY - timedelta(days=5)
        for k, (name, files) in enumerate(sorted(mine.items())):
            if len(files) < 2:
                continue
            pet_id = f"cat-{name}"
            day = lost_day + timedelta(days=k)
            posts.append(make_post("lost", pet_id, "cat", files[:1], [None],
                                   "alder-falls-lost-found", "Summit Drive, Lark Hill",
                                   "Lark Hill", day, used))
            posts.append(make_post("found", pet_id, "cat", files[1:], [None] * (len(files) - 1),
                                   random.choice(["old-mill-neighbours", "cedar-heights-pets"]),
                                   random.choice(["Pine Street", "Maple Avenue"]), "Old Mill",
                                   day + timedelta(days=2), used))

    posts.sort(key=lambda p: p["created_at"])
    (HERE / "seed_posts.json").write_text(json.dumps(posts, indent=2), encoding="utf-8")
    kinds = {}
    for p in posts:
        kinds[p["post_type"]] = kinds.get(p["post_type"], 0) + 1
    print(f"{len(posts)} posts from {len(pets)} pets: {kinds}")


if __name__ == "__main__":
    main()
