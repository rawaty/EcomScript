"""
Meesho QC Pre-Check Module
Validates generated data BEFORE upload to catch errors early.
"""

# Meesho restricted/warning keywords
RESTRICTED_KEYWORDS = [
    'comfort', 'comfortable', 'EVA', 'everyday', 'daily wear',
    'best quality', 'premium quality', 'high quality', 'top quality',
    'Amazon', 'Flipkart', 'Myntra', 'Ajio', 'elegant',
]

WARNING_KEYWORDS = [
    'Premium', 'Exclusive', 'Designer', 'Luxury',
]


def run_qc_check(rows, col_map, dropdowns=None):
    """
    Run Meesho QC checks on generated rows.
    Returns: list of dicts with {row, field, error_type, message}
    """
    errors = []
    warnings = []

    if not rows:
        errors.append({"row": 0, "field": "-", "error_type": "CRITICAL",
                       "message": "No rows generated"})
        return errors, warnings

    # Group rows by Group ID
    groups = {}
    for i, row in enumerate(rows):
        gid = row.get('Group ID', '?')
        if gid not in groups:
            groups[gid] = []
        groups[gid].append((i, row))

    # ─── Check 1: Same Product Name within Group ──────────────────────
    for gid, group_rows in groups.items():
        names = set(r.get('Product Name', '') for _, r in group_rows)
        if len(names) > 1:
            errors.append({
                "row": group_rows[0][0] + 1,
                "field": "Product Name",
                "error_type": "ERROR",
                "message": f"Group {gid}: Different Product Names in same group ({len(names)} unique)"
            })

    # ─── Check 2: Unique Variation within Group ───────────────────────
    for gid, group_rows in groups.items():
        variations = [r.get('Variation', '') for _, r in group_rows]
        if len(variations) != len(set(variations)):
            dupes = [v for v in set(variations) if variations.count(v) > 1]
            errors.append({
                "row": group_rows[0][0] + 1,
                "field": "Variation",
                "error_type": "ERROR",
                "message": f"Group {gid}: Same variation repeated — {dupes}"
            })

    # ─── Check 3: Same Attributes within Group ────────────────────────
    # Fields that must be identical within a group (except Variation, SKU, Style ID, Color)
    VARIANT_FIELDS = {'Variation', 'SKU ID',
                      'Image 1 (Front)', 'Image 2', 'Image 3', 'Image 4'}
    for gid, group_rows in groups.items():
        if len(group_rows) < 2:
            continue
        base_row = group_rows[0][1]
        for idx, row in group_rows[1:]:
            for field in row:
                if field in VARIANT_FIELDS:
                    continue
                if row.get(field) != base_row.get(field):
                    errors.append({
                        "row": idx + 1,
                        "field": field,
                        "error_type": "ERROR",
                        "message": f"Group {gid}: '{field}' differs between rows "
                                   f"('{base_row.get(field)}' vs '{row.get(field)}')"
                    })
                    break  # One error per group is enough

    # ─── Check 4: Restricted Keywords in Product Name ─────────────────
    for i, row in enumerate(rows):
        name = row.get('Product Name', '')
        for kw in RESTRICTED_KEYWORDS:
            if kw.lower() in name.lower():
                errors.append({
                    "row": i + 1,
                    "field": "Product Name",
                    "error_type": "ERROR",
                    "message": f"Restricted keyword '{kw}' found in title"
                })
        for kw in WARNING_KEYWORDS:
            if kw.lower() in name.lower():
                warnings.append({
                    "row": i + 1,
                    "field": "Product Name",
                    "error_type": "WARNING",
                    "message": f"Warning keyword '{kw}' in title — may flag on some categories"
                })

        # Check description too
        desc = row.get('Product Description', '')
        if desc:
            for kw in RESTRICTED_KEYWORDS:
                if kw.lower() in desc.lower():
                    errors.append({
                        "row": i + 1,
                        "field": "Product Description",
                        "error_type": "ERROR",
                        "message": f"Restricted keyword '{kw}' found in description"
                    })
                    break  # One error per row enough

    # ─── Check 5: Price Rules ─────────────────────────────────────────
    for i, row in enumerate(rows):
        mp = row.get('Meesho Price')
        wrp = row.get('Wrong/Defective Returns Price')
        mrp = row.get('MRP')

        if mp and mrp:
            try:
                if float(mp) >= float(mrp):
                    errors.append({
                        "row": i + 1,
                        "field": "Meesho Price",
                        "error_type": "ERROR",
                        "message": f"Meesho Price (₹{mp}) must be less than MRP (₹{mrp})"
                    })
            except (ValueError, TypeError):
                pass

        if mp and wrp:
            try:
                if float(wrp) >= float(mp):
                    errors.append({
                        "row": i + 1,
                        "field": "Wrong/Defective Returns Price",
                        "error_type": "ERROR",
                        "message": f"W/D Price (₹{wrp}) must be less than Meesho Price (₹{mp})"
                    })
            except (ValueError, TypeError):
                pass

    # ─── Check 6: Missing Compulsory Fields ───────────────────────────
    CRITICAL_FIELDS = ['Product Name', 'Variation', 'Brand Name', 'Image 1 (Front)']
    for i, row in enumerate(rows):
        for field in CRITICAL_FIELDS:
            if field in col_map and not row.get(field):
                errors.append({
                    "row": i + 1,
                    "field": field,
                    "error_type": "ERROR",
                    "message": f"Required field '{field}' is empty"
                })

    # ─── Check 7: Dropdown Validation ─────────────────────────────────
    if dropdowns:
        for i, row in enumerate(rows):
            for field, valid_values in dropdowns.items():
                if field in row and row[field]:
                    val = str(row[field]).strip()
                    if val and val not in valid_values:
                        # Only warn for first occurrence
                        if i == 0:
                            warnings.append({
                                "row": i + 1,
                                "field": field,
                                "error_type": "WARNING",
                                "message": f"'{val}' not in template dropdown for '{field}'"
                            })

    # ─── Check 8: Image URL Format ────────────────────────────────────
    for i, row in enumerate(rows):
        for img_field in ['Image 1 (Front)', 'Image 2', 'Image 3', 'Image 4']:
            url = row.get(img_field, '')
            if url:
                if 'drive.google.com' in url:
                    errors.append({
                        "row": i + 1,
                        "field": img_field,
                        "error_type": "ERROR",
                        "message": "Google Drive links not allowed — use Meesho image uploader"
                    })
                elif not url.startswith('http'):
                    errors.append({
                        "row": i + 1,
                        "field": img_field,
                        "error_type": "ERROR",
                        "message": f"Invalid image URL format"
                    })

    # ─── Check 9: Product Name length ─────────────────────────────────
    for i, row in enumerate(rows):
        name = row.get('Product Name', '')
        if len(name) > 200:
            warnings.append({
                "row": i + 1,
                "field": "Product Name",
                "error_type": "WARNING",
                "message": f"Title too long ({len(name)} chars) — keep under 100 for best results"
            })

    return errors, warnings
