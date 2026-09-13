"""
📊 Meesho Dashboard Module
DevTools se nikala curl parse karke Meesho API call karta hai aur
Profit / Loss / Upcoming Payments / Returns dikhata hai.

Curl storage file: meesho_curl.txt
  labels: [returns] (RTO + Customer Return), [payments], [orders]
"""

import re
import json
import shlex
import requests
import pandas as pd
import streamlit as st

CURL_FILE = "meesho_curl.txt"


# ─── CURL PARSING ──────────────────────────────────────────────────────────

def _load_curl_blocks(filepath=CURL_FILE):
    """
    meesho_curl.txt ko labels ke hisaab se blocks me tod deta hai.
    Returns dict {label: curl_string}.
    """
    try:
        with open(filepath, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return {}

    blocks = {}
    current_label = None
    buffer = []

    for line in lines:
        stripped = line.strip()
        # Label line like [payments]
        m = re.match(r"^\[([a-zA-Z0-9_-]+)\]\s*$", stripped)
        if m:
            if current_label is not None:
                blocks[current_label] = "\n".join(buffer).strip()
            current_label = m.group(1).lower()
            buffer = []
            continue
        # Skip comment lines (only outside curl — but keep inside data)
        if stripped.startswith("#") and not buffer:
            continue
        if current_label is not None:
            buffer.append(line.rstrip("\n"))

    if current_label is not None:
        blocks[current_label] = "\n".join(buffer).strip()

    # Drop empty blocks
    return {k: v for k, v in blocks.items() if v.strip()}


def parse_curl(curl_str):
    """
    curl command string ko parse karke request ke parts nikaalta hai.
    Returns dict: {method, url, headers, data}
    """
    if not curl_str or not curl_str.strip():
        return None

    # Join line continuations (\ at end of line)
    cleaned = re.sub(r"\\\s*\n", " ", curl_str.strip())
    # Normalize newlines to spaces
    cleaned = cleaned.replace("\n", " ")

    try:
        tokens = shlex.split(cleaned)
    except ValueError:
        # Fallback: shlex fail on unbalanced quotes
        tokens = cleaned.split()

    method = "GET"
    url = None
    headers = {}
    data = None

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "curl":
            i += 1
            continue
        elif tok in ("-X", "--request"):
            method = tokens[i + 1].upper()
            i += 2
        elif tok in ("-H", "--header"):
            h = tokens[i + 1]
            if ":" in h:
                key, _, val = h.partition(":")
                headers[key.strip()] = val.strip()
            i += 2
        elif tok in ("--data-raw", "--data", "-d", "--data-binary", "--data-urlencode"):
            data = tokens[i + 1]
            if method == "GET":
                method = "POST"
            i += 2
        elif tok in ("-b", "--cookie"):
            headers["Cookie"] = tokens[i + 1]
            i += 2
        elif tok == "--url":
            url = tokens[i + 1]
            i += 2
        elif tok.startswith("http"):
            url = tok
            i += 1
        elif tok in ("--compressed", "--location", "-L", "-s", "--silent",
                     "-i", "--include", "-k", "--insecure", "-v", "--verbose"):
            i += 1
        else:
            # Unknown flag with value, or a stray token
            if tok.startswith("-") and i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                i += 2
            else:
                i += 1

    return {"method": method, "url": url, "headers": headers, "data": data}


def _do_request(parsed, timeout=30):
    """Ek single HTTP request bhejta hai. Returns parsed JSON (or text)."""
    resp = requests.request(
        method=parsed["method"],
        url=parsed["url"],
        headers=parsed["headers"],
        data=parsed["data"].encode("utf-8") if parsed["data"] else None,
        timeout=timeout,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"_raw_text": resp.text}


def run_curl(curl_str, timeout=30, max_pages=50):
    """
    Parse curl and execute the HTTP request. Returns parsed JSON (or text).

    AUTO-PAGINATION: agar response me `total_pages > 1` ho (Meesho returns/orders
    jaise cursor-based APIs), to saare pages laake sab records jod deta hai.
    Isliye 50/100/500 kitne bhi records hon, sab aa jaayenge — `size` badhane ki
    zaroorat nahi. Raises exception on failure.
    """
    parsed = parse_curl(curl_str)
    if not parsed or not parsed.get("url"):
        raise ValueError("Curl me valid URL nahi mila. Curl dobara check karo.")

    first = _do_request(parsed, timeout=timeout)

    # Sirf JSON dict responses me pagination possible hai
    if not isinstance(first, dict):
        return first

    total_pages = first.get("total_pages")
    cursor = first.get("cursor")
    # Pagination tabhi jab total_pages > 1 aur next cursor mile
    if not (isinstance(total_pages, int) and total_pages > 1 and cursor):
        return first

    # Base request body ko parse karo taaki cursor/page_pointer inject kar sakein
    try:
        base_body = json.loads(parsed["data"]) if parsed["data"] else {}
    except (ValueError, TypeError):
        return first  # body JSON nahi hai — pagination skip

    all_data = list(first.get("data", []) or [])
    next_cursor = cursor
    filter_cursor = first.get("filter_cursor")

    for _ in range(2, min(total_pages, max_pages) + 1):
        if not next_cursor:
            break
        body = dict(base_body)
        body["cursor"] = next_cursor
        # page_pointer / filter_cursor bhi bhejo agar API expect karta hai
        if "page_pointer" in base_body or True:
            body["page_pointer"] = next_cursor
        if filter_cursor:
            body["filter_cursor"] = filter_cursor

        page_parsed = dict(parsed)
        page_parsed["data"] = json.dumps(body)
        try:
            page = _do_request(page_parsed, timeout=timeout)
        except Exception:
            break
        if not isinstance(page, dict):
            break
        page_records = page.get("data", []) or []
        if not page_records:
            break
        all_data.extend(page_records)
        next_cursor = page.get("cursor")
        filter_cursor = page.get("filter_cursor", filter_cursor)

    # Merged result — data[] me saare pages ke records
    merged = dict(first)
    merged["data"] = all_data
    merged["_pages_fetched"] = min(total_pages, max_pages)
    return merged


# ─── DATA FLATTENING ─────────────────────────────────────────────────────────

def _find_records(obj):
    """
    JSON response me se sabse bada list-of-dicts dhoondhta hai
    (jo aksar orders/payments ka data hota hai).
    """
    best = []

    def walk(node):
        nonlocal best
        if isinstance(node, list):
            if node and all(isinstance(x, dict) for x in node):
                if len(node) > len(best):
                    best = node
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)

    walk(obj)
    return best


