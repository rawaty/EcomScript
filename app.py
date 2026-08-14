"""
🛒 Bulk Listing Generator (Meesho + Flipkart)
Clean rewrite — all Meesho rules enforced, no QC errors.
"""

import streamlit as st
import pandas as pd
import io
import re
import random
import string
import json
import os
from openpyxl import load_workbook
from dotenv import load_dotenv

load_dotenv()

from ai_helper import ai_generate_titles, ai_generate_description, ai_suggest_fields
from qc_checker import run_qc_check
from database import (get_supabase_client, check_duplicates, save_listings,
                      get_listing_count, save_profile_cloud, load_profiles_cloud)

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

PROFILES_FILE = "profiles.json"
PRESETS_FILE = "presets.json"

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

RESTRICTED_KEYWORDS = [
    'comfort', 'comfortable', 'EVA', 'everyday', 'daily wear',
    'best quality', 'premium quality', 'high quality', 'top quality',
    'Amazon', 'Flipkart', 'Myntra', 'Ajio', 'elegant',
]

SKIP_FIELDS = {'ERROR STATUS', 'ERROR MESSAGE'}
AUTO_FIELDS = {'Product Name', 'SKU ID', 'Product ID / Style ID'}
PROGRAMMATIC_FIELDS = {'Group ID', 'Color', 'Product Name', 'SKU ID',
                       'Product ID / Style ID', 'Brand Name'}
VARIATION_FIELD = 'Variation'
PRICE_FIELDS = {'Meesho Price', 'Wrong/Defective Returns Price', 'Selling Price'}
NUMERIC_FIELDS = {
    'HSN ID', 'GST %', 'Net Weight (gms)', 'Inventory',
    'Net Quantity (N)', 'MRP', 'Meesho Price', 'Wrong/Defective Returns Price',
    'Selling Price', 'Manufacturer Pincode', 'Packer Pincode', 'Importer Pincode',
}

FOOT_LENGTH_MAP = {
    'IND-2': '21', 'IND-3': '21.5', 'IND-4': '22', 'IND-5': '23',
    'IND-6': '24', 'IND-7': '25', 'IND-8': '26', 'IND-9': '27',
    'IND-10': '28', 'IND-11': '29', 'IND-12': '30', 'IND-13': '30',
}
FOOT_WIDTH_MAP = {
    'IND-2': '8', 'IND-3': '8.5', 'IND-4': '9', 'IND-5': '9.5',
    'IND-6': '10', 'IND-7': '10.2', 'IND-8': '10.4', 'IND-9': '10.6',
    'IND-10': '10.8', 'IND-11': '11', 'IND-12': '11.2', 'IND-13': '11.4',
}

DEFAULT_PRESETS = {
    "Flip Flops (Men)": {
        "Generic Name": "Flip Flops", "Material": "EVA", "Sole Material": "EVA",
        "Type": "Thong Flip-flops", "Pattern": "Solid", "Waterproof": "Yes",
        "Main Trend": "Solid/Regular", "Net Quantity (N)": "1",
        "Net Weight (gms)": "220", "GST %": "5", "HSN ID": "64022090",
    },
    "Flip Flops (Women)": {
        "Generic Name": "Flip Flops", "Material": "PU", "Sole Material": "PU",
        "Type": "Thong Flip-flops", "Pattern": "Printed", "Waterproof": "No",
        "Main Trend": "Floral", "Net Quantity (N)": "1",
        "Net Weight (gms)": "180", "GST %": "5", "HSN ID": "64022090",
    },
    "Kurta Sets (Girls)": {
        "Generic Name": "Kurtis & Kurtas", "Occasion": "Casual",
        "Sleeve Length": "Long Sleeves", "Fabric": "Cotton",
        "Pattern": "Printed", "Net Weight (gms)": "300",
        "GST %": "5", "HSN ID": "6111", "Net Quantity (N)": "1",
        "Stitch Type": "Stitched",
    },
    "Sliders (Men)": {
        "Generic Name": "Sliders", "Material": "Synthetic", "Sole Material": "Rubber",
        "Type": "Sliders", "Pattern": "Solid", "Waterproof": "No",
        "Main Trend": "Solid/Regular", "Net Quantity (N)": "1",
        "Net Weight (gms)": "250", "GST %": "5", "HSN ID": "64022090",
    },
}


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return {}

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def parse_csv(raw):
    seen, result = set(), []
    for item in raw.split(","):
        t = item.strip()
        if t and t not in seen:
            seen.add(t); result.append(t)
    return result

