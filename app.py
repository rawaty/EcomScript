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

# Load environment variables
load_dotenv()

# Import AI helper
from ai_helper import ai_generate_titles, ai_generate_description, ai_suggest_fields

# ─── Profile & Preset Storage ─────────────────────────────────────────────────

PROFILES_FILE = "profiles.json"
PRESETS_FILE = "presets.json"


def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return {}


def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


# Default category presets
DEFAULT_PRESETS = {
    "Flip Flops (Men)": {
        "Generic Name": "Flip Flops",
        "Material": "EVA",
        "Sole Material": "EVA",
        "Type": "Thong Flip-flops",
        "Pattern": "Solid",
        "Waterproof": "Yes",
        "Main Trend": "Solid/Regular",
        "Net Quantity (N)": "1",
        "Net Weight (gms)": "220",
        "GST %": "5",
        "HSN ID": "64022090",
    },
    "Flip Flops (Women)": {
        "Generic Name": "Flip Flops",
        "Material": "PU",
        "Sole Material": "PU",
        "Type": "Thong Flip-flops",
        "Pattern": "Printed",
        "Waterproof": "No",
        "Main Trend": "Floral",
        "Net Quantity (N)": "1",
        "Net Weight (gms)": "180",
        "GST %": "5",
        "HSN ID": "64022090",
    },
    "Kurta Sets (Girls)": {
        "Generic Name": "Kurtis & Kurtas",
        "Bottom Type": "pyjamas",
        "Dupatta": "Without Dupatta",
        "Occasion": "Casual",
        "Sleeve Length": "Long Sleeves",
        "Stitch": "Ready To Wear",
        "Top Fabric": "Cotton",
        "Top Pattern": "Printed",
        "Top Shape": "straight",
        "Top Hemline": "straight",
        "Top Design Styling": "regular",
        "Net Weight (gms)": "300",
        "GST %": "5",
        "HSN ID": "6111",
    },
    "Sliders (Men)": {
        "Generic Name": "Sliders",
        "Material": "Synthetic",
        "Sole Material": "Rubber",
        "Type": "Sliders",
        "Pattern": "Solid",
        "Waterproof": "No",
        "Main Trend": "Solid/Regular",
        "Net Quantity (N)": "1",
        "Net Weight (gms)": "250",
        "GST %": "5",
        "HSN ID": "64022090",
    },
}


# ─── Constants ────────────────────────────────────────────────────────────────