def _to_number(val):
    """String/number ko float me convert karta hai. Fail hone par None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val)
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _sum_by_keywords(records, keywords):
    """
    Records me jin fields ke naam me diye keywords aate hain,
    unke numeric values ka total karta hai.
    Returns (total, matched_field_names).
    """
    total = 0.0
    matched = set()
    for rec in records:
        for key, val in rec.items():
            lk = key.lower()
            if any(kw in lk for kw in keywords):
                num = _to_number(val)
                if num is not None:
                    total += num
                    matched.add(key)
    return total, matched


# ─── CATEGORY CLASSIFICATION ─────────────────────────────────────────────────

# Label me ye keywords aaye to us block ka data in metrics me count hota hai.
EARNING_LABELS = ("order", "sale", "settlement", "payout", "earning")
UPCOMING_LABELS = ("payment", "outstanding", "upcoming", "pending", "future", "receivable")

EARNING_FIELD_KW = ["settlement", "payout", "earning", "profit", "net",
                    "final_settlement", "total_amount", "amount", "sale"]
LOSS_FIELD_KW = ["deduction", "penalty", "loss", "return", "claim",
                 "recovery", "charge", "commission", "fee"]
UPCOMING_FIELD_KW = ["upcoming", "pending", "outstanding", "future", "unpaid",
                     "receivable", "to_be_paid", "amount"]


def _classify(label):
    """Label ke naam se decide karta hai block kis metric me jaata hai."""
    l = label.lower()
    is_earning = any(k in l for k in EARNING_LABELS)
    is_upcoming = any(k in l for k in UPCOMING_LABELS)
    return is_earning, is_upcoming


# ─── SNAPSHOT & DIFF (difference dekhte rehna) ───────────────────────────────

import os
from datetime import datetime

SNAPSHOT_DIR = "meesho_snapshots"


def _record_key(rec):
    """Har record ke liye ek unique key — diff track karne ke liye."""
    for k in ("sub_order_identifier", "sub_order_num", "order_num", "awb",
              "transferId", "date", "id"):
        if rec.get(k):
            return str(rec[k])
    # Fallback: pura record ka hash
    return json.dumps(rec, sort_keys=True, default=str)[:200]


def _load_snapshot(label):
    """Pichla saved snapshot load karta hai. Returns dict or None."""
    path = os.path.join(SNAPSHOT_DIR, f"{label}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _save_snapshot(label, records):
    """Current data ko snapshot me save karta hai (keys + timestamp)."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    keys = [_record_key(r) for r in records]
    snap = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(records),
        "keys": keys,
    }
    try:
        with open(os.path.join(SNAPSHOT_DIR, f"{label}.json"), "w") as f:
            json.dump(snap, f)
    except Exception:
        pass


