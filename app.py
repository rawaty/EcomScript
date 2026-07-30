import streamlit as st
import pandas as pd
import io
import re
import random
import string
from typing import Optional
from openpyxl import load_workbook

# ─── Constants ────────────────────────────────────────────────────────────────

TITLE_PREFIXES = [
    "Premium", "Classic", "Trendy", "Stylish", "Elegant",
    "Comfortable", "Ethnic", "Designer", "Exclusive", "Traditional",
    "Modern", "Beautiful", "Fancy", "Attractive", "Latest",
    "New", "Fashionable", "Superior", "Printed", "Embroidered",
]

# Fields to skip (system use — don't show in form)
SKIP_FIELDS = {'ERROR STATUS', 'ERROR MESSAGE'}

# Fields that get auto-generated per row (random unique)
AUTO_GENERATED_FIELDS = {'Product Name', 'SKU ID', 'Product ID / Style ID'}

# The size/variation field
VARIATION_FIELD = 'Variation'


# ─── Template Parsing ─────────────────────────────────────────────────────────

def parse_comma_separated(raw: str) -> list[str]:
    seen = set()
    result = []
    for item in raw.split(","):
        trimmed = item.strip()
        if trimmed and trimmed not in seen:
            seen.add(trimmed)
            result.append(trimmed)
    return result


def find_data_sheet(wb):
    """Find the 'Fill this' sheet."""
    for name in wb.sheetnames:
        if 'fill' in name.lower():
            return wb[name]
    if len(wb.sheetnames) > 1:
        return wb[wb.sheetnames[1]]
    return wb[wb.sheetnames[0]]


def find_header_row(ws):
    """Find the 'Fields + Description' row (contains field names in multiline cells)."""
    for row_idx in range(1, min(10, ws.max_row + 1)):
        cell_val = ws.cell(row=row_idx, column=1).value
        if cell_val and 'Fields + Description' in str(cell_val):
            return row_idx
    # Fallback: look for multiline cell with 'Product Name' + description
    for row_idx in range(1, min(10, ws.max_row + 1)):
        for col_idx in range(1, min(60, ws.max_column + 1)):
            cell_val = ws.cell(row=row_idx, column=col_idx).value
            if cell_val:
                val = str(cell_val)
                if 'Product Name' in val and len(val) > 30:
                    return row_idx
    # Fallback: row after "Field Names"
    for row_idx in range(1, min(10, ws.max_row + 1)):
        cell_val = ws.cell(row=row_idx, column=1).value
        if cell_val and 'Field Names' == str(cell_val).strip():
            return row_idx + 1
    return 3


def find_data_start_row(ws, header_row: int) -> int:
    """Find where data rows start (after header + tutorial/description rows)."""
    start = header_row + 1
    for row_idx in range(header_row + 1, header_row + 5):
        skip = False
        for col_idx in range(1, min(10, ws.max_column + 1)):
            cell_val = ws.cell(row=row_idx, column=col_idx).value
            if cell_val:
                val = str(cell_val)
                if ('Tutorial' in val or 'Watch' in val or
                    'Validation Sheet' in val or len(val) > 200):
                    skip = True
                    break
        if skip:
            start = row_idx + 1
        else:
            break
    return start


def get_column_mapping(ws, header_row: int) -> dict:
    """Extract field names from multiline header cells.
    
    Cells look like: '\\n\\nProduct Name\\n\\nPlease enter the product name...'
    We extract the first non-empty line as the field name.
    """
    col_map = {}
    for col_idx in range(1, ws.max_column + 1):
        cell_val = ws.cell(row=header_row, column=col_idx).value
        if cell_val:
            lines = str(cell_val).split('\n')
            field_name = None
            for line in lines:
                stripped = line.strip()
                if stripped and stripped not in (
                    'Fields + Description:',
                    'Field Names',
                    'Field Type (Compulsory, Recommended, System_Use) ->',
                ):
                    field_name = stripped
                    break
            if field_name:
                col_map[field_name] = col_idx
    return col_map


def get_compulsory_fields(ws, header_row: int, col_map: dict) -> set:
    """Detect which fields are compulsory from the '* Compulsory Field' markers.
    
    Meesho template has a row ABOVE the Fields+Description row (usually header_row - 1)
    that contains '* Compulsory Field' or 'Optional Field' for each column.
    """
    compulsory = set()
    # The markers row is typically 1 row above header_row
    # But could also be 2 rows above — check both
    for marker_row in [header_row - 1, header_row - 2]:
        if marker_row < 1:
            continue
        found_any = False
        for field_name, col_idx in col_map.items():
            cell_val = ws.cell(row=marker_row, column=col_idx).value
            if cell_val:
                val = str(cell_val).strip()
                if 'Compulsory' in val:
                    compulsory.add(field_name)
                    found_any = True
        if found_any:
            break

    return compulsory


