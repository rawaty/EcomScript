"""
Database Module — Supabase Cloud Integration
Stores all generated listings to prevent duplicates across uploads.
"""

import os
from datetime import datetime

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


def get_supabase_client():
    """Get Supabase client. Returns None if not configured."""
    if not SUPABASE_AVAILABLE:
        return None
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def init_database(client):
    """
    Initialize database tables via Supabase.
    NOTE: Tables must be created via Supabase Dashboard SQL Editor.
    Run this SQL in Supabase Dashboard → SQL Editor:

    CREATE TABLE IF NOT EXISTS listings (
        id BIGSERIAL PRIMARY KEY,
        style_id TEXT NOT NULL,
        sku_id TEXT NOT NULL,
        product_name TEXT,
        brand TEXT,
        color TEXT,
        category TEXT,
        image_urls TEXT[],
        catalog_name TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        status TEXT DEFAULT 'active'
    );

    CREATE INDEX idx_style_id ON listings(style_id);
    CREATE INDEX idx_sku_id ON listings(sku_id);
    CREATE INDEX idx_image_urls ON listings USING GIN(image_urls);
    """
    pass  # Tables created via Supabase Dashboard


def check_duplicates(client, style_ids=None, sku_ids=None, image_urls=None):
    """
    Check if any Style IDs, SKU IDs, or Image URLs already exist.
    Returns dict with duplicate info.
    """
    if not client:
        return {"style_ids": [], "sku_ids": [], "image_urls": []}

    result = {"style_ids": [], "sku_ids": [], "image_urls": []}

    try:
        # Check Style IDs
        if style_ids:
            resp = client.table("listings").select("style_id").in_("style_id", list(style_ids)).execute()
            result["style_ids"] = [r["style_id"] for r in resp.data]

        # Check SKU IDs
        if sku_ids:
            resp = client.table("listings").select("sku_id").in_("sku_id", list(sku_ids)).execute()
            result["sku_ids"] = [r["sku_id"] for r in resp.data]

        # Check Image URLs
        if image_urls:
            # Check each URL against stored arrays
            for url in image_urls:
                resp = client.table("listings").select("id, style_id").contains("image_urls", [url]).execute()
                if resp.data:
                    result["image_urls"].append(url)

    except Exception as e:
        print(f"Database check error: {e}")

    return result


def save_listings(client, rows, catalog_name="", fields=None):
    """
    Save generated listings to database for future duplicate checking.
    fields: optional role -> header map from resolve_fields().
    """
    if not client:
        return False

    fields = fields or {}
    style_key = fields.get("style_id", "Product ID / Style ID")
    sku_key = fields.get("sku", "SKU ID")
    name_key = fields.get("product_name", "Product Name")
    brand_key = fields.get("brand", "Brand Name")
    color_key = fields.get("color", "Color")
    image_keys = [
        fields.get("image1", "Image 1 (Front)"),
        fields.get("image2", "Image 2"),
        fields.get("image3", "Image 3"),
        fields.get("image4", "Image 4"),
    ]

    try:
        records = []
        for row in rows:
            imgs = []
            for img_field in image_keys:
                if not img_field:
                    continue
                url = row.get(img_field, '')
                if url:
                    imgs.append(url)

            records.append({
                "style_id": row.get(style_key, ""),
                "sku_id": row.get(sku_key, ""),
                "product_name": row.get(name_key, ""),
                "brand": row.get(brand_key, ""),
                "color": row.get(color_key, ""),
                "category": row.get("Generic Name", ""),
                "image_urls": imgs,
                "catalog_name": catalog_name,
                "status": "active",
            })

        # Batch insert (Supabase handles it)
        if records:
            client.table("listings").insert(records).execute()
        return True

    except Exception as e:
        print(f"Database save error: {e}")
        return False


def get_listing_count(client):
    """Get total number of saved listings."""
    if not client:
        return 0
    try:
        resp = client.table("listings").select("id", count="exact").execute()
        return resp.count or 0
    except Exception:
        return 0


def get_recent_listings(client, limit=20):
    """Get recent listings for display."""
    if not client:
        return []
    try:
        resp = (client.table("listings")
                .select("style_id, product_name, color, catalog_name, created_at")
                .order("created_at", desc=True)
                .limit(limit)
                .execute())
        return resp.data
    except Exception:
        return []


# ─── PROFILES (Cloud) ─────────────────────────────────────────────────────

def save_profile_cloud(client, name, data):
    """Save profile to Supabase (upsert — insert or update)."""
    if not client:
        return False
    try:
        client.table("profiles").upsert(
            {"name": name, "data": data},
            on_conflict="name"
        ).execute()
        return True
    except Exception as e:
        print(f"Profile save error: {e}")
        return False


def load_profiles_cloud(client):
    """Load all profiles from Supabase. Returns dict {name: data}."""
    if not client:
        return {}
    try:
        resp = client.table("profiles").select("name, data").execute()
        return {r["name"]: r["data"] for r in resp.data}
    except Exception:
        return {}


def delete_profile_cloud(client, name):
    """Delete a profile from Supabase."""
    if not client:
        return False
    try:
        client.table("profiles").delete().eq("name", name).execute()
        return True
    except Exception:
        return False