def _compute_diff(label, records):
    """
    Pichle snapshot se compare karke difference nikaalta hai.
    Returns dict: {prev_time, prev_count, new_keys, removed_keys, delta} or None.
    """
    prev = _load_snapshot(label)
    cur_keys = set(_record_key(r) for r in records)
    if prev is None:
        return {"first_time": True, "count": len(records)}
    prev_keys = set(prev.get("keys", []))
    return {
        "first_time": False,
        "prev_time": prev.get("saved_at", ""),
        "prev_count": prev.get("count", 0),
        "cur_count": len(records),
        "new_keys": cur_keys - prev_keys,
        "removed_keys": prev_keys - cur_keys,
        "delta": len(records) - prev.get("count", 0),
    }


def _render_diff(diff, key_to_rec, row_fn=None):
    """Diff ko UI me dikhata hai."""
    if diff is None:
        return
    if diff.get("first_time"):
        st.info(f"📸 Pehli baar data save hua ({diff['count']} records). "
                "Agli baar se difference dikhega.")
        return

    delta = diff["delta"]
    new_n = len(diff["new_keys"])
    rem_n = len(diff["removed_keys"])

    st.markdown(f"#### 🔍 Difference (pichhle refresh se — {diff['prev_time']})")
    d1, d2, d3 = st.columns(3)
    d1.metric("Total ab", diff["cur_count"], delta=delta)
    d2.metric("🆕 Naye aaye", new_n)
    d3.metric("✅ Hat gaye / complete", rem_n)

    if new_n and row_fn:
        with st.expander(f"🆕 {new_n} naye record", expanded=True):
            new_rows = [row_fn(key_to_rec[k]) for k in diff["new_keys"] if k in key_to_rec]
            if new_rows:
                st.dataframe(pd.DataFrame(new_rows), use_container_width=True,
                             hide_index=True)
    if rem_n:
        with st.expander(f"✅ {rem_n} record hat gaye (pichli baar the, ab nahi)"):
            st.write(list(diff["removed_keys"])[:50])


# ─── RETURNS (RTO vs CUSTOMER RETURN) ────────────────────────────────────────

def _is_returns_data(records):
    """Records Meesho returns API ke hain ya nahi — 'type' me RTO/RET dekho."""
    if not records:
        return False
    sample = records[0]
    return isinstance(sample, dict) and str(sample.get("type", "")).upper() in ("RTO", "RET")


