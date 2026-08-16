"""
Platform QC Pre-Check Module
Validates generated data BEFORE upload. Meesho and Flipkart aware.
"""

from platform_config import (
    MEESHO_RESTRICTED_KEYWORDS,
    FLIPKART_RESTRICTED_KEYWORDS,
)

# Back-compat export
RESTRICTED_KEYWORDS = MEESHO_RESTRICTED_KEYWORDS

WARNING_KEYWORDS = [
    "Premium", "Exclusive", "Designer", "Luxury",
]


def _f(fields, role, default=None):
    if fields and role in fields:
        return fields[role]
    return default


def run_qc_check(rows, col_map, dropdowns=None, platform="Meesho", fields=None):
    """
    Run platform QC checks on generated rows.
    fields: dict of role -> concrete header name from resolve_fields().
    Returns: (errors, warnings)
    """
    errors = []
    warnings = []
    fields = fields or {}

    product_name = _f(fields, "product_name", "Product Name")
    variation = _f(fields, "variation", "Variation" if platform == "Meesho" else "Size")
    sku = _f(fields, "sku", "SKU ID" if platform == "Meesho" else "Seller SKU ID")
    style_id = _f(
        fields, "style_id",
        "Product ID / Style ID" if platform == "Meesho" else "Group ID / Style Code",
    )
    group_id = _f(fields, "group_id", "Group ID")
    brand = _f(fields, "brand", "Brand Name" if platform == "Meesho" else "Brand")
    description = _f(
        fields, "description",
        "Product Description" if platform == "Meesho" else "Key Features",
    )
    price = _f(fields, "price", "Meesho Price" if platform == "Meesho" else "Selling Price")
    wd_price = _f(fields, "wd_price", "Wrong/Defective Returns Price")
    mrp = _f(fields, "mrp", "MRP")
    image_fields = [
        _f(fields, "image1"),
        _f(fields, "image2"),
        _f(fields, "image3"),
        _f(fields, "image4"),
    ]
    image_fields = [i for i in image_fields if i]

    if not rows:
        errors.append({
            "row": 0, "field": "-", "error_type": "CRITICAL",
            "message": "No rows generated",
        })
        return errors, warnings

    groups = {}
    for i, row in enumerate(rows):
        gid = row.get(group_id, row.get(style_id, "?"))
        groups.setdefault(gid, []).append((i, row))

    for gid, group_rows in groups.items():
        names = set(r.get(product_name, "") for _, r in group_rows)
        if len(names) > 1:
            errors.append({
                "row": group_rows[0][0] + 1,
                "field": product_name,
                "error_type": "ERROR",
                "message": (
                    f"Group {gid}: Different product names in same group "
                    f"({len(names)} unique)"
                ),
            })

    for gid, group_rows in groups.items():
        variations = [r.get(variation, "") for _, r in group_rows]
        if len(variations) != len(set(variations)):
            dupes = [v for v in set(variations) if variations.count(v) > 1]
            errors.append({
                "row": group_rows[0][0] + 1,
                "field": variation,
                "error_type": "ERROR",
                "message": f"Group {gid}: Same variation/size repeated — {dupes}",
            })

    variant_fields = {variation, sku}
    variant_fields.update(image_fields)
    for gid, group_rows in groups.items():
        if len(group_rows) < 2:
            continue
        base_row = group_rows[0][1]
        for idx, row in group_rows[1:]:
            for field in row:
                if field in variant_fields:
                    continue
                if row.get(field) != base_row.get(field):
                    errors.append({
                        "row": idx + 1,
                        "field": field,
                        "error_type": "ERROR",
                        "message": (
                            f"Group {gid}: '{field}' differs between rows "
                            f"('{base_row.get(field)}' vs '{row.get(field)}')"
                        ),
                    })
                    break

    banned = (
        MEESHO_RESTRICTED_KEYWORDS if platform == "Meesho"
        else FLIPKART_RESTRICTED_KEYWORDS
    )
    apply_keyword_qc = platform == "Meesho"
    for i, row in enumerate(rows):
        name = row.get(product_name, "") or ""
        if apply_keyword_qc:
            for kw in banned:
                if kw.lower() in name.lower():
                    errors.append({
                        "row": i + 1,
                        "field": product_name,
                        "error_type": "ERROR",
                        "message": f"Restricted keyword '{kw}' found in title",
                    })
            for kw in WARNING_KEYWORDS:
                if kw.lower() in name.lower():
                    warnings.append({
                        "row": i + 1,
                        "field": product_name,
                        "error_type": "WARNING",
                        "message": (
                            f"Warning keyword '{kw}' in title — "
                            "may flag on some categories"
                        ),
                    })
            desc = row.get(description, "") or ""
            if desc:
                for kw in banned:
                    if kw.lower() in desc.lower():
                        errors.append({
                            "row": i + 1,
                            "field": description,
                            "error_type": "ERROR",
                            "message": f"Restricted keyword '{kw}' found in description",
                        })
                        break
        else:
            for kw in banned:
                if kw.lower() in name.lower():
                    warnings.append({
                        "row": i + 1,
                        "field": product_name,
                        "error_type": "WARNING",
                        "message": f"Competitor/quality claim '{kw}' in title",
                    })

    for i, row in enumerate(rows):
        mp = row.get(price) if price else None
        wrp = row.get(wd_price) if wd_price else None
        mrp_val = row.get(mrp) if mrp else None

        if mp and mrp_val:
            try:
                if float(mp) >= float(mrp_val):
                    errors.append({
                        "row": i + 1,
                        "field": price,
                        "error_type": "ERROR",
                        "message": f"{price} (₹{mp}) must be less than MRP (₹{mrp_val})",
                    })
            except (ValueError, TypeError):
                pass

        if platform == "Meesho" and mp and wrp:
            try:
                if float(wrp) >= float(mp):
                    errors.append({
                        "row": i + 1,
                        "field": wd_price,
                        "error_type": "ERROR",
                        "message": f"W/D Price (₹{wrp}) must be less than {price} (₹{mp})",
                    })
            except (ValueError, TypeError):
                pass

    critical = [product_name, variation, brand]
    if image_fields:
        critical.append(image_fields[0])
    if sku:
        critical.append(sku)
    for i, row in enumerate(rows):
        for field in critical:
            if field and field in col_map and not row.get(field):
                errors.append({
                    "row": i + 1,
                    "field": field,
                    "error_type": "ERROR",
                    "message": f"Required field '{field}' is empty",
                })

    if dropdowns:
        for i, row in enumerate(rows):
            for field, valid_values in dropdowns.items():
                if field in row and row[field]:
                    val = str(row[field]).strip()
                    if val and val not in valid_values and i == 0:
                        warnings.append({
                            "row": i + 1,
                            "field": field,
                            "error_type": "WARNING",
                            "message": f"'{val}' not in template dropdown for '{field}'",
                        })

    for i, row in enumerate(rows):
        for img_field in image_fields:
            url = row.get(img_field, "")
            if not url:
                continue
            if platform == "Meesho" and "drive.google.com" in url:
                errors.append({
                    "row": i + 1,
                    "field": img_field,
                    "error_type": "ERROR",
                    "message": "Google Drive links not allowed — use Meesho image uploader",
                })
            elif not str(url).startswith("http"):
                errors.append({
                    "row": i + 1,
                    "field": img_field,
                    "error_type": "ERROR",
                    "message": "Invalid image URL format",
                })

    for i, row in enumerate(rows):
        name = row.get(product_name, "") or ""
        if len(name) > 200:
            warnings.append({
                "row": i + 1,
                "field": product_name,
                "error_type": "WARNING",
                "message": (
                    f"Title too long ({len(name)} chars) — "
                    "keep under 100 for best results"
                ),
            })

    return errors, warnings
