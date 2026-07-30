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
    fab = fabric if fabric else ""
    t = random.choice([
        f"{brand} {adj} {fab} {cat} {feat} {occ} {audience}_({color})",
        f"{brand} {fab} {cat} {adj} {feat} {occ} {audience}_({color})",
        f"{adj} {brand} {fab} {cat} {occ} {feat} {audience}_({color})",
        f"{brand} {cat} {adj} {fab} {feat} {occ} {audience}_({color})",
    ])
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
            colors_raw = st.text_input("Colors *", placeholder="Orange, Navy, Red")
            brand = st.text_input("Brand Name *", placeholder="Riwaaz")
            category = st.text_input("Product Category *", placeholder="Kurta Set")
        with c2:
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

        st.markdown("### 📝 Template Fields")
        st.markdown("*Fields with dropdowns will show values from the Validation Sheet*")

        fv = {}
        show = [f for f in fields if f not in AUTO_FIELDS
                and f != VARIATION_FIELD and f != 'Brand Name']
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

        # Build rows
        rows = []
        for i in range(int(count)):
            color = colors[i % len(colors)]
            size = sizes[i % len(sizes)]
            row = {}
            row['Product Name'] = gen_title(brand.strip(), category.strip(),
                color, fabric=str(fv.get('Top Fabric','')),
                occasion=str(fv.get('Occasion','')), audience=audience)
            row['SKU ID'] = gen_sku(style_code.strip(), i)
            row['Product ID / Style ID'] = gen_style(style_code.strip(), i)
            row['Brand Name'] = brand.strip()
            row[VARIATION_FIELD] = size
            for f, v in fv.items():
                val = str(v).strip()
                if val:
                    # Price variation
                    if f in PRICE_FIELDS and price_var > 0:
                        try:
                            row[f] = vary_price(float(val), price_var)
                        except ValueError:
                            row[f] = val
                    else:
                        row[f] = val
            rows.append(row)

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
