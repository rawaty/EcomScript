import streamlit as st
import pandas as pd
import io
import re
import random
import string
from openpyxl import load_workbook

# ─── Constants ────────────────────────────────────────────────────────────────

SEO_ADJECTIVES = [
    "Premium", "Stylish", "Trendy", "Designer", "Exclusive",
    "Comfortable", "Beautiful", "Attractive", "Latest", "Fashionable",
    "Traditional", "Modern", "Elegant", "Classic", "New Launched",
]
SEO_FEATURES = [
    "Embroidered", "Printed", "Self Design", "Solid", "Woven",
    "Block Print", "Bandhani", "Tie Dye", "Floral", "Checked",
    "Striped", "Geometric", "Abstract", "Ethnic Motif", "Colorblocked",
]
SEO_OCCASIONS = [
    "Ethnic Wear", "Party Wear", "Casual Wear", "Daily Wear",
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
    occ = occasion if occasion else random.choice(SEO_OCCASIONS)
    # Do NOT include fabric/material in title — restricted keywords like EVA cause errors
    t = random.choice([
        f"{brand} {adj} {cat} {feat} {occ} {audience}_({color})",
        f"{brand} {cat} {adj} {feat} {occ} {audience}_({color})",
        f"{adj} {brand} {cat} {occ} {feat} {audience}_({color})",
        f"{brand} {cat} {adj} {feat} {audience} {occ}_({color})",
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
    for i, row in enumerate(rows):
        for fn, val in row.items():
            if fn in cm:
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
                and f not in ('Image 1 (Front)', 'Image 2', 'Image 3', 'Image 4')]
        req = [f for f in show if f in compulsory]
        opt = [f for f in show if f not in compulsory]

        # Required fields
        if req:
            st.markdown("**⭐ Required:**")
            cols = st.columns(2)
            for i, f in enumerate(req):
                with cols[i % 2]:
                    if f in dropdowns:
                        fv[f] = st.selectbox(f"⭐ {f}", options=[""] + dropdowns[f],
                                             key=f"f_{f}")
                    else:
                        fv[f] = st.text_input(f"⭐ {f}", key=f"f_{f}")

        # Optional fields
        if opt:
            with st.expander(f"📎 Optional Fields ({len(opt)})"):
                cols2 = st.columns(2)
                for i, f in enumerate(opt):
                    with cols2[i % 2]:
                        if f in dropdowns:
                            fv[f] = st.selectbox(f, options=[""] + dropdowns[f],
                                                 key=f"f_{f}")
                        else:
                            fv[f] = st.text_input(f, key=f"f_{f}")

        submitted = st.form_submit_button("🚀 Generate & Fill Template")

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
            for color in colors:
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

                    # Group ID — different per catalog
                    row['Group ID'] = str(cat_idx + 1)

                    # Price
                    for f, v in fv.items():
                        val = str(v).strip()
                        if not val:
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

                    rows.append(row)
                    row_idx += 1
                    catalog_row_count += 1
                if catalog_row_count >= actual_per_catalog:
                    break

        # Inject & download
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
