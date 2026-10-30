"""Check how often the right pet comes out on top for the seeded posts.

For every lost post whose found partner is searchable (same demo pet, in an
opted-in group, found after it was lost), report where the partner ranks
before and after the Muse Spark check. Comparisons are saved, so the demo
can show these searches later without new calls.

Run from the project folder: python -m demo_data.accuracy
"""
import json

from app import config, matching, store


def main():
    posts = store.searchable_posts()
    found_by_pet = {}
    for p in posts:
        if p["post_type"] == "found":
            found_by_pet.setdefault(p["demo_pet"], []).append(p["id"])

    rows = []
    for p in posts:
        if p["post_type"] != "lost" or p["demo_pet"] not in found_by_pet:
            continue
        partners = set(found_by_pet[p["demo_pet"]])
        results = matching.find_matches(p["id"])
        reranked = [r["post"]["id"] for r in results]
        by_score = [r["post"]["id"] for r in sorted(results, key=lambda r: r["combined"],
                                                    reverse=True)]

        def rank(order):
            hits = [i for i, pid in enumerate(order, 1) if pid in partners]
            return hits[0] if hits else None

        top = results[0] if results else None
        rows.append({
            "pet": p["demo_pet"], "lost_post": p["id"],
            "rank_by_score": rank(by_score), "rank_after_check": rank(reranked),
            "top_likelihood": top["verdict"]["same_pet_likelihood"] if top and "verdict" in top else None,
        })
        print(f"{p['demo_pet']:45s} score rank {rank(by_score)}  after check {rank(reranked)}",
              flush=True)

    def share(key, k):
        return sum(1 for r in rows if r[key] is not None and r[key] <= k) / max(1, len(rows))

    summary = {
        "lost_posts_with_partner": len(rows),
        "top1_by_score": share("rank_by_score", 1), "top3_by_score": share("rank_by_score", 3),
        "top1_after_check": share("rank_after_check", 1),
        "top3_after_check": share("rank_after_check", 3),
    }
    print(json.dumps(summary, indent=2))
    (config.DATA / "accuracy.json").write_text(json.dumps({"summary": summary, "rows": rows},
                                                          indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
