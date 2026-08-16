# Bulk Listing Generator (Meesho + Flipkart)

Local Streamlit app that fills marketplace listing templates from a single form.

## Setup

```powershell
cd EcomScript
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` if you want optional AI / Supabase features:

```
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
```

## Run

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

Or without activating the venv:

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

Open http://localhost:8501

## Usage

1. Upload a blank **Meesho** or **Flipkart** `.xlsx` template.
2. The app detects the platform from column headers and maps fields automatically.
3. Fill colors, sizes, brand, prices, images, and template fields.
4. Generate → QC check → download `{Platform}_{style}_{n}.xlsx`.

## Project layout

| File | Role |
|------|------|
| `app.py` | Streamlit UI |
| `platform_config.py` | Platform detection + field aliases |
| `excel_utils.py` | Template read/write |
| `listing_builder.py` | Color×Size row generation |
| `qc_checker.py` | Pre-upload QC |
| `ai_helper.py` | Gemini helpers |
| `database.py` | Optional Supabase |
