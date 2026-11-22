"""
Market Insights Module
Turns pasted Meesho search/feed API responses into per-category statistics
(price band, rating floor, dispatch tag, designs, common title words).

Only a compact set of public catalog fields is stored. Cookies, tokens and
the raw response are never saved.

Storage: Supabase table `market_snapshots` (see database.MARKET_SNAPSHOTS_SQL),
with a local `market_insights.json` fallback when Supabase is unavailable.
"""

import json
import math
import os
import re
from collections import Counter
from datetime import date, datetime, timezone

import database

LOCAL_FILE = "market_insights.json"
NEXT_DAY_TAG = "NEXT DAY DISPATCH"
MIN_LISTINGS_FOR_BAND = 10

STOPWORDS = {
    "for", "and", "the", "with", "from", "you", "your", "this", "that",
    "are", "its", "has", "can", "our", "pack", "set",
}


class InsightsError(Exception):
    """Raised when a pasted response cannot be used."""


# ─── PARSING ──────────────────────────────────────────────────────────────────

def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _detail(text, key):
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", text or "", re.M)
    return m.group(1).strip() if m else ""


def parse_json_text(text):
    """Parse pasted/uploaded text into a dict, with a clear error for non-JSON."""
    raw = (text or "").strip()
    if not raw:
        raise InsightsError("Khali hai. Response JSON paste karo.")
    if raw.lower().startswith("curl"):
        raise InsightsError("Ye curl command hai. Isme cookies hoti hain, "
                            "sirf response JSON paste karo (DevTools > Network > Response).")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise InsightsError(f"JSON sahi nahi hai: {e}")


def parse_response(data):
    """Extract a compact list of listings from a Meesho search/feed response dict."""
    if not isinstance(data, dict) or not isinstance(data.get("catalogs"), list):
        raise InsightsError("Is JSON me 'catalogs' list nahi mili. "
                            "Meesho search ya feed ka response paste karo.")
    out = []
    for pos, c in enumerate(data["catalogs"], 1):
        if not isinstance(c, dict):
            continue
        cat_rev = c.get("catalog_reviews_summary") or {}
        sup_rev = c.get("supplier_reviews_summary") or {}
        rev = cat_rev or sup_rev
        rating_source = "catalog" if cat_rev else ("supplier" if sup_rev else "")

        price = _float(c.get("min_product_price") or c.get("min_catalog_price"))
        offers = (c.get("special_offers") or {}).get("offers") or []
        offer_total = sum((_float(o.get("amount")) or 0) for o in offers if isinstance(o, dict))
        effective = round(price - offer_total, 2) if price and offers else None

        tag_names = [t.get("name") for t in (c.get("tags") or []) if isinstance(t, dict)]
        tag_names.append((c.get("value_prop_tag") or {}).get("name"))

        details = c.get("full_details") or ""
        dm = re.search(r"Dispatch:\s*(\d+)(?:-\d+)?\s*Day", c.get("share_text") or "")
        meta = (c.get("app_event_data") or {}).get("candidate_metadata") or {}

        out.append({
            "id": c.get("id") or c.get("catalogId"),
            "position": pos,
            "title": c.get("hero_product_name") or c.get("name") or "",
            "catalog_name": c.get("name") or "",
            "category": c.get("sub_sub_category_name") or "",
            "price": price,
            "effective_price": effective,
            "mrp": _float(c.get("original_price")),
            "discount_pct": _float(c.get("max_product_discount")),
            "rating": _float(rev.get("average_rating")),
            "rating_count": int(rev.get("rating_count") or 0) if rev else None,
            "rating_source": rating_source,
            "designs": c.get("num_designs"),
            "created": (c.get("created_iso") or c.get("created") or "")[:10],
            "next_day_tag": NEXT_DAY_TAG in tag_names,
            "dispatch_days": int(dm.group(1)) if dm else None,
            "mall_verified": bool(c.get("mall_verified")),
            "assured": bool((c.get("assured_details") or {}).get("is_assured")),
            "material": _detail(details, "Material"),
            "is_ad": bool(c.get("isAdProduct")),
            "retrieval": meta.get("sub_source") or meta.get("source") or "",
        })
    if not out:
        raise InsightsError("Response me koi catalog nahi mila.")
    return out


# ─── STATS ────────────────────────────────────────────────────────────────────

def _pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo = int(math.floor(k))
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def _title_terms(titles, n_listings):
    min_count = max(2, math.ceil(0.1 * n_listings))
    words, phrases = Counter(), Counter()
    for t in titles:
        toks = re.findall(r"[a-z]+", t.lower())
        keep = [w for w in toks if len(w) > 2 and w not in STOPWORDS]
        words.update(set(keep))
        pairs = {f"{a} {b}" for a, b in zip(toks, toks[1:])
                 if len(a) > 2 and len(b) > 2 and a not in STOPWORDS and b not in STOPWORDS}
        phrases.update(pairs)
    top_w = [(w, c) for w, c in words.most_common(30) if c >= min_count][:12]
    top_p = [(p, c) for p, c in phrases.most_common(30) if c >= min_count][:8]
    return top_w, top_p


