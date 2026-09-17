# System Design POC — Bulk Listing Generator + Meesho Dashboard

> A Streamlit-based tool that does two things:
> 1. **Bulk Listing Generator** — creates product listings for Meesho/Flipkart (with AI + QC + deduplication).
> 2. **Meesho Dashboard** — pastes a curl from DevTools to show live Meesho data (returns, payments) and tracks the diff across refreshes.

This document was written by reading the actual code (`app.py`, `meesho_dashboard.py`, `ai_helper.py`, `qc_checker.py`, `database.py`) — not from guesses.

---

## 1. Overview (one line)

The user uploads a blank Meesho template Excel → fills data via form/AI → bulk listings are generated → QC check + duplicate check runs → the filled Excel is downloaded. Alongside, there's a dashboard that takes a curl from Meesho's internal API and renders live business data (returns, payouts).

---

## 2. High-Level Architecture

```
                          ┌───────────────────────────────────────────┐
                          │              STREAMLIT UI                   │
                          │   (app.py — main(), 2 tabs)                 │
                          │                                             │
                          │   ┌──────────────┐   ┌──────────────────┐  │
                          │   │ Listing Gen  │   │  Meesho Dashboard │  │
                          │   │  Tab         │   │  Tab              │  │
                          │   └──────┬───────┘   └────────┬──────────┘  │
                          └──────────┼────────────────────┼─────────────┘
                                     │                     │
              ┌──────────────────────┼─────────┐           │
              ▼                      ▼         ▼           ▼
       ┌────────────┐        ┌────────────┐ ┌────────┐  ┌────────────────┐
       │ ai_helper  │        │ qc_checker │ │database│  │ meesho_dashboard│
       │ (Gemini)   │        │ (rules)    │ │(Supabase)│ │ (curl runner)  │
       └─────┬──────┘        └────────────┘ └────┬───┘  └────────┬───────┘
             │                                    │               │
             ▼                                    ▼               ▼
     ┌───────────────┐                    ┌──────────────┐  ┌───────────────┐
     │ Google Gemini │                    │  Supabase    │  │ Meesho private │
     │  API          │                    │  (Postgres)  │  │ APIs (HTTP)    │
     └───────────────┘                    └──────────────┘  └──────┬────────┘
                                                                    │
                                                            ┌───────▼────────┐
                                                            │ snapshots/*.json│
                                                            │ (diff tracking) │
                                                            └────────────────┘
```

---

## 3. Components (who does what)

| Module | Responsibility | Key Functions |
|---|---|---|
| `app.py` | UI orchestration + generation logic. Template parse → form → row build → QC → dedup → download. | `main()`, `run_generator()`, `inject_data()`, `gen_title()`, `gen_sku()` |
| `ai_helper.py` | Titles, descriptions, field suggestions and image analysis via Google Gemini. Stateless wrappers. | `ai_generate_titles()`, `ai_generate_description()`, `ai_analyze_image()`, `ai_suggest_fields()` |
| `qc_checker.py` | Validates Meesho rules before upload (pure functions, no I/O). | `run_qc_check()` → `(errors, warnings)` |
| `database.py` | Supabase (Postgres) integration — duplicate check, listings save, profiles CRUD. | `check_duplicates()`, `save_listings()`, `save_profile_cloud()` |
| `meesho_dashboard.py` | DevTools curl → HTTP request → auto-pagination → flatten → diff vs snapshot → render. | `parse_curl()`, `run_curl()`, `_compute_diff()`, `_render_returns()`, `_render_payments()` |

Design principle visible in the code: **layers are separated** — the UI (`app.py`) is decoupled from business rules (`qc_checker`) and external calls (`ai_helper`, `database`, `meesho_dashboard`). QC and curl parsing are pure/deterministic, which makes them easy to test.

---

## 4. Data Flow — Flow A: Listing Generation

```
1. User uploads blank template (.xlsx)
        │
        ▼
2. Template parsing (openpyxl)
   find_data_sheet → find_header_row → get_col_map → get_dropdowns → get_compulsory
   (auto-detects the Meesho template layout)
        │
        ▼
3. [optional] Product image upload → ai_analyze_image() → form auto-fill
   (dropdown values are passed to the AI as constraints → only valid values come back)
        │
        ▼
4. User fills the form (colors, sizes, brand, price, images, template fields)
        │
        ▼
5. Row build loop:  for each color × size →
   - gen_title() / AI title  (strips restricted keywords)
   - gen_sku()  (random unique SKU)
   - Style ID per color, Group ID, prices (± variation), images (round-robin)
        │
        ▼
6. run_qc_check(rows)  →  errors + warnings
   (same-name-per-group, unique variation, price rules, banned keywords, image URL format...)
        │
        ▼
7. check_duplicates(Supabase)  →  auto-regenerate duplicate SKUs, flag style/image dupes
        │
        ▼
8. inject_data(wb2, rows) → filled Excel → download button
        │
        ▼
9. save_listings(Supabase)  (if QC passes)  → store for future dedup
```

