"""
GST Helper — Meesho TCS reports se GSTR-1 ka data taiyaar karta hai.

Meesho har mahine do Excel deta hai:
  - tcs_sales.xlsx         -> jo becha (outward supplies)
  - tcs_sales_return.xlsx  -> jo wapas aaya (returns)

Ye module dono ko padh ke NET (sales - returns) nikaalta hai aur
GSTR-1 ke liye teen cheezein banata hai:
  1. B2C (Others)  -> Place-of-Supply (state) x GST-rate wise
  2. HSN Summary   -> HSN wise quantity / value / tax
  3. Summary       -> total taxable, IGST, CGST, SGST, tax payable

Note: Ye SIRF data taiyaar karta hai. Actual filing GST portal pe
aapko khud OTP/DSC ke saath karni hogi.
"""

from __future__ import annotations

import pandas as pd


# ─── State code mapping (GST portal ke "Place of Supply" ke liye) ──────────────
# Key: state ka naam UPPERCASE (file mein kabhi caps, kabhi title-case aata hai)
# Value: (2-digit state code, portal-style "07-Delhi" label)
STATE_CODES = {
    "JAMMU AND KASHMIR": "01", "JAMMU & KASHMIR": "01",
    "HIMACHAL PRADESH": "02",
    "PUNJAB": "03",
    "CHANDIGARH": "04",
    "UTTARAKHAND": "05", "UTTARANCHAL": "05",
    "HARYANA": "06",
    "DELHI": "07",
    "RAJASTHAN": "08",
    "UTTAR PRADESH": "09",
    "BIHAR": "10",
    "SIKKIM": "11",
    "ARUNACHAL PRADESH": "12",
    "NAGALAND": "13",
    "MANIPUR": "14",
    "MIZORAM": "15",
    "TRIPURA": "16",
    "MEGHALAYA": "17",
    "ASSAM": "18",
    "WEST BENGAL": "19",
    "JHARKHAND": "20",
    "ODISHA": "21", "ORISSA": "21",
    "CHATTISGARH": "22", "CHHATTISGARH": "22",
    "MADHYA PRADESH": "23",
    "GUJARAT": "24",
    "DAMAN AND DIU": "26", "DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "26",
    "MAHARASHTRA": "27",
    "ANDHRA PRADESH": "37", "ANDHRA PRADESH (OLD)": "28",
    "KARNATAKA": "29",
    "GOA": "30",
    "LAKSHADWEEP": "31",
    "KERALA": "32",
    "TAMIL NADU": "33",
    "PONDICHERRY": "34", "PUDUCHERRY": "34",
    "TELANGANA": "36",
    "LADAKH": "38",
    "OTHER TERRITORY": "97",
}

# Canonical portal naam (state code -> nice label)
STATE_NAMES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory",
}

# Columns jo Meesho file mein hote hain (reference)
EXPECTED_COLS = [
    "sup_name", "gstin", "sub_order_num", "order_date", "hsn_code",
    "quantity", "gst_rate", "total_taxable_sale_value", "tax_amount",
    "total_invoice_value", "taxable_shipping", "end_customer_state_new",
]


class GSTError(Exception):
    """Business-level error jise UI friendly message ke saath dikha sake."""


def _norm_state(name: str) -> str:
    """State ka naam normalize karo -> UPPERCASE trimmed."""
    if name is None:
        return ""
    return str(name).strip().upper()


def state_code(name: str) -> str:
    """State naam se 2-digit GST code nikaalo. Na mile to '' return."""
    return STATE_CODES.get(_norm_state(name), "")