def compute_stats(listings, today=None):
    """Aggregate a list of parsed listings. Returns a JSON-serialisable dict."""
    n = len(listings)
    if not n:
        return None
    today = today or date.today()

    prices = [l["price"] for l in listings if l.get("price")]
    eff = [l["effective_price"] for l in listings if l.get("effective_price")]
    ratings = [l["rating"] for l in listings if l.get("rating")]
    counts = [l["rating_count"] for l in listings
              if l.get("rating_source") == "catalog" and l.get("rating_count") is not None]
    designs = [l["designs"] for l in listings if l.get("designs")]
    tagged = [l for l in listings if l.get("next_day_tag")]
    one_day = [l for l in listings if l.get("dispatch_days") == 1]

    new_count = 0
    for l in listings:
        try:
            if (today - date.fromisoformat(l["created"])).days <= 365:
                new_count += 1
        except (ValueError, KeyError, TypeError):
            pass

    words, phrases = _title_terms([l.get("title", "") for l in listings], n)
    materials = Counter(l["material"] for l in listings if l.get("material"))

    def share(k):
        return round(100 * k / n)

    return {
        "n": n,
        "price": {k: _pct(prices, p) for k, p in
                  (("min", 0), ("p10", 10), ("p25", 25), ("median", 50),
                   ("p75", 75), ("p90", 90), ("max", 100))},
        "effective_price_median": _pct(eff, 50),
        "rating": {
            "min": min(ratings) if ratings else None,
            "median": _pct(ratings, 50),
            "share_4plus": round(100 * sum(r >= 4.0 for r in ratings) / len(ratings)) if ratings else None,
        },
        "rating_count": {
            "median": _pct(counts, 50),
            "share_under_1000": round(100 * sum(c < 1000 for c in counts) / len(counts)) if counts else None,
        },
        "designs": {
            "share_2plus": round(100 * sum(d >= 2 for d in designs) / len(designs)) if designs else None,
            "max": max(designs) if designs else None,
        },
        "dispatch": {
            "tag_share": share(len(tagged)),
            "one_day_n": len(one_day),
            "one_day_tagged": sum(1 for l in one_day if l.get("next_day_tag")),
        },
        "new_share": share(new_count),
        "top_words": words,
        "top_phrases": phrases,
        "top_materials": materials.most_common(5),
    }


def get_price_band(stats, min_n=MIN_LISTINGS_FOR_BAND):
    """Price band for QC, or None if there is too little data."""
    if not stats or stats["n"] < min_n or not stats["price"].get("p10"):
        return None
    return {"low": stats["price"]["p10"], "high": stats["price"]["p90"],
            "median": stats["price"]["median"], "n": stats["n"]}


def suggested_title_words(stats, restricted=(), limit=8):
    """Common title words, minus anything in the restricted keyword list."""
    if not stats:
        return []
    bad = [r.lower() for r in restricted]
    out = []
    for w, _ in stats.get("top_words", []):
        if any(w == b or w in b.split() for b in bad):
            continue
        out.append(w)
    return out[:limit]


# ─── STORAGE (Supabase first, local file fallback) ────────────────────────────

def normalize_label(label):
    return re.sub(r"\s+", " ", (label or "").strip().lower())


def _local_load():
    if os.path.exists(LOCAL_FILE):
        try:
            with open(LOCAL_FILE, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _local_save(data):
    with open(LOCAL_FILE, "w") as f:
        json.dump(data, f, indent=1)


def save_snapshot(label, listings, source=""):
    """Save one parsed response. Returns 'cloud' or 'local'."""
    label = normalize_label(label)
    if not label:
        raise InsightsError("Label daalo (jaise 'girls sliders').")
    client = database.get_supabase_client()
    if client and database.save_market_snapshot(client, label, listings, source):
        return "cloud"
    data = _local_load()
    data.setdefault(label, []).append({
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "listings": listings,
    })
    _local_save(data)
    return "local"


def load_snapshots(label):
    label = normalize_label(label)
    snaps = []
    client = database.get_supabase_client()
    if client:
        snaps += database.load_market_snapshots(client, label)
    snaps += _local_load().get(label, [])
    return snaps


def list_labels():
    labels = set(_local_load().keys())
    client = database.get_supabase_client()
    if client:
        labels |= set(database.list_market_labels(client))
    return sorted(labels)


def merge_listings(snapshots):
    """One entry per catalog id. The most recent snapshot wins."""
    merged = {}
    for snap in sorted(snapshots, key=lambda s: str(s.get("captured_at", ""))):
        for l in snap.get("listings", []):
            key = l.get("id") or l.get("title")
            merged[key] = l
    return list(merged.values())


def get_stats(label):
    snaps = load_snapshots(label)
    listings = merge_listings(snaps)
    stats = compute_stats(listings)
    if stats:
        stats["label"] = normalize_label(label)
        stats["snapshots"] = len(snaps)
    return stats