# ─── Random Generators ────────────────────────────────────────────────────────

def generate_random_sku(base_code: str, index: int) -> str:
    rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{base_code}_{rnd}{index + 1}"


def generate_random_style_code(base_code: str, index: int) -> str:
    rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"{base_code}-{rnd}{index + 1}"


def generate_random_title(brand: str, category: str, color: str) -> str:
    prefix = random.choice(TITLE_PREFIXES)
    templates = [
        f"{brand} {prefix} {category} for Girls_({color})",
        f"{brand} {category} {prefix} Collection_({color})",
        f"{prefix} {brand} {category} for Kids_({color})",
        f"{brand} {prefix} {category}_({color})",
        f"{prefix} {category} by {brand}_({color})",
        f"{brand} {category} - {prefix}_({color})",
    ]
    return random.choice(templates)


# ─── Data Injection ───────────────────────────────────────────────────────────

def inject_data(wb, data_rows: list[dict]) -> None:
    """Inject data rows into the Fill sheet."""
    ws = find_data_sheet(wb)
    header_row = find_header_row(ws)
    col_map = get_column_mapping(ws, header_row)
    start_row = find_data_start_row(ws, header_row)

    # Clear existing data rows
    for row_idx in range(start_row, start_row + len(data_rows) + 100):
        for col_idx in range(1, ws.max_column + 1):
            ws.cell(row=row_idx, column=col_idx).value = None

    # Write data
    for i, row_data in enumerate(data_rows):
        for field_name, value in row_data.items():
            if field_name in col_map:
                ws.cell(row=start_row + i, column=col_map[field_name]).value = value