def load_meesho_file(path_or_buffer) -> pd.DataFrame:
    """
    Ek Meesho TCS Excel padho aur clean DataFrame do.
    - Pehli row header hai (identifier, sup_name, ...).
    - Numeric columns ko number mein badalta hai.
    - Empty/garbage rows hata deta hai.
    """
    df = pd.read_excel(path_or_buffer, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    if "total_taxable_sale_value" not in df.columns:
        raise GSTError(
            "Ye Meesho TCS report nahi lag rahi. "
            "Expected column 'total_taxable_sale_value' nahi mila. "
            f"Mile columns: {list(df.columns)[:8]}..."
        )

    num_cols = [
        "quantity", "gst_rate", "total_taxable_sale_value",
        "tax_amount", "total_invoice_value", "taxable_shipping",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # taxable value NaN wali rows kaam ki nahi
    df = df.dropna(subset=["total_taxable_sale_value"]).reset_index(drop=True)
    return df


def _tag_rows(df: pd.DataFrame, sign: int) -> pd.DataFrame:
    """
    Har row pe derived fields lagao:
    - state_name, state_cd
    - b2b flag (buyer ka GSTIN hai ya nahi)
    - signed taxable/tax (returns ke liye sign = -1)
    """
    out = df.copy()
    out["state_name"] = out["end_customer_state_new"].map(_norm_state)
    out["state_cd"] = out["state_name"].map(lambda s: STATE_CODES.get(s, ""))

    # Meesho B2C hi hota hai (buyer GSTIN khaali). Agar kabhi buyer GSTIN
    # column aaye to b2b detect kar lenge; abhi sab B2C.
    buyer_gstin_col = None
    for cand in ("buyer_gstin", "customer_gstin", "bill_to_gstin"):
        if cand in out.columns:
            buyer_gstin_col = cand
            break
    if buyer_gstin_col:
        out["is_b2b"] = out[buyer_gstin_col].fillna("").str.strip().ne("")
    else:
        out["is_b2b"] = False

    out["gst_rate"] = out["gst_rate"].fillna(0.0)
    out["signed_taxable"] = out["total_taxable_sale_value"].fillna(0.0) * sign
    out["signed_tax"] = out["tax_amount"].fillna(0.0) * sign
    out["signed_qty"] = out["quantity"].fillna(0.0) * sign
    return out


def build_dataset(sales_df: pd.DataFrame,
                  return_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Sales (+1) aur returns (-1) ko ek combined tagged DataFrame mein jodo."""
    parts = [_tag_rows(sales_df, sign=1)]
    if return_df is not None and len(return_df) > 0:
        parts.append(_tag_rows(return_df, sign=-1))
    return pd.concat(parts, ignore_index=True)


def supplier_state_code(df: pd.DataFrame, fallback: str = "07") -> str:
    """Seller ka apna state code (GSTIN ke pehle 2 digit se)."""
    if "gstin" in df.columns and len(df) > 0:
        g = str(df["gstin"].dropna().iloc[0]).strip() if df["gstin"].notna().any() else ""
        if len(g) >= 2 and g[:2].isdigit():
            return g[:2]
    return fallback


def b2c_summary(data: pd.DataFrame, supplier_cd: str) -> pd.DataFrame:
    """
    GSTR-1 Table 7 (B2C Others): Place-of-supply x rate wise.
    Inter-state (POS != supplier state) -> IGST.
    Intra-state (POS == supplier state) -> CGST + SGST (aadha-aadha).
    """
    b2c = data[~data["is_b2b"]].copy()
    grp = (b2c.groupby(["state_cd", "state_name", "gst_rate"], dropna=False)
              .agg(taxable=("signed_taxable", "sum"),
                   tax=("signed_tax", "sum"))
              .reset_index())
    rows = []
    for _, r in grp.iterrows():
        cd = r["state_cd"] or ""
        intra = (cd == supplier_cd)
        taxable = round(float(r["taxable"]), 2)
        tax = round(float(r["tax"]), 2)
        rows.append({
            "Place of Supply": f"{cd}-{STATE_NAMES.get(cd, r['state_name'].title())}" if cd else r["state_name"].title(),
            "Rate (%)": float(r["gst_rate"]),
            "Taxable Value": taxable,
            "IGST": 0.0 if intra else tax,
            "CGST": round(tax / 2, 2) if intra else 0.0,
            "SGST": round(tax / 2, 2) if intra else 0.0,
            "Total Tax": tax,
            "Type": "Intra-state" if intra else "Inter-state",
        })
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(["Place of Supply", "Rate (%)"]).reset_index(drop=True)
    return res


def hsn_summary(data: pd.DataFrame, supplier_cd: str) -> pd.DataFrame:
    """GSTR-1 Table 12 (HSN-wise summary)."""
    grp = (data.groupby(["hsn_code", "gst_rate"], dropna=False)
               .agg(qty=("signed_qty", "sum"),
                    taxable=("signed_taxable", "sum"),
                    tax=("signed_tax", "sum"))
               .reset_index())
    rows = []
    for _, r in grp.iterrows():
        taxable = round(float(r["taxable"]), 2)
        tax = round(float(r["tax"]), 2)
        # HSN summary mein portal IGST/CGST/SGST ka total chahta hai.
        # Yahan hum poori period ke liye combined dikhate hain; intra/inter
        # ka exact split B2C table se aata hai. HSN me aam taur pe total tax.
        rows.append({
            "HSN": str(r["hsn_code"]).split(".")[0] if pd.notna(r["hsn_code"]) else "",
            "Rate (%)": float(r["gst_rate"]),
            "Total Quantity": round(float(r["qty"]), 2),
            "Taxable Value": taxable,
            "Total Tax": tax,
        })
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(["HSN", "Rate (%)"]).reset_index(drop=True)
    return res


def overall_summary(data: pd.DataFrame, supplier_cd: str) -> dict:
    """Dashboard ke liye grand totals."""
    intra_mask = data["state_cd"] == supplier_cd
    total_taxable = round(float(data["signed_taxable"].sum()), 2)
    total_tax = round(float(data["signed_tax"].sum()), 2)
    intra_tax = round(float(data.loc[intra_mask, "signed_tax"].sum()), 2)
    inter_tax = round(float(data.loc[~intra_mask, "signed_tax"].sum()), 2)

    sales_ct = int((data["signed_taxable"] > 0).sum())
    return_ct = int((data["signed_taxable"] < 0).sum())

    return {
        "orders_net": sales_ct - return_ct,
        "sales_rows": sales_ct,
        "return_rows": return_ct,
        "total_taxable": total_taxable,
        "igst": inter_tax,            # inter-state tax = IGST
        "cgst": round(intra_tax / 2, 2),
        "sgst": round(intra_tax / 2, 2),
        "total_tax": total_tax,
        "invoice_value": round(total_taxable + total_tax, 2),
    }


def documents_issued(sales_df: pd.DataFrame,
                     return_df: pd.DataFrame | None) -> dict:
    """
    GSTR-1 Table 13 (Documents Issued) — carefully counted.

    Meesho data ki baareekiyaan jo yahan handle hoti hain:
      1. Ek invoice (sub_order_num) ki ek se zyada rows ho sakti hain —
         ek asli sale (qty>0) aur ek price-adjustment line (qty=0, taxable -ve).
         Ye SAME invoice hai, do nahi. Isliye unique sub_order_num ginte hain.
      2. Kuch invoices poore adjust/cancel ho jaate hain (net qty=0).
         GST mein invoice fir bhi ISSUE hui thi, to count hoti hai —
         par hum inhe alag 'fully_adjusted' mein bhi dikhate hain.
      3. Returns alag documents hain = Credit Notes (GSTR-1 Table 9B),
         NOT cancelled invoices. Inhe alag ginते hain.

    Returns dict:
      - invoices_issued   : unique invoices issued (Table 13 ka main number)
      - invoice_line_rows : total sales rows (line items, info ke liye)
      - adjustment_rows   : qty=0 wali adjustment lines
      - fully_adjusted    : invoices jinka net qty=0 (issue hui, value 0)
      - active_invoices   : invoices jinka net qty>0 (asli bikri)
      - credit_notes      : returns = credit notes (Table 9B)
      - net_documents     : invoices_issued - credit_notes
    """
    def _prep(df):
        if df is None or len(df) == 0:
            return None
        d = df.copy()
        d["quantity"] = pd.to_numeric(d.get("quantity"), errors="coerce").fillna(0)
        d["total_taxable_sale_value"] = pd.to_numeric(
            d.get("total_taxable_sale_value"), errors="coerce").fillna(0)
        return d

    s = _prep(sales_df)
    r = _prep(return_df)

    if s is None or "sub_order_num" not in s.columns:
        invoices_issued = int(len(s)) if s is not None else 0
        adjustment_rows = 0
        fully_adjusted = 0
        active_invoices = invoices_issued
        line_rows = invoices_issued
    else:
        line_rows = int(len(s))
        adjustment_rows = int((s["quantity"] == 0).sum())
        per_inv = s.groupby("sub_order_num").agg(
            net_qty=("quantity", "sum")).reset_index()
        invoices_issued = int(per_inv["sub_order_num"].nunique())
        fully_adjusted = int((per_inv["net_qty"] <= 0).sum())
        active_invoices = int((per_inv["net_qty"] > 0).sum())

    if r is None or "sub_order_num" not in r.columns:
        credit_notes = int(len(r)) if r is not None else 0
    else:
        credit_notes = int(r["sub_order_num"].dropna().astype(str).nunique())

    return {
        "invoices_issued": invoices_issued,
        "invoice_line_rows": line_rows,
        "adjustment_rows": adjustment_rows,
        "fully_adjusted": fully_adjusted,
        "active_invoices": active_invoices,
        "credit_notes": credit_notes,
        "net_documents": invoices_issued - credit_notes,
    }


def process(sales_path, return_path=None, supplier_fallback="07"):
    """
    High-level entry point. Paths ya file-like buffers leta hai.
    Returns dict: {b2c, hsn, summary, docs, supplier_cd, data}
    """
    sales_df = load_meesho_file(sales_path)
    return_df = load_meesho_file(return_path) if return_path is not None else None

    data = build_dataset(sales_df, return_df)
    supplier_cd = supplier_state_code(sales_df, fallback=supplier_fallback)

    return {
        "supplier_cd": supplier_cd,
        "b2c": b2c_summary(data, supplier_cd),
        "hsn": hsn_summary(data, supplier_cd),
        "summary": overall_summary(data, supplier_cd),
        "docs": documents_issued(sales_df, return_df),
        "data": data,
    }


def to_excel_bytes(result: dict) -> bytes:
    """
    Result ko ek multi-sheet Excel (bytes) mein badlo — download ke liye.
    Sheets: Summary, B2C (Others), HSN Summary.
    """
    import io
    buf = io.BytesIO()
    s = result["summary"]
    summary_df = pd.DataFrame([
        ("Net Orders", s["orders_net"]),
        ("Sales Rows", s["sales_rows"]),
        ("Return Rows", s["return_rows"]),
        ("Total Taxable Value", s["total_taxable"]),
        ("IGST (inter-state)", s["igst"]),
        ("CGST (intra-state)", s["cgst"]),
        ("SGST (intra-state)", s["sgst"]),
        ("Total Tax", s["total_tax"]),
        ("Total Invoice Value", s["invoice_value"]),
    ], columns=["Particular", "Value"])

    d = result.get("docs", {})
    docs_df = pd.DataFrame([
        ("Invoices Issued (Table 13)", d.get("invoices_issued", 0)),
        ("  — Active invoices (net qty > 0)", d.get("active_invoices", 0)),
        ("  — Fully adjusted/cancelled (net qty = 0)", d.get("fully_adjusted", 0)),
        ("Credit Notes / Returns (Table 9B)", d.get("credit_notes", 0)),
        ("Net Documents", d.get("net_documents", 0)),
        ("(info) Total sale line-rows", d.get("invoice_line_rows", 0)),
        ("(info) Price-adjustment rows (qty = 0)", d.get("adjustment_rows", 0)),
    ], columns=["Particular", "Count"])

    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        summary_df.to_excel(xw, sheet_name="Summary", index=False)
        result["b2c"].to_excel(xw, sheet_name="B2C (Others)", index=False)
        result["hsn"].to_excel(xw, sheet_name="HSN Summary", index=False)
        docs_df.to_excel(xw, sheet_name="Documents Issued", index=False)
    return buf.getvalue()