def _returns_row(rec):
    """Ek return record ko clean flat dict me convert karta hai UI ke liye."""
    product = rec.get("product", {}) or {}
    imgs = product.get("image_urls", []) or []
    reason = rec.get("return_reason_details", {}) or {}
    created = str(rec.get("created_date_iso", ""))[:10]
    expected = str(rec.get("expected_delivery_date_iso", ""))[:10]
    return {
        "Image": imgs[0] if imgs else "",
        "Product": product.get("name", ""),
        "SKU": product.get("sku", ""),
        "Size": product.get("variation", ""),
        "Order No": rec.get("order_num", ""),
        "AWB": rec.get("awb", ""),
        "Courier": rec.get("carrier_name", ""),
        "Status": rec.get("shipment_status", ""),
        "Sub Type": rec.get("sub_type", ""),
        "Return Reason": reason.get("return_reason", ""),
        "Detail": reason.get("detailed_reason", ""),
        "Return Ship Fee": rec.get("return_shipping_fee", ""),
        "Created": created,
        "Expected Delivery": expected,
        "Track": rec.get("tracking_url", ""),
    }


def _render_returns(records, label="returns"):
    """RTO (Courier Return) aur RET (Customer Return) alag-alag dikhata hai."""
    rto = [r for r in records if str(r.get("type", "")).upper() == "RTO"]
    ret = [r for r in records if str(r.get("type", "")).upper() == "RET"]
    other = [r for r in records
             if str(r.get("type", "")).upper() not in ("RTO", "RET")]

    # Customer return ki total shipping fee (loss)
    ret_fee_total = sum(
        (_to_number(r.get("return_shipping_fee")) or 0.0) for r in ret
    )
    rto_fee_total = sum(
        (_to_number(r.get("return_shipping_fee")) or 0.0) for r in rto
    )

    st.markdown("### 📦 Returns Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚚 Courier Return (RTO)", len(rto))
    c2.metric("🙋 Customer Return", len(ret))
    c3.metric("💸 Return Ship Fee (Customer)", f"₹{ret_fee_total:,.0f}")
    c4.metric("📊 Total Returns", len(records))

    # ─── DIFFERENCE (pichhle refresh se) ─────────────────────────────────
    diff = _compute_diff(label, records)
    key_to_rec = {_record_key(r): r for r in records}
    _render_diff(diff, key_to_rec, row_fn=_returns_row)
    _save_snapshot(label, records)

    img_cfg = {"Image": st.column_config.ImageColumn("Image", width="small"),
               "Track": st.column_config.LinkColumn("Track", width="small")}

    sub_rto, sub_ret = st.tabs(
        [f"🚚 Courier Return / RTO ({len(rto)})",
         f"🙋 Customer Return ({len(ret)})"]
    )

    with sub_rto:
        st.caption("RTO = order customer tak nahi pahuncha, wapas aa raha hai.")
        if rto:
            df = pd.DataFrame([_returns_row(r) for r in rto])
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_config=img_cfg)
        else:
            st.info("Koi Courier Return (RTO) nahi mila.")

    with sub_ret:
        st.caption("Customer Return = customer ne product wapas kiya (return shipping fee lagti hai).")
        if ret:
            df = pd.DataFrame([_returns_row(r) for r in ret])
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_config=img_cfg)
        else:
            st.info("Koi Customer Return nahi mila.")

    if other:
        with st.expander(f"❓ Other ({len(other)})"):
            df = pd.DataFrame([_returns_row(r) for r in other])
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_config=img_cfg)

    return {
        "rto_count": len(rto),
        "ret_count": len(ret),
        "ret_fee_total": ret_fee_total,
        "rto_fee_total": rto_fee_total,
    }


# ─── PAYMENTS (payouts: previous + upcoming) ─────────────────────────────────

def _is_daywise_payments(full_response):
    """Response payments API ka hai ya nahi (daywisePayments key se)."""
    return isinstance(full_response, dict) and "daywisePayments" in full_response


def _payment_mode(label, curl_str):
    """Label ya curl URL se decide — 'upcoming' ya 'previous'."""
    hay = (label + " " + (curl_str or "")).lower()
    if "upcoming" in hay:
        return "upcoming"
    return "previous"


