# System Design POC — Bulk Listing Generator

> A Streamlit-based tool that creates product listings for Meesho/Flipkart (with AI + QC + deduplication).

This document was written by reading the actual code (`app.py`, `ai_helper.py`, `qc_checker.py`, `database.py`) — not from guesses.

---

## 1. Overview (one line)

The user uploads a blank Meesho template Excel → fills data via form/AI → bulk listings are generated → QC check + duplicate check runs → the filled Excel is downloaded.

---

## 2. High-Level Architecture

```
                          ┌───────────────────────────────────────────┐
                          │              STREAMLIT UI                   │
                          │   (app.py — main(), run_generator())        │
                          │                                             │
                          │   ┌──────────────────────────────────────┐ │
                          │   │        Listing Generator             │ │
                          │   └──────────────────┬───────────────────┘ │
                          └──────────────────────┼─────────────────────┘
                                                  │
              ┌───────────────────────┬──────────┴──────────┐
              ▼                       ▼                      ▼
       ┌────────────┐        ┌────────────┐          ┌────────────┐
       │ ai_helper  │        │ qc_checker │          │  database  │
       │ (Gemini)   │        │ (rules)    │          │ (Supabase) │
       └─────┬──────┘        └────────────┘          └─────┬──────┘
             │                                              │
             ▼                                              ▼
     ┌───────────────┐                              ┌──────────────┐
     │ Google Gemini │                              │  Supabase    │
     │  API          │                              │  (Postgres)  │
     └───────────────┘                              └──────────────┘
```

---

## 3. Components (who does what)

| Module | Responsibility | Key Functions |
|---|---|---|
| `app.py` | UI orchestration + generation logic. Template parse → form → row build → QC → dedup → download. | `main()`, `run_generator()`, `inject_data()`, `gen_title()`, `gen_sku()` |
| `ai_helper.py` | Titles, descriptions, field suggestions and image analysis via Google Gemini. Stateless wrappers. | `ai_generate_titles()`, `ai_generate_description()`, `ai_analyze_image()`, `ai_suggest_fields()` |
| `qc_checker.py` | Validates Meesho rules before upload (pure functions, no I/O). | `run_qc_check()` → `(errors, warnings)` |
| `database.py` | Supabase (Postgres) integration — duplicate check, listings save, profiles CRUD. | `check_duplicates()`, `save_listings()`, `save_profile_cloud()` |

Design principle visible in the code: **layers are separated** — the UI (`app.py`) is decoupled from business rules (`qc_checker`) and external calls (`ai_helper`, `database`). QC is pure/deterministic, which makes it easy to test.

---

## 4. Data Flow — Listing Generation

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

## 5. Tech Stack & Reasons

| Layer | Choice | Reason (evident from code) |
|---|---|---|
| UI / App | **Streamlit** | Single-file rapid UI; form + file upload built in. Good fit for an internal tool. |
| Excel | **openpyxl** | Needs to read/write Meesho's complex multi-sheet template (validation + fill sheets). |
| AI | **Google Gemini** (`google-genai`, `gemini-3-flash-preview`) | Title/description generation + image → attributes. Degrades gracefully if no key. |
| DB | **Supabase (Postgres)** | Cloud dedup store + profiles. `image_urls TEXT[]` + GIN index makes URL dedup fast. |

---

## 6. Data Model (Supabase)

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

---

## 7. Failure Modes & Handling (observed in code)

| Failure | Handling |
|---|---|
| Gemini key missing / API fails | `get_client()` returns None → AI features silently skipped, manual fill still works. |
| Supabase config missing | Local `profiles.json` fallback; dedup skipped. |
| QC errors | Generation is shown but DB save is blocked. |

---

## 8. POC Scope vs Production Gaps (honest)

**In the POC:**
- End-to-end listing generation + QC + dedup + download.

**Pending for production (if scaling up):**
- Auth/multi-user (currently single supplier style).
- Secrets live in `.env` — a secret manager would be better.
- No background jobs — everything is synchronous on the UI thread (can be slow on large catalogs).
- Minimal retry/rate-limit handling around Gemini calls.

---

## 9. One-Slide Summary (for a presentation)

- **Problem:** Bulk listing on Meesho is manual and error-prone.
- **Solution:** A template-aware generator (AI + QC + dedup).
- **Architecture:** Streamlit UI → 3 clean modules (AI / QC / DB) → Gemini + Supabase.
- **Why it works:** business rules sit in a pure-function layer, external calls are isolated, graceful degradation everywhere.
- **Next:** auth, async jobs, secret manager.