**Idempotency / safety notes (from the code):**
- SKU IDs are random; if a duplicate is found, it's regenerated.
- If QC fails, nothing is saved to the DB (`if db_client and not qc_errors`).
- If Supabase is down/unconfigured, profiles fall back to local (`profiles.json`).

---

## 5. Data Flow — Flow B: Meesho Dashboard (curl-driven)

```
1. User copies a curl from Meesho DevTools and pastes it into meesho_curl.txt under a [label]
        │
        ▼
2. _load_curl_blocks()  →  {label: curl_string}   (multiple APIs in one file)
        │
        ▼
3. parse_curl()  →  {method, url, headers, data}   (shlex-based, handles -H / -b / --data-raw)
        │
        ▼
4. run_curl()  →  HTTP request (requests lib)
   AUTO-PAGINATION: if total_pages > 1 + cursor exists, fetches all pages and merges data[]
        │
        ▼
5. _find_records() → extracts the largest list-of-dicts from the response (generic flattener)
        │
        ▼
6. _compute_diff(label, records)  vs  meesho_snapshots/<label>.json
   → what's new, what's removed, how much the count changed
        │
        ▼
7. _save_snapshot(label, records)   (baseline for the next refresh)
        │
        ▼
8. Render:
   - returns  → _render_returns()   (RTO vs Customer Return sub-tabs)
   - payments → _render_payments()  (previous / upcoming, mode auto-detected)
```

**Detection logic (label-agnostic too):** `_is_returns_data()` (RTO/RET in the `type` field) and `_is_daywise_payments()` (`daywisePayments` key) auto-pick the view, rather than relying only on the label.

---

## 6. Tech Stack & Reasons

| Layer | Choice | Reason (evident from code) |
|---|---|---|
| UI / App | **Streamlit** | Single-file rapid UI; form + tabs + file upload built in. Good fit for an internal tool. |
| Excel | **openpyxl** | Needs to read/write Meesho's complex multi-sheet template (validation + fill sheets). |
| AI | **Google Gemini** (`google-genai`, `gemini-3-flash-preview`) | Title/description generation + image → attributes. Degrades gracefully if no key. |
| DB | **Supabase (Postgres)** | Cloud dedup store + profiles. `image_urls TEXT[]` + GIN index makes URL dedup fast. |
| Dashboard data | **requests + curl parsing** | Meesho gives no public API; reuse the DevTools curl to call it with auth cookies. |
| Diff store | **Local JSON snapshots** | Simple, serverless diff tracking — no DB needed for refresh comparison. |

---

## 7. Data Model (Supabase)

```sql
-- listings: for deduplication
listings(
  id, style_id, sku_id, product_name, brand, color,
  category, image_urls TEXT[], catalog_name, created_at, status
)
  INDEX(style_id), INDEX(sku_id), GIN(image_urls)

-- profiles: reusable form presets (cloud)
profiles(name PRIMARY, data JSONB)   -- upsert on name
```

Snapshot file (per dashboard label):
```json
{ "timestamp": "...", "keys": ["order_num_1", "awb_2", ...] }
```

---

## 8. Failure Modes & Handling (observed in code)

| Failure | Handling |
|---|---|
| Gemini key missing / API fails | `get_client()` returns None → AI features silently skipped, manual fill still works. |
| Supabase config missing | Local `profiles.json` fallback; dedup skipped. |
| Meesho session/cookie expired (401/403) | Dashboard shows an error → the user is asked for a fresh curl. |
| Curl parse fails (unbalanced quotes) | `shlex` fails → falls back to token split. |
| Pagination cursor missing | Loop breaks, returns whatever records were fetched. |
| QC errors | Generation is shown but DB save is blocked. |

---

## 9. POC Scope vs Production Gaps (honest)

**In the POC:**
- End-to-end listing generation + QC + dedup + download.
- Live dashboard with diff tracking + auto-pagination.

**Pending for production (if scaling up):**
- Auth/multi-user (currently single supplier `wafhp`/`4789817` hardcoded-style).
- Curl-based auth is fragile — cookie expiry is manual. No proper token refresh.
- Secrets live in `.env` — a secret manager would be better.
- No background jobs — everything is synchronous on the UI thread (can be slow on large catalogs).
- Snapshots are in local files — a multi-instance deploy would need a shared store.
- Minimal retry/rate-limit handling around Gemini calls.

---

## 10. One-Slide Summary (for a presentation)

- **Problem:** Bulk listing on Meesho is manual and error-prone; and sellers get no live view of returns/payouts.
- **Solution:** A template-aware generator (AI + QC + dedup) + a curl-driven live dashboard with diff.
- **Architecture:** Streamlit UI → 4 clean modules (AI / QC / DB / Dashboard) → Gemini + Supabase + Meesho API.
- **Why it works:** business rules sit in a pure-function layer, external calls are isolated, graceful degradation everywhere.
- **Next:** auth, token refresh, async jobs, shared snapshot store.