def _payment_row(rec):
    """Ek daywise payment ko clean flat dict me convert karta hai."""
    recovery = rec.get("netPlatformRecovery", {}) or {}
    comp = rec.get("netPlatformCompensation", {}) or {}
    date = str(rec.get("date", "") or rec.get("date_iso", ""))[:10]
    return {
        "Date": date,
        "Net Payment (₹)": _to_number(rec.get("netAmount")) or 0.0,
        "Order Amount (₹)": _to_number(rec.get("netOrderAmount")) or 0.0,
        "Deduction (₹)": _to_number(rec.get("platformRecovery")) or 0.0,
        "Ads Cost (₹)": _to_number(recovery.get("adsCost")) or 0.0,
        "Program Cost (₹)": _to_number(recovery.get("programCosts")) or 0.0,
        "Loan Settle (₹)": _to_number(recovery.get("loanSettlementAmount")) or 0.0,
        "Compensation (₹)": _to_number(rec.get("platformCompensation")) or 0.0,
        "Referral (₹)": _to_number(comp.get("referralAmount")) or 0.0,
        "Transfer ID": rec.get("transferId", ""),
    }


def _render_payments(full_response, label="prev_payments", mode="previous"):
    """
    Day-wise payments view. mode='previous' (jo mil chuke) ya
    mode='upcoming' (jo aane wale hain).
    """
    days = full_response.get("daywisePayments", []) or []
    header = full_response.get("header", {}) or {}
    payout_state = full_response.get("payoutState", {}) or {}
    updated_at = str(full_response.get("updatedAtTimestamp", ""))[:19]

    total_net = _to_number(header.get("netAmount")) or sum(
        (_to_number(d.get("netAmount")) or 0.0) for d in days)
    total_order = _to_number(header.get("netOrderAmount")) or sum(
        (_to_number(d.get("netOrderAmount")) or 0.0) for d in days)
    total_recovery = _to_number(header.get("platformRecovery")) or sum(
        (_to_number(d.get("platformRecovery")) or 0.0) for d in days)

    if mode == "upcoming":
        st.markdown("### ⏳ Upcoming Payments (jo aane wale hain)")
        net_label = "💵 Total Upcoming"
    else:
        st.markdown("### 💰 Previous Payments (jo mil chuke)")
        net_label = "💵 Total Received"

    p1, p2, p3, p4 = st.columns(4)
    p1.metric(net_label, f"₹{total_net:,.2f}")
    p2.metric("🧾 Order Amount", f"₹{total_order:,.2f}")
    p3.metric("📉 Deductions", f"₹{abs(total_recovery):,.2f}")
    p4.metric("📅 Payment Days", len(days))

    if updated_at:
        st.caption(f"🕐 Last updated: {updated_at.replace('T', ' ')}")

    state = payout_state.get("state", "")
    if state:
        if state.lower() == "unblocked":
            st.success(f"✅ Payout state: {state}")
        else:
            st.warning(f"⚠️ Payout state: {state}")

    # Difference (pichhle refresh se — transferId/date ke basis pe)
    diff = _compute_diff(label, days)
    key_to_rec = {_record_key(d): d for d in days}
    _render_diff(diff, key_to_rec, row_fn=_payment_row)
    _save_snapshot(label, days)

    if days:
        df = pd.DataFrame([_payment_row(d) for d in days])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Koi payment record nahi mila.")

    return {"total_net": total_net, "total_recovery": total_recovery}


# ─── RENDER ─────────────────────────────────────────────────────────────────