SEO_ADJECTIVES = [
    "Premium", "Stylish", "Trendy", "Designer", "Exclusive",
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
SKIP_FIELDS = {'ERROR STATUS', 'ERROR MESSAGE'}
AUTO_FIELDS = {'Product Name', 'SKU ID', 'Product ID / Style ID'}
VARIATION_FIELD = 'Variation'
PRICE_FIELDS = {'Meesho Price', 'Wrong/Defective Returns Price', 'Selling Price'}

# Indian shoe size to foot length mapping (cm)
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

# Meesho restricted/warning keywords (avoid in Product Description)
RESTRICTED_KEYWORDS = [
    'comfort', 'comfortable', 'EVA', 'everyday', 'daily wear',
    'best quality', 'premium quality', 'high quality', 'top quality',
    'Amazon', 'Flipkart', 'Myntra', 'Ajio',
    'elegant',
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def parse_csv(raw):
    seen, result = set(), []
    for item in raw.split(","):
        t = item.strip()
        if t and t not in seen:
            seen.add(t); result.append(t)
    return result

def find_data_sheet(wb):
    for name in wb.sheetnames:
        if 'fill' in name.lower(): return wb[name]
    return wb[wb.sheetnames[1]] if len(wb.sheetnames) > 1 else wb[wb.sheetnames[0]]

def find_header_row(ws):
    for r in range(1, 10):
        v = ws.cell(row=r, column=1).value
        if v and 'Fields + Description' in str(v): return r
    for r in range(1, 10):
        for c in range(1, 60):
            v = ws.cell(row=r, column=c).value
            if v and 'Product Name' in str(v) and len(str(v)) > 30: return r
    for r in range(1, 10):
        v = ws.cell(row=r, column=1).value
        if v and str(v).strip() == 'Field Names': return r + 1
    return 3

def find_data_start(ws, hdr):
    start = hdr + 1
    for r in range(hdr+1, hdr+5):
        skip = False
        for c in range(1, 10):
            v = ws.cell(row=r, column=c).value
            if v and ('Tutorial' in str(v) or 'Watch' in str(v) or
                      'Validation Sheet' in str(v) or len(str(v)) > 200):
                skip = True; break
        if skip: start = r + 1
        else: break
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
    for mr in [hdr-1, hdr-2]:
        if mr < 1: continue
        found = False
        for fn, ci in col_map.items():
            v = ws.cell(row=mr, column=ci).value
            if v and 'Compulsory' in str(v):
                comp.add(fn); found = True
        if found: break
    return comp

def get_dropdowns(wb, col_map):
    """Read validation sheet dropdown options."""
    dd = {}
    vs = None
    for name in wb.sheetnames:
        if 'validation' in name.lower(): vs = wb[name]; break
    if not vs: return dd

    # Find header row in validation sheet
    vhr = 1
    for r in range(1, 5):
        v = vs.cell(row=r, column=1).value
        if v and ('Field Type' in str(v) or 'Field Names' in str(v)):
            vhr = r; break

    # Map columns
    vcm = {}
    for c in range(1, vs.max_column + 1):
        v = vs.cell(row=vhr, column=c).value
        if v and str(v).strip() in col_map:
            vcm[str(v).strip()] = c

    # Data rows start after descriptions
    ds = vhr + 1
    chk = vs.cell(row=ds, column=1).value
    if chk and 'Field Names' in str(chk): ds += 1

    for fn, ci in vcm.items():
        vals = []
        for r in range(ds, min(ds + 300, vs.max_row + 1)):
            v = vs.cell(row=r, column=ci).value
            if v: vals.append(str(v).strip())
        if vals: dd[fn] = vals
    return dd


def gen_sku(base, i):
    return f"{base}_{''.join(random.choices(string.ascii_uppercase+string.digits,k=4))}{i+1}"

def gen_style(base, i):
    return f"{base}-{''.join(random.choices(string.ascii_uppercase+string.digits,k=3))}{i+1}"

def gen_title(brand, cat, color, fabric="", occasion="", audience="for Kids"):
    adj = random.choice(SEO_ADJECTIVES)
    feat = random.choice(SEO_FEATURES)
    # If occasion is a raw value like "ethnic", convert to proper format "Ethnic Wear"
    if occasion and occasion.strip():
        occ_val = occasion.strip()
        if not any(occ_val.lower().endswith(s) for s in ['wear', 'collection']):
            occ_val = f"{occ_val.title()} Wear"
        else:
            occ_val = occ_val.title()
        occ = occ_val
    else:
        occ = random.choice(SEO_OCCASIONS)
    # Meesho rule: Each color = separate product = needs UNIQUE Product Name
    # Include color naturally in title
    t = random.choice([
        f"{brand} {adj} {color} {cat} {feat} {occ} {audience}",
        f"{brand} {color} {cat} {adj} {feat} {occ} {audience}",
        f"{adj} {brand} {color} {cat} {occ} {feat} {audience}",
        f"{brand} {color} {cat} {adj} {feat} {audience} {occ}",
    ])
    # Remove any restricted keywords from title
    for kw in RESTRICTED_KEYWORDS:
        t = re.sub(r'\b' + re.escape(kw) + r'\b', '', t, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', t).strip()

def vary_price(base, variation):
    if variation <= 0: return base
    return max(1.0, round(base + random.randint(-variation, variation), 2))

def inject_data(wb, rows):
    ws = find_data_sheet(wb)
    hdr = find_header_row(ws)
    cm = get_col_map(ws, hdr)
    start = find_data_start(ws, hdr)
    for r in range(start, start + len(rows) + 100):
        for c in range(1, ws.max_column + 1):
            ws.cell(row=r, column=c).value = None

    # Fields that must be written as numbers (to match Meesho dropdown validation)
    NUMERIC_FIELDS = {
        'HSN ID', 'GST %', 'Net Weight (gms)', 'Inventory',
        'Net Quantity (N)', 'MRP', 'Meesho Price', 'Wrong/Defective Returns Price',
        'Selling Price', 'Manufacturer Pincode', 'Packer Pincode', 'Importer Pincode',
    }

    for i, row in enumerate(rows):
        for fn, val in row.items():
            if fn in cm:
                if fn in NUMERIC_FIELDS and val is not None and str(val).strip():
                    try:
                        num_val = float(str(val).strip())
                        ws.cell(row=start+i, column=cm[fn]).value = int(num_val) if num_val == int(num_val) else num_val
                    except (ValueError, TypeError):
                        ws.cell(row=start+i, column=cm[fn]).value = val
                else:
                    ws.cell(row=start+i, column=cm[fn]).value = val


# ─── STREAMLIT APP ────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Bulk Listing Generator", layout="wide")
    st.title("🛒 Bulk Listing Generator (Meesho + Flipkart)")
    st.caption("Template upload → Dynamic form (with dropdowns) → Bulk fill → Download")

    uploaded = st.file_uploader("📁 Upload your template (.xlsx)", type=["xlsx"])
    if not uploaded:
        st.info("👆 Upload a blank Meesho or Flipkart template to get started"); return

    try:
        wb = load_workbook(uploaded, keep_vba=False)
        ws = find_data_sheet(wb)
        hdr = find_header_row(ws)
        col_map = get_col_map(ws, hdr)
        data_start = find_data_start(ws, hdr)
        compulsory = get_compulsory(ws, hdr, col_map)
        dropdowns = get_dropdowns(wb, col_map)
    except Exception as e:
        st.error(f"Error: {e}"); return

    fields = [f for f in col_map if f not in SKIP_FIELDS]
    st.success(f"✅ Sheet: '{ws.title}' | {len(fields)} fields | "
               f"{len(compulsory)} required | {len(dropdowns)} dropdowns | Row: {data_start}")

    with st.expander("📋 All detected fields"):
        for f in fields:
            m = "⭐" if f in compulsory else "○"
            d = f" 🔽[{len(dropdowns[f])} opts]" if f in dropdowns else ""
            st.text(f"{m} {f}{d}")

    # ─── Profiles & Presets Section ──────────────────────────────────────────
    st.markdown("---")
    prof_col, preset_col = st.columns(2)

    with prof_col:
        st.markdown("**👤 Saved Profiles (Manufacturer Details)**")
        profiles = load_json(PROFILES_FILE)
        profile_names = list(profiles.keys())

        if profile_names:
            selected_profile = st.selectbox("Load Profile", ["-- None --"] + profile_names,
                                            key="profile_select")
        else:
            selected_profile = "-- None --"
            st.caption("No saved profiles yet. Fill the form and save.")

    with preset_col:
        st.markdown("**📦 Category Presets (One-click fill)**")
        all_presets = {**DEFAULT_PRESETS, **load_json(PRESETS_FILE)}
        preset_names = list(all_presets.keys())
        selected_preset = st.selectbox("Load Preset", ["-- None --"] + preset_names,
                                       key="preset_select")

    # Store prefill values in session state so they persist
    if selected_profile != "-- None --" and selected_profile in profiles:
        for k, v in profiles[selected_profile].items():
            st.session_state[f"f_{k}"] = v
        st.session_state['prefill'] = profiles[selected_profile]
    if selected_preset != "-- None --" and selected_preset in all_presets:
        for k, v in all_presets[selected_preset].items():
            st.session_state[f"f_{k}"] = v
        st.session_state['prefill'] = {**st.session_state.get('prefill', {}), **all_presets[selected_preset]}

    prefill = st.session_state.get('prefill', {})

    # Clear button
    if st.button("🗑️ Clear prefill", key="clear_prefill"):
        st.session_state['prefill'] = {}
        prefill = {}
        # Clear all form field keys
        keys_to_clear = [k for k in st.session_state if k.startswith("f_")]
        for k in keys_to_clear:
            del st.session_state[k]
        st.rerun()

    # Always remove programmatic fields from session state (prevent stale overwrites)
    for stale_key in ['f_Group ID', 'f_Color', 'f_Product Name', 'f_SKU ID',
                      'f_Product ID / Style ID']:
        if stale_key in st.session_state:
            del st.session_state[stale_key]

    with st.form("main_form"):
        st.markdown("### 🎨 Core Settings")
        c1, c2 = st.columns(2)
        with c1:
            # Colors: use dropdown from Validation Sheet if available
            color_options = dropdowns.get('Color', [])
            if color_options:
                colors_selected = st.multiselect(
                    "Colors (select from template) *",
                    options=color_options,
                    help="Validation Sheet se detected colors."
                )
                colors_raw = ", ".join(colors_selected)
            else:
                colors_raw = st.text_input("Colors *", placeholder="Orange, Navy, Red")

            brand = st.text_input("Brand Name *", placeholder="Riwaaz")
            category = st.text_input("Product Category *", placeholder="Kurta Set")
        with c2:
            # Sizes: use dropdown from Validation Sheet if available
            size_options = dropdowns.get(VARIATION_FIELD, [])
            if size_options:
                sizes_selected = st.multiselect(
                    "Sizes / Variations (select from template) *",
                    options=size_options,
                    help="Validation Sheet se detected options. Multiple select karo."
                )
                sizes_raw = ", ".join(sizes_selected)
            else:
                sizes_raw = st.text_input("Sizes *", placeholder="5-6 Years, 7-8 Years")

            style_code = st.text_input("Base Style Code *", placeholder="A-501")
            audience = st.selectbox("Target Audience *",
                ["for Boys","for Girls","for Kids","for Baby Boys",
                 "for Baby Girls","for Men","for Women","Unisex"])

        st.markdown("### 🤖 AI Settings (Google Gemini — Free)")
        ai_col1, ai_col2 = st.columns(2)
        with ai_col1:
            use_ai_titles = st.checkbox("✨ AI Title Generation",
                help="Gemini se Meesho-optimized SEO titles generate karo")
            use_ai_desc = st.checkbox("📝 AI Product Description",
                help="AI se product description auto-generate")
        with ai_col2:
            use_ai_suggest = st.checkbox("💡 AI Field Suggestions",
                help="Category ke basis pe fields auto-fill karo")
            gemini_key = st.text_input("Gemini API Key",
                value=os.environ.get("GEMINI_API_KEY", ""),
                type="password",
                help="https://aistudio.google.com/apikey se free key lo")

        st.markdown("### 💰 Price & Count")
        c3, c4, c5 = st.columns(3)
        with c3:
            count = st.number_input("Listings count", 1, 5000, 50, 10)
        with c4:
            price_var = st.number_input("Price variation (±₹)", 0, 100, 0, 5,
                help="0 = same price for all. 20 = each row varies ±₹20 randomly.")
        with c5:
            st.markdown("") # spacer

        st.markdown("### � Multi-Catalog Mode (Visibility Booster)")
        st.markdown("*Same product, multiple catalogs with different titles — zyada visibility!*")
        num_catalogs = st.number_input("Number of Catalogs", 1, 10, 1, 1,
            help="1 = normal single catalog. 3-5 = same product 3-5 alag catalogs mein with different SEO titles.")
        if num_catalogs > 1:
            alt_categories = st.text_area(
                f"Alternate Product Categories (one per line, {num_catalogs} total)",
                placeholder="Flip flop\nMen's Slippers\nCasual Flip Flops\nBeach Sandals",
                height=100,
                help="Har catalog ke liye ek alag product category likho. Ye title mein use hoga."
            )
        else:
            alt_categories = ""

        st.markdown("### �📝 Template Fields")
        st.markdown("*Fields with dropdowns will show values from the Validation Sheet*")

        # Image URL Pool
        st.markdown("### 🖼️ Image URLs (bulk paste — one URL per line)")
        st.markdown("*URLs will rotate across listings. More URLs = less repetition.*")
        img_c1, img_c2 = st.columns(2)
        with img_c1:
            img1_raw = st.text_area("Image 1 (Front) URLs *", height=100,
                                     placeholder="https://meesho.com/img1.jpg\nhttps://meesho.com/img2.jpg")
            img2_raw = st.text_area("Image 2 URLs", height=100,
                                     placeholder="https://meesho.com/back1.jpg\nhttps://meesho.com/back2.jpg")
        with img_c2:
            img3_raw = st.text_area("Image 3 URLs", height=100, placeholder="Optional")
            img4_raw = st.text_area("Image 4 URLs", height=100, placeholder="Optional")

        fv = {}
        show = [f for f in fields if f not in AUTO_FIELDS
                and f != VARIATION_FIELD and f != 'Brand Name'
                and f not in ('Image 1 (Front)', 'Image 2', 'Image 3', 'Image 4')
                and f not in ('Foot Length Size', 'Foot Width Size')
                and f != 'Group ID' and f != 'Color']
        req = [f for f in show if f in compulsory]
        opt = [f for f in show if f not in compulsory]

        # Required fields
        if req:
            st.markdown("**⭐ Required:**")
            cols = st.columns(2)
            for i, f in enumerate(req):
                with cols[i % 2]:
                    if f in dropdowns:
                        opts = [""] + dropdowns[f]
                        fv[f] = st.selectbox(f"⭐ {f}", options=opts, key=f"f_{f}")
                    else:
                        fv[f] = st.text_input(f"⭐ {f}", key=f"f_{f}")

        # Optional fields
        if opt:
            with st.expander(f"📎 Optional Fields ({len(opt)})"):
                cols2 = st.columns(2)
                for i, f in enumerate(opt):
                    with cols2[i % 2]:
                        if f in dropdowns:
                            opts = [""] + dropdowns[f]
                            fv[f] = st.selectbox(f, options=opts, key=f"f_{f}")
                        else:
                            fv[f] = st.text_input(f, key=f"f_{f}")

        submitted = st.form_submit_button("🚀 Generate & Fill Template")

        # Save Profile option inside form
        st.markdown("---")
        st.markdown("**💾 Save Profile**")
        save_col1, save_col2 = st.columns([3, 1])
        with save_col1:
            profile_name = st.text_input("Profile name to save", placeholder="My Business",
                                         key="save_profile_name")
        with save_col2:
            save_profile = st.form_submit_button("💾 Save")

    if save_profile:
        if profile_name.strip():
            profiles = load_json(PROFILES_FILE)
            profile_data = {}
            for f, v in fv.items():
                val = str(v).strip()
                if val:
                    profile_data[f] = val
            profile_data['Brand Name'] = brand.strip() if brand else ""
            profiles[profile_name.strip()] = profile_data
            save_json(PROFILES_FILE, profiles)
            st.success(f"✅ Profile '{profile_name.strip()}' saved! Reload page to see it in dropdown.")
        else:
            st.error("Profile name daalo")
        return

    if submitted:
        errs = []
        if not colors_raw.strip(): errs.append("Colors required")
        if not sizes_raw.strip(): errs.append("Sizes required")
        if not brand.strip(): errs.append("Brand Name required")
        if not style_code.strip(): errs.append("Style Code required")
        if not category.strip(): errs.append("Product Category required")
        for f in fv:
            if f in compulsory and not str(fv[f]).strip():
                errs.append(f"⭐ '{f}' is required")
        if errs:
            for e in errs: st.error(e)
            return

        colors = parse_csv(colors_raw)
        sizes = parse_csv(sizes_raw)

        # AI Field Suggestions — auto-fill empty fields
        if use_ai_suggest and gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
            suggestions = ai_suggest_fields(category.strip(), list(col_map.keys()))
            if suggestions:
                for field, value in suggestions.items():
                    # Only fill if user hasn't already provided a value
                    if field in fv and not str(fv[field]).strip():
                        fv[field] = value
                st.info(f"🤖 AI suggested values for {len(suggestions)} fields")

        # Parse image URL pools
        img1_urls = [u.strip() for u in img1_raw.strip().split('\n') if u.strip()]
        img2_urls = [u.strip() for u in img2_raw.strip().split('\n') if u.strip()]
        img3_urls = [u.strip() for u in img3_raw.strip().split('\n') if u.strip()]
        img4_urls = [u.strip() for u in img4_raw.strip().split('\n') if u.strip()]

        # Parse multi-catalog categories
        if num_catalogs > 1 and alt_categories.strip():
            catalog_categories = [c.strip() for c in alt_categories.strip().split('\n') if c.strip()]
            # Pad with original category if not enough lines provided
            while len(catalog_categories) < num_catalogs:
                catalog_categories.append(category.strip())
        else:
            catalog_categories = [category.strip()]

        # IMPORTANT: Meesho rule — same color ke sab sizes ka Product Name SAME hona chahiye
        # Limit: max listings per catalog = colors × sizes
        max_per_catalog = len(colors) * len(sizes)
        actual_per_catalog = min(int(count), max_per_catalog)
        if actual_per_catalog < int(count):
            st.warning(f"⚠️ Max per catalog = {len(colors)} colors × {len(sizes)} sizes = {max_per_catalog}. "
                       f"Using {actual_per_catalog} per catalog.")

        # Build rows for all catalogs
        rows = []
        row_idx = 0

        for cat_idx, cat_name in enumerate(catalog_categories):
            # Generate unique titles for this catalog
            color_titles = {}
            # Try AI title generation first
            ai_titles = None
            if use_ai_titles and gemini_key:
                os.environ["GEMINI_API_KEY"] = gemini_key
                ai_titles = ai_generate_titles(
                    brand.strip(), cat_name, colors,
                    str(fv.get('Occasion', 'Casual Wear')), audience
                )
            for color in colors:
                if ai_titles and color in ai_titles:
                    color_titles[color] = ai_titles[color]
                else:
                    color_titles[color] = gen_title(brand.strip(), cat_name,
                        color, occasion=str(fv.get('Occasion', '')), audience=audience)

            # Unique style code per catalog
            catalog_style = f"{style_code.strip()}-C{cat_idx+1}" if cat_idx > 0 else style_code.strip()

            # Each catalog gets its own color × size grid
            catalog_row_count = 0
            for ci, color in enumerate(colors):
                for si, size in enumerate(sizes):
                    if catalog_row_count >= actual_per_catalog:
                        break
                    row = {}

                    row['Product Name'] = color_titles[color]
                    row['SKU ID'] = gen_sku(catalog_style, row_idx)
                    row['Product ID / Style ID'] = gen_style(catalog_style, row_idx)
                    row['Brand Name'] = brand.strip()
                    row[VARIATION_FIELD] = size

                    # Group ID — unique per color per catalog
                    # Meesho rule: same Group ID = same product
                    # Each color in each catalog is a separate product
                    group_num = cat_idx * len(colors) + ci + 1
                    row['Group ID'] = str(group_num)

                    # Price & other fields
                    for f, v in fv.items():
                        val = str(v).strip()
                        if not val:
                            continue
                        # Skip fields we set programmatically — don't overwrite!
                        if f in ('Group ID', 'Product Name', 'SKU ID',
                                 'Product ID / Style ID', 'Brand Name', 'Color'):
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

                    # Images
                    if img1_urls:
                        row['Image 1 (Front)'] = img1_urls[row_idx % len(img1_urls)]
                    if img2_urls:
                        row['Image 2'] = img2_urls[row_idx % len(img2_urls)]
                    if img3_urls:
                        row['Image 3'] = img3_urls[row_idx % len(img3_urls)]
                    if img4_urls:
                        row['Image 4'] = img4_urls[row_idx % len(img4_urls)]

                    # Foot length/width
                    if size in FOOT_LENGTH_MAP:
                        row['Foot Length Size'] = FOOT_LENGTH_MAP[size]
                    if size in FOOT_WIDTH_MAP:
                        row['Foot Width Size'] = FOOT_WIDTH_MAP[size]

                    # Color
                    if 'Color' in col_map:
                        row['Color'] = color

                    # AI Product Description (generate once per color)
                    if use_ai_desc and gemini_key and 'Product Description' in col_map:
                        if si == 0:  # Only generate once per color, reuse for all sizes
                            os.environ["GEMINI_API_KEY"] = gemini_key
                            ai_desc = ai_generate_description(
                                brand.strip(), cat_name, color,
                                str(fv.get('Fabric', '')),
                                str(fv.get('Occasion', '')), audience
                            )
                            if ai_desc:
                                st.session_state[f'ai_desc_{cat_idx}_{ci}'] = ai_desc
                        desc = st.session_state.get(f'ai_desc_{cat_idx}_{ci}', '')
                        if desc:
                            row['Product Description'] = desc

                    rows.append(row)
                    row_idx += 1
                    catalog_row_count += 1
                if catalog_row_count >= actual_per_catalog:
                    break

        # Inject & download
        # MEESHO RULE: Each catalog = separate Excel file
        if num_catalogs > 1:
            # Split rows by catalog and generate separate files
            import zipfile
            catalog_rows = {}
            for row in rows:
                gid = row.get('Group ID', '1')
                # Find which catalog this belongs to based on index
                if gid not in catalog_rows:
                    catalog_rows[gid] = []
                catalog_rows[gid].append(row)

            # Group by catalog (each catalog = colors sharing same catalog_style)
            # Rebuild: rows per catalog
            rows_per_catalog = []
            start_idx = 0
            for cat_idx in range(len(catalog_categories)):
                cat_rows = []
                for ci in range(len(colors)):
                    for si in range(len(sizes)):
                        if start_idx < len(rows):
                            cat_rows.append(rows[start_idx])
                            start_idx += 1
                        if len(cat_rows) >= actual_per_catalog:
                            break
                    if len(cat_rows) >= actual_per_catalog:
                        break
                rows_per_catalog.append(cat_rows)

            # Create ZIP with separate Excel files
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for cat_idx, cat_rows in enumerate(rows_per_catalog):
                    if not cat_rows:
                        continue
                    uploaded.seek(0)
                    wb_cat = load_workbook(uploaded, keep_vba=False)
                    inject_data(wb_cat, cat_rows)
                    cat_out = io.BytesIO()
                    wb_cat.save(cat_out)
                    cat_out.seek(0)
                    cat_name_safe = re.sub(r'[^a-zA-Z0-9_-]', '-', catalog_categories[cat_idx])
                    zf.writestr(f"Catalog_{cat_idx+1}_{cat_name_safe}.xlsx", cat_out.getvalue())

            zip_buffer.seek(0)

            st.success(f"✅ {len(rows)} listings generated across {len(rows_per_catalog)} catalogs!")
            st.info(f"📦 {len(rows_per_catalog)} separate Excel files in ZIP — har catalog alag upload karo Meesho pe")
            df = pd.DataFrame(rows)
            prev = ['Product Name', VARIATION_FIELD, 'SKU ID', 'Group ID', 'Color']
            st.dataframe(df[[c for c in prev if c in df.columns]].head(20),
                         use_container_width=True)

            fn = f"Catalogs_{re.sub(r'[^a-zA-Z0-9_-]','-',style_code)}_{len(rows_per_catalog)}files.zip"
            st.download_button("📥 Download All Catalogs (ZIP)", zip_buffer.getvalue(),
                               fn, "application/zip")

        else:
            # Single catalog — single file
            uploaded.seek(0)
            wb2 = load_workbook(uploaded, keep_vba=False)
            inject_data(wb2, rows)
            out = io.BytesIO()
            wb2.save(out); out.seek(0)

            st.success(f"✅ {len(rows)} listings generated and filled!")
            df = pd.DataFrame(rows)
            prev = ['Product Name', VARIATION_FIELD, 'SKU ID', 'Brand Name']
            st.dataframe(df[[c for c in prev if c in df.columns]].head(15),
                         use_container_width=True)
            if len(rows) > 15:
                st.caption(f"...+{len(rows)-15} more rows in download")

            fn = f"Filled_{re.sub(r'[^a-zA-Z0-9_-]','-',style_code)}_{len(rows)}.xlsx"
            st.download_button("📥 Download Filled Template", out.getvalue(),
                               fn, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    main()