def parse_urls(raw):
    return [u.strip() for u in raw.strip().split('\n') if u.strip()]


# ─── EXCEL HELPERS ────────────────────────────────────────────────────────────

def find_data_sheet(wb):
    for name in wb.sheetnames:
        if 'fill' in name.lower():
            return wb[name]
    return wb[wb.sheetnames[1]] if len(wb.sheetnames) > 1 else wb[wb.sheetnames[0]]

def find_header_row(ws):
    for r in range(1, 10):
        v = ws.cell(row=r, column=1).value
        if v and 'Fields + Description' in str(v):
            return r
    for r in range(1, 10):
        for c in range(1, 60):
            v = ws.cell(row=r, column=c).value
            if v and 'Product Name' in str(v) and len(str(v)) > 30:
                return r
    for r in range(1, 10):
        v = ws.cell(row=r, column=1).value
        if v and str(v).strip() == 'Field Names':
            return r + 1
    return 3

def find_data_start(ws, hdr):
    start = hdr + 1
    for r in range(hdr + 1, hdr + 5):
        skip = False
        for c in range(1, 10):
            v = ws.cell(row=r, column=c).value
            if v and ('Tutorial' in str(v) or 'Watch' in str(v) or
                      'Validation Sheet' in str(v) or len(str(v)) > 200):
                skip = True; break
        if skip:
            start = r + 1
        else:
            break
    return start

def get_col_map(ws, hdr):
    m = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=hdr, column=c).value
        if v:
            for line in str(v).split('\n'):
                s = line.strip()
                if s and s not in ('Fields + Description:', 'Field Names',
                    'Field Type (Compulsory, Recommended, System_Use) ->'):
                    m[s] = c; break
    return m

def get_compulsory(ws, hdr, col_map):
    comp = set()
    for mr in [hdr - 1, hdr - 2]:
        if mr < 1:
            continue
        found = False
        for fn, ci in col_map.items():
            v = ws.cell(row=mr, column=ci).value
            if v and 'Compulsory' in str(v):
                comp.add(fn); found = True
        if found:
            break
    return comp

def get_dropdowns(wb, col_map):
    dd = {}
    vs = None
    for name in wb.sheetnames:
        if 'validation' in name.lower():
            vs = wb[name]; break
    if not vs:
        return dd
    vhr = 1
    for r in range(1, 5):
        v = vs.cell(row=r, column=1).value
        if v and ('Field Type' in str(v) or 'Field Names' in str(v)):
            vhr = r; break
    vcm = {}
    for c in range(1, vs.max_column + 1):
        v = vs.cell(row=vhr, column=c).value
        if v and str(v).strip() in col_map:
            vcm[str(v).strip()] = c
    ds = vhr + 1
    chk = vs.cell(row=ds, column=1).value
    if chk and 'Field Names' in str(chk):
        ds += 1
    for fn, ci in vcm.items():
        vals = []
        for r in range(ds, min(ds + 300, vs.max_row + 1)):
            v = vs.cell(row=r, column=ci).value
            if v:
                vals.append(str(v).strip())
        if vals:
            dd[fn] = vals
    return dd


# ─── GENERATION HELPERS ───────────────────────────────────────────────────────

def gen_sku(base, i):
    return f"{base}_{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}{i + 1}"