# ─── STREAMLIT APP ────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Meesho Bulk Listing - Dynamic", layout="wide")
    st.title("🛒 Meesho Bulk Listing Generator")
    st.caption("Koi bhi Meesho template upload karo → Automatic form banega → Bulk fill karke download karo")

    # Step 1: Upload template
    st.subheader("📁 Step 1: Meesho Template Upload Karo")
    uploaded_file = st.file_uploader(
        "Meesho ka blank .xlsx template yahan upload karo",
        type=["xlsx"],
    )

    if uploaded_file is None:
        st.info("👆 Meesho Supplier Panel se template download karke yahan upload karo")
        return

    # Parse template
    try:
        wb = load_workbook(uploaded_file, keep_vba=False)
        ws = find_data_sheet(wb)
        header_row = find_header_row(ws)
        col_map = get_column_mapping(ws, header_row)
        data_start = find_data_start_row(ws, header_row)
    except Exception as e:
        st.error(f"Template read error: {e}")
        return

    # Filter out system fields
    form_fields = [f for f in col_map.keys() if f not in SKIP_FIELDS]
    compulsory_fields = get_compulsory_fields(ws, header_row, col_map)

    st.success(f"✅ Template loaded! Sheet: '{ws.title}' | "
               f"{len(form_fields)} fields detected | "
               f"{len(compulsory_fields)} compulsory | Data row: {data_start}")

    with st.expander("📋 Detected Fields (click to see)"):
        for f in form_fields:
            marker = "⭐ REQUIRED" if f in compulsory_fields else "○ Optional"
            st.text(f"{marker} — {f}")

    # Step 2: Dynamic Form
    st.subheader("📋 Step 2: Product Details Bharo")
    st.markdown("*Auto-generated fields (Product Name, SKU ID, Style ID) form mein nahi dikhenge — "
                "ye automatically random generate honge.*")

    with st.form("dynamic_form"):
        # Special inputs first
        st.markdown("**🎨 Colors & Sizes (for variation)**")
        col_a, col_b = st.columns(2)
        with col_a:
            colors_raw = st.text_input(
                "Colors (comma-separated) *",
                placeholder="Orange, Navy, Red, Blue, Green"
            )
        with col_b:
            sizes_raw = st.text_input(
                "Sizes / Variations (comma-separated) *",
                placeholder="5-6 Years, 7-8 Years, 9-10 Years"
            )

        st.markdown("**🏷️ Brand & Style (for title/SKU generation)**")
        col_c, col_d = st.columns(2)
        with col_c:
            brand_name = st.text_input("Brand Name *", placeholder="Riwaaz")
        with col_d:
            base_style_code = st.text_input("Base Style Code *", placeholder="A-501")

        product_category = st.text_input("Product Category (for title) *",
                                         placeholder="Kurta Pyjama Set")

        # Dynamic form fields from template
        st.markdown("---")
        st.markdown("**📝 Template Fields (detected from your uploaded file)**")
        st.markdown("⭐ = Required field")

        # Show input for each field that's NOT auto-generated or variation
        field_values = {}
        fields_to_show = [f for f in form_fields
                          if f not in AUTO_GENERATED_FIELDS
                          and f != VARIATION_FIELD
                          and f != 'Brand Name']  # Brand Name already asked above

        # Separate required and optional
        required_fields = [f for f in fields_to_show if f in compulsory_fields]
        optional_fields = [f for f in fields_to_show if f not in compulsory_fields]

        # Show required fields first
        if required_fields:
            st.markdown("**⭐ Required Fields:**")
            cols = st.columns(2)
            for i, field in enumerate(required_fields):
                with cols[i % 2]:
                    field_values[field] = st.text_input(
                        f"⭐ {field}", key=f"field_{field}"
                    )

        # Then optional
        if optional_fields:
            with st.expander("📎 Optional Fields (click to expand)"):
                cols2 = st.columns(2)
                for i, field in enumerate(optional_fields):
                    with cols2[i % 2]:
                        field_values[field] = st.text_input(
                            field, key=f"field_{field}"
                        )

        # Generation settings
        st.markdown("---")
        st.markdown("**🔢 Kitni Listings Generate Karni Hain?**")
        listing_count = st.number_input(
            "Number of Listings",
            min_value=1, max_value=5000, value=50, step=10
        )

        submitted = st.form_submit_button("🚀 Generate & Fill Template")

    if submitted:
        # Validate
        errors = []
        if not colors_raw.strip():
            errors.append("Colors required hain")
        if not sizes_raw.strip():
            errors.append("Sizes/Variations required hain")
        if not brand_name.strip():
            errors.append("Brand Name required hai")
        if not base_style_code.strip():
            errors.append("Base Style Code required hai")
        if not product_category.strip():
            errors.append("Product Category required hai")

        # Validate compulsory template fields
        for field in field_values:
            if field in compulsory_fields and not field_values[field].strip():
                errors.append(f"⭐ '{field}' required hai (Compulsory Field)")

        if errors:
            for e in errors:
                st.error(e)
            return

        colors = parse_comma_separated(colors_raw)
        sizes = parse_comma_separated(sizes_raw)

        # Generate data rows
        data_rows = []
        for i in range(int(listing_count)):
            color = colors[i % len(colors)]
            size = sizes[i % len(sizes)]

            row = {}

            # Auto-generated fields
            row['Product Name'] = generate_random_title(
                brand_name.strip(), product_category.strip(), color
            )
            row['SKU ID'] = generate_random_sku(base_style_code.strip(), i)
            row['Product ID / Style ID'] = generate_random_style_code(
                base_style_code.strip(), i
            )
            row['Brand Name'] = brand_name.strip()
            row[VARIATION_FIELD] = size

            # Fill all other fields from form
            for field, value in field_values.items():
                if value.strip():
                    row[field] = value.strip()

            data_rows.append(row)

        # Inject into template
        uploaded_file.seek(0)
        wb = load_workbook(uploaded_file, keep_vba=False)
        inject_data(wb, data_rows)

        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        st.success(f"✅ {len(data_rows)} listings generate ho gaye aur template mein fill ho gaye!")

        # Preview
        preview_df = pd.DataFrame(data_rows)
        preview_cols = ['Product Name', VARIATION_FIELD, 'SKU ID',
                        'Product ID / Style ID', 'Brand Name']
        available = [c for c in preview_cols if c in preview_df.columns]
        st.dataframe(preview_df[available].head(20), use_container_width=True)
        if len(data_rows) > 20:
            st.caption(f"... aur {len(data_rows) - 20} rows (download mein sab honge)")

        # Download
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '-', base_style_code.strip())
        filename = f"Meesho_{sanitized}_{len(data_rows)}listings_FILLED.xlsx"

        st.download_button(
            label="📥 Download Filled Template",
            data=output.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    main()
