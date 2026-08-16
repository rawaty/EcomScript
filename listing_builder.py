"""Listing row generation helpers (platform-aware)."""

import os
import random
import string

from platform_config import PRICE_FIELDS, scrub_restricted
from ai_helper import ai_generate_titles, ai_generate_description

SEO_ADJECTIVES = [
    "Stylish", "Trendy", "Designer", "Exclusive",
    "Beautiful", "Attractive", "Latest", "Fashionable",
    "Traditional", "Modern", "Classic", "New Launched",
]
SEO_FEATURES = [
    "Embroidered", "Printed", "Self Design", "Solid", "Woven",
    "Block Print", "Bandhani", "Tie Dye", "Floral", "Checked",
    "Striped", "Geometric", "Abstract", "Ethnic Motif", "Colorblocked",
]
SEO_OCCASIONS = [
    "Ethnic Wear", "Party Wear", "Casual Wear",
    "Festive Wear", "Wedding Wear", "Festival Collection",
]

FOOT_LENGTH_MAP = {
    "IND-2": "21", "IND-3": "21.5", "IND-4": "22", "IND-5": "23",
    "IND-6": "24", "IND-7": "25", "IND-8": "26", "IND-9": "27",
    "IND-10": "28", "IND-11": "29", "IND-12": "30", "IND-13": "30",
}
FOOT_WIDTH_MAP = {
    "IND-2": "8", "IND-3": "8.5", "IND-4": "9", "IND-5": "9.5",
    "IND-6": "10", "IND-7": "10.2", "IND-8": "10.4", "IND-9": "10.6",
    "IND-10": "10.8", "IND-11": "11", "IND-12": "11.2", "IND-13": "11.4",
}


def gen_sku(base, i):
    return f"{base}_{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}{i + 1}"


def gen_title(brand, cat, color, occasion="", audience="for Kids", platform="Meesho"):
    adj = random.choice(SEO_ADJECTIVES)
    feat = random.choice(SEO_FEATURES)
    if occasion and occasion.strip():
        occ_val = occasion.strip()
        if not any(occ_val.lower().endswith(s) for s in ["wear", "collection"]):
            occ_val = f"{occ_val.title()} Wear"
        else:
            occ_val = occ_val.title()
        occ = occ_val
    else:
        occ = random.choice(SEO_OCCASIONS)
    t = random.choice([
        f"{brand} {adj} {color} {cat} {feat} {occ} {audience}",
        f"{brand} {color} {cat} {adj} {feat} {occ} {audience}",
        f"{adj} {brand} {color} {cat} {occ} {feat} {audience}",
        f"{brand} {color} {cat} {adj} {feat} {audience} {occ}",
    ])
    return scrub_restricted(t, platform)


def vary_price(base, variation):
    if variation <= 0:
        return base
    return max(1.0, round(base + random.randint(-variation, variation), 2))


