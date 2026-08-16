"""Platform detection, field aliases, and keyword scrubbing."""

import re

MEESHO_RESTRICTED_KEYWORDS = [
    "comfort", "comfortable", "EVA", "everyday", "daily wear",
    "best quality", "premium quality", "high quality", "top quality",
    "Amazon", "Flipkart", "Myntra", "Ajio", "elegant",
]
FLIPKART_RESTRICTED_KEYWORDS = [
    "best quality", "premium quality", "high quality", "top quality",
    "Amazon", "Myntra", "Ajio", "Meesho",
]
RESTRICTED_KEYWORDS = MEESHO_RESTRICTED_KEYWORDS

SKIP_FIELDS = {"ERROR STATUS", "ERROR MESSAGE"}
PRICE_FIELDS = {
    "Meesho Price", "Wrong/Defective Returns Price", "Selling Price",
}
NUMERIC_FIELDS = {
    "HSN ID", "GST %", "GST Rate", "Net Weight (gms)", "Inventory",
    "Net Quantity (N)", "MRP", "Meesho Price", "Wrong/Defective Returns Price",
    "Selling Price", "Manufacturer Pincode", "Packer Pincode", "Importer Pincode",
}

# Internal role -> candidate Excel headers (first match in col_map wins)
PLATFORM_ALIASES = {
    "Meesho": {
        "product_name": ["Product Name"],
        "sku": ["SKU ID"],
        "style_id": ["Product ID / Style ID"],
        "price": ["Meesho Price"],
        "wd_price": ["Wrong/Defective Returns Price"],
        "variation": ["Variation", "Size"],
        "group_id": ["Group ID"],
        "description": ["Product Description"],
        "brand": ["Brand Name", "Brand"],
        "color": ["Color"],
        "image1": ["Image 1 (Front)", "Image 1", "Main Image"],
        "image2": ["Image 2"],
        "image3": ["Image 3"],
        "image4": ["Image 4"],
        "mrp": ["MRP"],
        "fabric": ["Fabric", "Material"],
        "occasion": ["Occasion"],
    },
    "Flipkart": {
        "product_name": ["Product Name", "Product Title"],
        "sku": ["Seller SKU ID", "SKU ID", "Seller SKU"],
        "style_id": ["Group ID / Style Code", "Style Code", "FSN"],
        "price": ["Selling Price", "Price"],
        "wd_price": [],
        "variation": ["Size", "Variation"],
        "group_id": ["Group ID", "Group ID / Style Code"],
        "description": ["Key Features", "Description", "Product Description"],
        "brand": ["Brand", "Brand Name"],
        "color": ["Color", "Colour"],
        "image1": ["Main Image URL", "Main Image", "Image 1", "Image URL 1"],
        "image2": ["Image URL 2", "Image 2", "Other Image URL 1"],
        "image3": ["Image URL 3", "Image 3", "Other Image URL 2"],
        "image4": ["Image URL 4", "Image 4", "Other Image URL 3"],
        "mrp": ["MRP", "Maximum Retail Price"],
        "fabric": ["Material", "Fabric"],
        "occasion": ["Occasion"],
    },
}

MEESHO_DETECT_HEADERS = {
    "Meesho Price", "Product ID / Style ID", "Wrong/Defective Returns Price",
}
FLIPKART_DETECT_HEADERS = {
    "Seller SKU ID", "Group ID / Style Code", "Selling Price", "Key Features",
}


def detect_platform(col_map):
    """Detect marketplace from uploaded template headers."""
    headers = set(col_map.keys())
    meesho_hits = len(headers & MEESHO_DETECT_HEADERS)
    flipkart_hits = len(headers & FLIPKART_DETECT_HEADERS)
    if flipkart_hits > meesho_hits:
        return "Flipkart"
    if meesho_hits > 0:
        return "Meesho"
    if flipkart_hits > 0:
        return "Flipkart"
    return "Meesho"


def _pick_header(col_map, candidates):
    for name in candidates:
        if name in col_map:
            return name
    lower_map = {k.lower(): k for k in col_map}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def resolve_fields(col_map, platform):
    """Map internal roles to concrete header names present in the template."""
    aliases = PLATFORM_ALIASES.get(platform, PLATFORM_ALIASES["Meesho"])
    resolved = {}
    for role, candidates in aliases.items():
        picked = _pick_header(col_map, candidates)
        if picked:
            resolved[role] = picked
    if "image1" not in resolved:
        for h in col_map:
            hl = h.lower()
            if "image" in hl and "2" not in hl and "3" not in hl and "4" not in hl:
                resolved["image1"] = h
                break
    return resolved


def programmatic_field_set(fields):
    """Headers filled programmatically (not shown as free-form inputs)."""
    roles = (
        "product_name", "sku", "style_id", "group_id", "brand", "color",
        "variation", "image1", "image2", "image3", "image4",
    )
    return {fields[r] for r in roles if r in fields}


def auto_field_set(fields):
    roles = ("product_name", "sku", "style_id")
    return {fields[r] for r in roles if r in fields}


def restricted_keywords_for(platform):
    if platform == "Flipkart":
        return FLIPKART_RESTRICTED_KEYWORDS
    return MEESHO_RESTRICTED_KEYWORDS


def scrub_restricted(text, platform):
    if not text:
        return text
    cleaned = text
    for kw in restricted_keywords_for(platform):
        cleaned = re.sub(r"\b" + re.escape(kw) + r"\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def detection_uncertain(col_map):
    """True when neither Meesho nor Flipkart marker headers are present."""
    headers = set(col_map.keys())
    return not (headers & MEESHO_DETECT_HEADERS) and not (headers & FLIPKART_DETECT_HEADERS)