def render_dashboard():
    st.title("📊 Meesho Dashboard")
    st.caption("Profit / Loss / Upcoming Payments — Meesho DevTools curl se live data")

    blocks = _load_curl_blocks()

    with st.expander("⚙️ Curl status & help", expanded=not blocks):
        st.markdown(
            f"""
            **Curl file:** `{CURL_FILE}`

            Isme apne Meesho ke SAARE curl paste karo (DevTools → Network → request pe
            right click → Copy → Copy as cURL). Jitni chahe utni API calls (4-5 ya zyada).

            Har curl ke upar `[label]` lagao. Label me:
            - **payment / outstanding / upcoming** aaye → ⏳ Upcoming Payment me count
            - **order / sale / settlement** aaye → 💰 Earnings + 📉 Loss me count
            - baaki sab sirf table me dikhenge

            Naya curl chahiye to mujhe bhej dena — main label ke saath add kar dunga.
            """
        )
        if blocks:
            st.success(f"✅ {len(blocks)} curl block(s) mile: {', '.join(blocks.keys())}")
        else:
            st.warning("⚠️ Abhi koi curl save nahi hai. `meesho_curl.txt` me curl paste karo.")

    if st.button("🔄 Refresh Data"):
        st.rerun()

    if not blocks:
        st.info("👆 Curl add karke upar 'Refresh Data' dabao — data yahan dikhega.")
        return

    # ─── SAARE CURL BLOCKS RUN KARO ──────────────────────────────────────
    results = {}       # label -> records list
    raw_results = {}   # label -> full JSON response
    errors = {}        # label -> error message
    with st.spinner("🌐 Meesho APIs call kar raha hoon..."):
        for label, curl_str in blocks.items():
            try:
                data = run_curl(curl_str)
                raw_results[label] = data
                results[label] = _find_records(data)
            except Exception as e:
                errors[label] = str(e)

    for label, msg in errors.items():
        st.error(f"❌ `[{label}]` curl fail: {msg}")

    # ─── METRICS AGGREGATE ───────────────────────────────────────────────
    earning_total = 0.0
    loss_total = 0.0
    upcoming_total = 0.0
    returns_labels = set()
    payment_labels = set()

    for label, records in results.items():
        full = raw_results.get(label)
        # Payments API (previous + upcoming) — daywisePayments
        if _is_daywise_payments(full):
            payment_labels.add(label)
            continue
        if not records:
            continue
        # Returns data alag handle hota hai (RTO / Customer Return)
        if _is_returns_data(records):
            returns_labels.add(label)
            continue
        is_earning, is_upcoming = _classify(label)
        if is_earning:
            earning_total += _sum_by_keywords(records, EARNING_FIELD_KW)[0]
            loss_total += _sum_by_keywords(records, LOSS_FIELD_KW)[0]
        if is_upcoming:
            upcoming_total += _sum_by_keywords(records, UPCOMING_FIELD_KW)[0]

    # ─── FINANCIAL SUMMARY (agar orders/payments curl bhi ho) ────────────
    if earning_total or loss_total or upcoming_total:
        st.markdown("### 💹 Financial Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💰 Earnings / Profit", f"₹{earning_total:,.2f}")
        m2.metric("📉 Loss / Deductions", f"₹{loss_total:,.2f}")
        m3.metric("⏳ Upcoming Payment", f"₹{upcoming_total:,.2f}")
        net = earning_total - loss_total
        m4.metric("📊 Net", f"₹{net:,.2f}", delta=f"{'Profit' if net >= 0 else 'Loss'}")
        st.markdown("---")

    # ─── PAYMENTS SECTION (upcoming pehle, phir previous) ────────────────
    payment_sorted = sorted(
        payment_labels,
        key=lambda l: 0 if _payment_mode(l, blocks.get(l, "")) == "upcoming" else 1
    )
    for label in payment_sorted:
        mode = _payment_mode(label, blocks.get(label, ""))
        _render_payments(raw_results[label], label=label, mode=mode)
        st.markdown("---")

    # ─── RETURNS SECTION ─────────────────────────────────────────────────
    for label in returns_labels:
        _render_returns(results[label], label=label)
        st.markdown("---")

    # ─── BAAKI API KA DATA (generic tables + diff) ───────────────────────
    skip = returns_labels | payment_labels
    generic = {l: r for l, r in results.items() if l not in skip}
    if generic:
        st.markdown("### 🧾 Other API Data")
        for label, records in generic.items():
            with st.expander(f"📁 [{label}] — {len(records)} rows", expanded=False):
                if records:
                    diff = _compute_diff(label, records)
                    key_to_rec = {_record_key(r): r for r in records}
                    _render_diff(diff, key_to_rec)
                    _save_snapshot(label, records)
                    st.dataframe(pd.DataFrame(records), use_container_width=True)
                else:
                    st.info("Is API se list-type data nahi mila. Response structure alag ho sakta hai.")