def build_listing_rows(
    *,
    platform,
    resolved,
    col_map,
    programmatic_fields,
    brand,
    style_code,
    category,
    colors,
    sizes,
    audience,
    fv,
    count,
    price_var,
    mrp_val,
    img_url_lists,
    use_ai_titles=False,
    use_ai_desc=False,
    gemini_key="",
    desc_cache=None,
):
    """
    Build Color x Size listing rows keyed by resolved template headers.
    desc_cache: mutable dict used to store AI descriptions across sizes.
    Returns (rows, actual_per_catalog, max_per_catalog).
    """
    if desc_cache is None:
        desc_cache = {}

    occasion_key = resolved.get("occasion") or "Occasion"
    fabric_key = resolved.get("fabric") or "Fabric"
    f_product = resolved.get("product_name")
    f_sku = resolved.get("sku")
    f_style = resolved.get("style_id")
    f_group = resolved.get("group_id")
    f_brand = resolved.get("brand")
    f_var = resolved.get("variation")
    f_color = resolved.get("color")
    f_price = resolved.get("price")
    f_wd = resolved.get("wd_price")
    f_desc = resolved.get("description")
    f_mrp = resolved.get("mrp", "MRP")
    img_keys = [resolved.get(k) for k in ("image1", "image2", "image3", "image4")]

    max_per_catalog = len(colors) * len(sizes) if colors and sizes else 0
    actual_per_catalog = min(int(count), max_per_catalog) if max_per_catalog else 0

    rows = []
    row_idx = 0
    catalog_categories = [category.strip()]

    for cat_idx, cat_name in enumerate(catalog_categories):
        catalog_style = (
            f"{style_code.strip()}-C{cat_idx + 1}" if cat_idx > 0 else style_code.strip()
        )
        batch_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))

        color_style_ids = {
            color: f"{catalog_style}-{color[:3].upper()}{batch_id}{ci + 1}"
            for ci, color in enumerate(colors)
        }

        color_titles = {}
        if use_ai_titles and gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
            ai_titles = ai_generate_titles(
                brand.strip(), cat_name, colors,
                str(fv.get(occasion_key, "Casual Wear")), audience,
                platform=platform,
            )
            if ai_titles:
                for color in colors:
                    color_titles[color] = ai_titles.get(color, "")
        for color in colors:
            if not color_titles.get(color):
                color_titles[color] = gen_title(
                    brand.strip(), cat_name, color,
                    occasion=str(fv.get(occasion_key, "")),
                    audience=audience,
                    platform=platform,
                )

        catalog_row_count = 0
        for ci, color in enumerate(colors):
            for si, size in enumerate(sizes):
                if catalog_row_count >= actual_per_catalog:
                    break
                row = {}
                if f_product:
                    row[f_product] = color_titles[color]
                if f_sku:
                    row[f_sku] = gen_sku(catalog_style, row_idx)
                if f_style:
                    row[f_style] = color_style_ids[color]
                if f_brand:
                    row[f_brand] = brand.strip()
                if f_var:
                    row[f_var] = size
                if f_group:
                    if platform == "Flipkart" and f_group == f_style:
                        row[f_group] = color_style_ids[color]
                    else:
                        row[f_group] = str(cat_idx * len(colors) + ci + 1)

                for f, v in fv.items():
                    val = str(v).strip()
                    if not val or f in programmatic_fields:
                        continue
                    if f_price and f == f_price:
                        try:
                            mp = float(val)
                            if price_var > 0:
                                mp = vary_price(mp, price_var)
                            row[f_price] = mp
                            if f_wd and f_wd in col_map:
                                row[f_wd] = round(mp - 1, 2)
                        except ValueError:
                            row[f] = val
                    elif f_wd and f == f_wd:
                        pass
                    elif f in PRICE_FIELDS and price_var > 0:
                        try:
                            row[f] = vary_price(float(val), price_var)
                        except ValueError:
                            row[f] = val
                    else:
                        row[f] = val

                if mrp_val.strip() and f_mrp in col_map:
                    row[f_mrp] = mrp_val.strip()

                for img_key, urls in zip(img_keys, img_url_lists):
                    if img_key and urls:
                        row[img_key] = urls[row_idx % len(urls)]

                if size in FOOT_LENGTH_MAP and "Foot Length Size" in col_map:
                    row["Foot Length Size"] = FOOT_LENGTH_MAP[size]
                if size in FOOT_WIDTH_MAP and "Foot Width Size" in col_map:
                    row["Foot Width Size"] = FOOT_WIDTH_MAP[size]

                if f_color and f_color in col_map:
                    row[f_color] = color

                cache_key = f"desc_{cat_idx}_{ci}"
                if use_ai_desc and gemini_key and f_desc and f_desc in col_map and si == 0:
                    os.environ["GEMINI_API_KEY"] = gemini_key
                    desc = ai_generate_description(
                        brand.strip(), cat_name, color,
                        str(fv.get(fabric_key, "")), str(fv.get(occasion_key, "")),
                        audience, platform=platform,
                    )
                    if desc:
                        desc_cache[cache_key] = desc
                if f_desc and cache_key in desc_cache:
                    row[f_desc] = scrub_restricted(desc_cache[cache_key], platform)

                rows.append(row)
                row_idx += 1
                catalog_row_count += 1
            if catalog_row_count >= actual_per_catalog:
                break

    return rows, actual_per_catalog, max_per_catalog