def gen_title(brand, cat, color, occasion="", audience="for Kids"):
    adj = random.choice(SEO_ADJECTIVES)
    feat = random.choice(SEO_FEATURES)
    if occasion and occasion.strip():
        occ_val = occasion.strip()
        if not any(occ_val.lower().endswith(s) for s in ['wear', 'collection']):
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
    for kw in RESTRICTED_KEYWORDS:
        t = re.sub(r'\b' + re.escape(kw) + r'\b', '', t, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', t).strip()

def vary_price(base, variation):
    if variation <= 0:
        return base
    return max(1.0, round(base + random.randint(-variation, variation), 2))

def inject_data(wb, rows):
    ws = find_data_sheet(wb)
    hdr = find_header_row(ws)
    cm = get_col_map(ws, hdr)
    start = find_data_start(ws, hdr)
    for r in range(start, start + len(rows) + 100):
        for c in range(1, ws.max_column + 1):
            ws.cell(row=r, column=c).value = None
    for i, row in enumerate(rows):
        for fn, val in row.items():
            if fn in cm:
                if fn in NUMERIC_FIELDS and val is not None and str(val).strip():
                    try:
                        num_val = float(str(val).strip())
                        ws.cell(row=start + i, column=cm[fn]).value = (
                            int(num_val) if num_val == int(num_val) else num_val)
                    except (ValueError, TypeError):
                        ws.cell(row=start + i, column=cm[fn]).value = val
                else:
                    ws.cell(row=start + i, column=cm[fn]).value = val


# ─── MAIN APP ─────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Bulk Listing Generator", layout="wide")
    st.title("🛒 Bulk Listing Generator (Meesho + Flipkart)")
    st.caption("Template upload → Dynamic form → Bulk fill → QC Check → Download")

    # ─── FILE UPLOAD ──────────────────────────────────────────────────────
    uploaded = st.file_uploader("📁 Upload your template (.xlsx)", type=["xlsx"])
    if not uploaded:
        st.info("👆 Upload a blank Meesho or Flipkart template to get started")
        return

    try:
        wb = load_workbook(uploaded, keep_vba=False)
        ws = find_data_sheet(wb)
        hdr = find_header_row(ws)
        col_map = get_col_map(ws, hdr)
        data_start = find_data_start(ws, hdr)
        compulsory = get_compulsory(ws, hdr, col_map)
        dropdowns = get_dropdowns(wb, col_map)
    except Exception as e:
        st.error(f"Error reading template: {e}")
        return

    fields = [f for f in col_map if f not in SKIP_FIELDS]
    st.success(f"✅ Sheet: '{ws.title}' | {len(fields)} fields | "
               f"{len(compulsory)} required | {len(dropdowns)} dropdowns")

    with st.expander("📋 All detected fields"):
        for f in fields:
            m = "⭐" if f in compulsory else "○"
            d = f" 🔽[{len(dropdowns[f])} opts]" if f in dropdowns else ""
            st.text(f"{m} {f}{d}")

    # ─── PROFILES & PRESETS ───────────────────────────────────────────────
    st.markdown("---")

    # ─── IMAGE ANALYSIS (AI Auto-fill) ───────────────────────────────────
    st.markdown("### 📸 Smart Fill: Upload product photo → AI auto-fills form")
    product_image = st.file_uploader("Upload product image (optional)", type=["jpg", "jpeg", "png"],
                                      key="product_img")
    if product_image and os.environ.get("GEMINI_API_KEY"):
        from ai_helper import ai_analyze_image
        import base64
        img_bytes = base64.b64encode(product_image.read()).decode()
        product_image.seek(0)  # Reset for later use

        if 'ai_analysis_done' not in st.session_state:
            # Pass dropdown values to AI so it returns only VALID options
            valid_options = {}
            for field in ['Color', 'Fabric', 'Pattern', 'Occasion', 'Sleeve Length',
                          'Fit/ Shape', 'Length', 'Neck/Collar', 'Print or Pattern Type']:
                if field in dropdowns:
                    valid_options[field] = dropdowns[field][:30]  # Max 30 per field

            with st.spinner("🤖 AI analyzing image..."):
                analysis = ai_analyze_image(img_bytes, category_hint="",
                                           valid_options=valid_options)

            if analysis:
                st.success("✅ AI detected product details!")
                st.json(analysis)
                # Auto-fill session state with detected values
                if analysis.get('color'):
                    st.session_state['ai_color'] = analysis['color']
                if analysis.get('fabric'):
                    st.session_state[f'f_Fabric'] = analysis['fabric']
                if analysis.get('pattern'):
                    st.session_state[f'f_Pattern'] = analysis['pattern']
                if analysis.get('occasion'):
                    st.session_state[f'f_Occasion'] = analysis['occasion']
                if analysis.get('category'):
                    st.session_state['ai_category'] = analysis['category']
                if analysis.get('description'):
                    desc_text = analysis['description']
                    # Remove restricted keywords from AI description
                    for kw in RESTRICTED_KEYWORDS:
                        desc_text = re.sub(r'\b' + re.escape(kw) + r'\b', '', desc_text, flags=re.IGNORECASE)
                    desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                    st.session_state['ai_description'] = desc_text
                    st.session_state['f_Product Description'] = desc_text
                if analysis.get('title_suggestion'):
                    st.session_state['ai_title'] = analysis['title_suggestion']
                st.session_state['ai_analysis_done'] = True
                st.rerun()  # Rerun to apply values to form
            else:
                st.warning("AI analysis failed — fill manually")
        else:
            # Show cached results
            st.success("✅ AI auto-filled form fields below!")
            # Show AI analysis data
            ai_data = {}
            if st.session_state.get('ai_color'): ai_data['color'] = st.session_state['ai_color']
            if st.session_state.get('f_Fabric'): ai_data['fabric'] = st.session_state['f_Fabric']
            if st.session_state.get('f_Pattern'): ai_data['pattern'] = st.session_state['f_Pattern']
            if st.session_state.get('f_Occasion'): ai_data['occasion'] = st.session_state['f_Occasion']
            if st.session_state.get('ai_category'): ai_data['category'] = st.session_state['ai_category']
            if st.session_state.get('ai_title'): ai_data['title_suggestion'] = st.session_state['ai_title']
            if st.session_state.get('ai_description'): ai_data['description'] = st.session_state['ai_description']
            with st.expander("🤖 AI Analysis Result (JSON)", expanded=True):
                st.json(ai_data)
            if st.button("🔄 Re-analyze image"):
                del st.session_state['ai_analysis_done']
                st.rerun()

    st.markdown("---")
    prof_col, preset_col = st.columns(2)
    with prof_col:
        st.markdown("**👤 Saved Profiles**")
        # Load from Supabase if available, fallback to local
        db_client_profiles = get_supabase_client()
        if db_client_profiles:
            profiles = load_profiles_cloud(db_client_profiles)
        else:
            profiles = load_json(PROFILES_FILE)
        profile_names = list(profiles.keys())
        selected_profile = st.selectbox("Load Profile", ["-- None --"] + profile_names,
                                        key="profile_select") if profile_names else "-- None --"
    with preset_col:
        st.markdown("**📦 Category Presets**")
        all_presets = {**DEFAULT_PRESETS, **load_json(PRESETS_FILE)}
        selected_preset = st.selectbox("Load Preset", ["-- None --"] + list(all_presets.keys()),
                                       key="preset_select")

    # Apply prefills
    if selected_profile != "-- None --" and selected_profile in profiles:
        for k, v in profiles[selected_profile].items():
            if k not in PROGRAMMATIC_FIELDS:
                st.session_state[f"f_{k}"] = v
    if selected_preset != "-- None --" and selected_preset in all_presets:
        for k, v in all_presets[selected_preset].items():
            if k not in PROGRAMMATIC_FIELDS:
                st.session_state[f"f_{k}"] = v

    # Clean stale programmatic keys
    for stale in [f"f_{f}" for f in PROGRAMMATIC_FIELDS]:
        st.session_state.pop(stale, None)

    if st.button("🗑️ Clear prefill"):
        for k in [k for k in st.session_state if k.startswith("f_")]:
            del st.session_state[k]
        st.rerun()

    # ─── MAIN FORM ────────────────────────────────────────────────────────
    with st.form("main_form"):
        st.markdown("### 🎨 Core Settings")
        c1, c2 = st.columns(2)
        with c1:
            color_options = dropdowns.get('Color', [])
            if color_options:
                # Pre-select AI detected color if available
                default_colors = []
                ai_color = st.session_state.get('ai_color', '')
                if ai_color and ai_color in color_options:
                    default_colors = [ai_color]
                colors_raw = ", ".join(st.multiselect("Colors *", options=color_options,
                                                      default=default_colors))
            else:
                colors_raw = st.text_input("Colors *",
                    value=st.session_state.get('ai_color', ''),
                    placeholder="Black, Blue, Red")
            brand = st.text_input("Brand Name *", placeholder="kidoready")
            category = st.text_input("Product Category *",
                value=st.session_state.get('ai_category', ''),
                placeholder="Kurtis & Kurtas")
        with c2:
            size_options = dropdowns.get(VARIATION_FIELD, [])
            if size_options:
                sizes_raw = ", ".join(st.multiselect("Sizes *", options=size_options))
            else:
                sizes_raw = st.text_input("Sizes *", placeholder="3-4 Years, 5-6 Years")
            style_code = st.text_input("Base Style Code *", placeholder="Kurti-01")
            audience = st.selectbox("Target Audience *",
                ["for Boys", "for Girls", "for Kids", "for Baby Boys",
                 "for Baby Girls", "for Men", "for Women", "Unisex"])

        # ─── AI SETTINGS ─────────────────────────────────────────────────
        st.markdown("### 🤖 AI & Database")
        ai_c1, ai_c2 = st.columns(2)
        with ai_c1:
            use_ai_titles = st.checkbox("✨ AI Titles (Gemini)")
            use_ai_desc = st.checkbox("📝 AI Descriptions")
        with ai_c2:
            use_ai_suggest = st.checkbox("💡 AI Field Suggestions")
            gemini_key = st.text_input("Gemini Key", value=os.environ.get("GEMINI_API_KEY", ""),
                                       type="password")

        # ─── PRICE & COUNT ───────────────────────────────────────────────
        st.markdown("### 💰 Price & Count")
        c3, c4, c5 = st.columns(3)
        with c3:
            count = st.number_input("Listings count", 1, 5000, 50, 10)
        with c4:
            price_var = st.number_input("Price variation (±₹)", 0, 100, 0, 5)
        with c5:
            mrp_val = st.text_input("MRP", placeholder="599")

        # ─── IMAGES ──────────────────────────────────────────────────────
        st.markdown("### 🖼️ Images (one URL per line)")
        ic1, ic2 = st.columns(2)
        with ic1:
            img1_raw = st.text_area("Image 1 (Front) *", height=80,
                placeholder="https://meesho.com/front.jpg")
            img2_raw = st.text_area("Image 2", height=80)
        with ic2:
            img3_raw = st.text_area("Image 3", height=80)
            img4_raw = st.text_area("Image 4", height=80)

        # ─── TEMPLATE FIELDS ─────────────────────────────────────────────
        st.markdown("### 📝 Template Fields")
        fv = {}
        show = [f for f in fields if f not in AUTO_FIELDS
                and f not in PROGRAMMATIC_FIELDS
                and f != VARIATION_FIELD
                and f not in ('Image 1 (Front)', 'Image 2', 'Image 3', 'Image 4')
                and f not in ('Foot Length Size', 'Foot Width Size')]
        req = [f for f in show if f in compulsory]
        opt = [f for f in show if f not in compulsory]

        if req:
            st.markdown("**⭐ Required:**")
            cols = st.columns(2)
            for i, f in enumerate(req):
                with cols[i % 2]:
                    if f in dropdowns:
                        fv[f] = st.selectbox(f"⭐ {f}", [""] + dropdowns[f], key=f"f_{f}")
                    else:
                        fv[f] = st.text_input(f"⭐ {f}", key=f"f_{f}")
        if opt:
            with st.expander(f"📎 Optional Fields ({len(opt)})"):
                cols2 = st.columns(2)
                for i, f in enumerate(opt):
                    with cols2[i % 2]:
                        if f in dropdowns:
                            fv[f] = st.selectbox(f, [""] + dropdowns[f], key=f"f_{f}")
                        else:
                            fv[f] = st.text_input(f, key=f"f_{f}")

        submitted = st.form_submit_button("🚀 Generate & Fill Template")

    # ─── SAVE PROFILE ─────────────────────────────────────────────────────
    with st.expander("💾 Save / Update Profile"):
        save_col1, save_col2, save_col3 = st.columns([3, 1, 1])
        with save_col1:
            profile_name = st.text_input("Profile name", placeholder="My Business")
        with save_col2:
            st.markdown("")
            save_btn = st.button("💾 Save")
        with save_col3:
            st.markdown("")
            update_btn = st.button("🔄 Update")

        if save_btn or update_btn:
            if profile_name.strip():
                # Save ONLY compulsory/required fields
                profile_data = {}
                for key, val in st.session_state.items():
                    if key.startswith("f_"):
                        field_name = key[2:]
                        if field_name in compulsory and str(val).strip():
                            profile_data[field_name] = str(val).strip()

                db_save = get_supabase_client()
                if db_save:
                    if save_profile_cloud(db_save, profile_name.strip(), profile_data):
                        action = "Updated" if update_btn else "Saved"
                        st.success(f"✅ Profile '{profile_name.strip()}' {action}! ({len(profile_data)} fields)")
                    else:
                        profiles_local = load_json(PROFILES_FILE)
                        profiles_local[profile_name.strip()] = profile_data
                        save_json(PROFILES_FILE, profiles_local)
                        st.warning("⚠️ Cloud failed — saved locally")
                else:
                    profiles_local = load_json(PROFILES_FILE)
                    profiles_local[profile_name.strip()] = profile_data
                    save_json(PROFILES_FILE, profiles_local)
                    st.success(f"✅ Profile '{profile_name.strip()}' saved locally!")
            else:
                st.error("Profile name daalo")

    # ─── GENERATION LOGIC ─────────────────────────────────────────────────
    if not submitted:
        return

    # Validation
    errs = []
    if not colors_raw.strip(): errs.append("Colors required")
    if not sizes_raw.strip(): errs.append("Sizes required")
    if not brand.strip(): errs.append("Brand Name required")
    if not style_code.strip(): errs.append("Style Code required")
    if not category.strip(): errs.append("Product Category required")
    # Check template compulsory fields
    for f in fv:
        if f in compulsory and not str(fv[f]).strip():
            errs.append(f"⭐ '{f}' is required")
    if errs:
        for e in errs:
            st.error(e)
        return

    colors = parse_csv(colors_raw)
    sizes = parse_csv(sizes_raw)

    # AI Field Suggestions
    if use_ai_suggest and gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key
        suggestions = ai_suggest_fields(category.strip(), list(col_map.keys()))
        if suggestions:
            for field, value in suggestions.items():
                if field in fv and not str(fv[field]).strip():
                    fv[field] = value
            st.info(f"🤖 AI suggested {len(suggestions)} fields")

    # Parse images
    img1_urls = parse_urls(img1_raw)
    img2_urls = parse_urls(img2_raw)
    img3_urls = parse_urls(img3_raw)
    img4_urls = parse_urls(img4_raw)

    # Single catalog
    catalog_categories = [category.strip()]

    # Max per catalog
    max_per_catalog = len(colors) * len(sizes)
    actual_per_catalog = min(int(count), max_per_catalog)
    if actual_per_catalog < int(count):
        st.warning(f"⚠️ Max per catalog = {len(colors)}×{len(sizes)} = {max_per_catalog}")

    # ─── BUILD ROWS ──────────────────────────────────────────────────────
    rows = []
    row_idx = 0

    for cat_idx, cat_name in enumerate(catalog_categories):
        catalog_style = f"{style_code.strip()}-C{cat_idx+1}" if cat_idx > 0 else style_code.strip()
        batch_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))

        # Unique Style ID per color (same for all sizes of that color)
        color_style_ids = {}
        for ci, color in enumerate(colors):
            color_style_ids[color] = f"{catalog_style}-{color[:3].upper()}{batch_id}{ci+1}"

        # Title per color (unique per catalog + color)
        color_titles = {}
        if use_ai_titles and gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
            ai_titles = ai_generate_titles(brand.strip(), cat_name, colors,
                str(fv.get('Occasion', 'Casual Wear')), audience)
            if ai_titles:
                for color in colors:
                    color_titles[color] = ai_titles.get(color, "")
        for color in colors:
            if not color_titles.get(color):
                color_titles[color] = gen_title(brand.strip(), cat_name, color,
                    occasion=str(fv.get('Occasion', '')), audience=audience)

        # Generate rows
        catalog_row_count = 0
        for ci, color in enumerate(colors):
            for si, size in enumerate(sizes):
                if catalog_row_count >= actual_per_catalog:
                    break
                row = {}
                row['Product Name'] = color_titles[color]
                row['SKU ID'] = gen_sku(catalog_style, row_idx)
                row['Product ID / Style ID'] = color_style_ids[color]
                row['Brand Name'] = brand.strip()
                row[VARIATION_FIELD] = size
                row['Group ID'] = str(cat_idx * len(colors) + ci + 1)

                # Form values (skip programmatic fields)
                for f, v in fv.items():
                    val = str(v).strip()
                    if not val or f in PROGRAMMATIC_FIELDS:
                        continue
                    if f == 'Meesho Price':
                        try:
                            mp = float(val)
                            if price_var > 0:
                                mp = vary_price(mp, price_var)
                            row['Meesho Price'] = mp
                            row['Wrong/Defective Returns Price'] = round(mp - 1, 2)
                        except ValueError:
                            row[f] = val
                    elif f == 'Wrong/Defective Returns Price':
                        pass
                    elif f in PRICE_FIELDS and price_var > 0:
                        try:
                            row[f] = vary_price(float(val), price_var)
                        except ValueError:
                            row[f] = val
                    else:
                        row[f] = val

                # MRP
                if mrp_val.strip():
                    row['MRP'] = mrp_val.strip()

                # Images
                if img1_urls:
                    row['Image 1 (Front)'] = img1_urls[row_idx % len(img1_urls)]
                if img2_urls:
                    row['Image 2'] = img2_urls[row_idx % len(img2_urls)]
                if img3_urls:
                    row['Image 3'] = img3_urls[row_idx % len(img3_urls)]
                if img4_urls:
                    row['Image 4'] = img4_urls[row_idx % len(img4_urls)]

                # Foot measurements
                if size in FOOT_LENGTH_MAP:
                    row['Foot Length Size'] = FOOT_LENGTH_MAP[size]
                if size in FOOT_WIDTH_MAP:
                    row['Foot Width Size'] = FOOT_WIDTH_MAP[size]

                # Color
                if 'Color' in col_map:
                    row['Color'] = color

                # AI Description (once per color per catalog)
                if use_ai_desc and gemini_key and 'Product Description' in col_map and si == 0:
                    os.environ["GEMINI_API_KEY"] = gemini_key
                    desc = ai_generate_description(brand.strip(), cat_name, color,
                        str(fv.get('Fabric', '')), str(fv.get('Occasion', '')), audience)
                    if desc:
                        st.session_state[f'desc_{cat_idx}_{ci}'] = desc
                if f'desc_{cat_idx}_{ci}' in st.session_state:
                    raw_desc = st.session_state[f'desc_{cat_idx}_{ci}']
                    # Remove restricted keywords from description
                    for kw in RESTRICTED_KEYWORDS:
                        raw_desc = re.sub(r'\b' + re.escape(kw) + r'\b', '', raw_desc, flags=re.IGNORECASE)
                    row['Product Description'] = re.sub(r'\s+', ' ', raw_desc).strip()

                rows.append(row)
                row_idx += 1
                catalog_row_count += 1
            if catalog_row_count >= actual_per_catalog:
                break

    # ─── QC CHECK ─────────────────────────────────────────────────────────
    qc_errors, qc_warnings = run_qc_check(rows, col_map, dropdowns)

    if qc_errors:
        st.error(f"❌ QC FAILED — {len(qc_errors)} error(s):")
        for err in qc_errors[:10]:
            st.markdown(f"  🔴 Row {err['row']} | `{err['field']}` — {err['message']}")
    if qc_warnings:
        with st.expander(f"⚠️ {len(qc_warnings)} Warning(s)"):
            for w in qc_warnings[:10]:
                st.markdown(f"  🟡 Row {w['row']} | `{w['field']}` — {w['message']}")
    if not qc_errors:
        st.success("✅ QC Pre-Check PASSED!")

    # ─── DATABASE CHECK ───────────────────────────────────────────────────
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    db_client = None
    if supabase_url and supabase_key:
        db_client = get_supabase_client()

    if db_client:
        all_style_ids = set(r.get('Product ID / Style ID', '') for r in rows)
        all_sku_ids = set(r.get('SKU ID', '') for r in rows)
        all_img_urls = set()
        for r in rows:
            for img_f in ['Image 1 (Front)', 'Image 2', 'Image 3', 'Image 4']:
                if r.get(img_f):
                    all_img_urls.add(r[img_f])

        dupes = check_duplicates(db_client, all_style_ids, all_sku_ids, list(all_img_urls)[:20])

        # If duplicate SKUs found, regenerate them
        if dupes["sku_ids"]:
            dupe_skus = set(dupes["sku_ids"])
            for row in rows:
                while row.get('SKU ID', '') in dupe_skus:
                    row['SKU ID'] = gen_sku(style_code.strip(), random.randint(100, 9999))
            st.info(f"🔄 {len(dupe_skus)} duplicate SKU IDs detected — auto-regenerated!")

        if dupes["style_ids"]:
            st.error(f"🔴 DUPLICATE Style IDs! Already uploaded: {dupes['style_ids'][:3]}")
        if dupes["image_urls"]:
            st.warning(f"⚠️ {len(dupes['image_urls'])} image(s) pehle use hui — duplicate risk!")
        st.caption(f"🗄️ Database: {get_listing_count(db_client)} listings stored")

    # ─── DOWNLOAD ─────────────────────────────────────────────────────────
    uploaded.seek(0)
    wb2 = load_workbook(uploaded, keep_vba=False)
    inject_data(wb2, rows)
    out = io.BytesIO()
    wb2.save(out); out.seek(0)
    st.success(f"✅ {len(rows)} listings generated!")
    st.download_button("📥 Download Filled Template", out.getvalue(),
        f"Filled_{style_code}_{len(rows)}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # Preview
    df = pd.DataFrame(rows)
    prev_cols = ['Product Name', VARIATION_FIELD, 'Product ID / Style ID', 'Group ID', 'Color']
    st.dataframe(df[[c for c in prev_cols if c in df.columns]].head(20), use_container_width=True)

    # ─── SAVE TO DATABASE ─────────────────────────────────────────────────
    if db_client and not qc_errors:
        if save_listings(db_client, rows, catalog_name=category.strip()):
            st.success("💾 Listings saved to database!")


if __name__ == "__main__":
    main()
