# PharmaStock 💊

Inventory optimisation, compliance and visualisation for pharmacy and hospital stores. Upload a batch-level stock file (CSV or Excel) and get daily, prioritised decisions on:

| # | Module | What it answers |
| --- | --- | --- |
| 1 | **Slow-moving stock** | Which medicines are stagnating and tying up cash before they become a loss? |
| 2 | **Expiry & compliance** | What has expired or expires within 30/60/90 days, and which batches will expire on the shelf (FEFO projection)? Controlled-drug and cold-chain flags included. |
| 3 | **Overstock** | Where is cash tied up in excess (specialty biologics, cold chain, seasonal lines like flu vaccine)? |
| 4 | **Stockout risk** | Which Vital or high-demand items are out, or will run out before the next delivery? Prioritised reorder list with suggested quantities. |
| 5 | **ABC-VEN matrix** | Value (ABC) × clinical criticality (Vital/Essential/Non-essential) → control categories I/II/III. |
| 6 | **Turnover, DOH & availability** | Annual turnover, days on hand, and stock availability overall and for Vital items. |

---

## Project structure

```text
Stockera_v1/
├── app.py                        # Streamlit app: pages, sidebar, layout, free/paid states
├── auth.py                       # Email + password sign-in, sessions, admin CLI
├── token_counter.py              # Persistent 5,000-token monthly budget per paid user
├── agents.py                     # AI Action Plan (Claude): prompt, urgent-issue check, saved plans
├── export_utils.py               # PDF / PPTX / DOCX / XLSX report export with charts
├── config.py                     # Environment settings, .env loading, SQLite schema
├── Dockerfile · docker-compose.yml · .env.example
├── requirements.txt
├── README.md
├── .streamlit/config.toml        # Theme + upload size
├── assets/guide.html             # How-to-Use & Compliance Guide (also shown in-app)
├── sample_data/pharmastock_sample.csv
└── pharmastock/
    ├── schema.py                 # File loading, header mapping, cleaning, data-quality report
    ├── analytics.py              # All inventory calculations (batch + SKU level)
    ├── charts.py                 # Plotly figures
    ├── ui.py                     # KPI cards, alerts, formatted tables
    ├── exports.py                # Multi-sheet Excel action report
    └── sample_data.py            # Sample dataset generator
```

---

## Setup in VS Code (Windows)

### Prerequisites

- **Python 3.10 or newer** (tested on 3.14). Check with `python --version`.
- **VS Code** with the **Python** extension (ms-python.python).

### Quickest way: one command, any terminal

The launchers create `.venv`, install the requirements on first run, and start the app. You don't need to activate anything.

| Terminal | Command |
| --- | --- |
| **Git Bash** | `./run.sh` |
| **PowerShell** | `.\run.bat` |
| **Command Prompt** | `run.bat` (or double-click `run.bat` in Explorer) |
| **VS Code** | Press **F5** (uses `.vscode/launch.json`) |

> **Which terminal am I in?** Look at the dropdown on the right of the VS Code terminal panel. Commands differ between terminals.
> In **Git Bash**, `.\.venv\Scripts\Activate.ps1` fails with `..venvScriptsActivate.ps1: command not found`, because bash treats `\` as an escape character and can't run PowerShell scripts. Use `source .venv/Scripts/activate` instead.

### 1. Open the folder

In VS Code: **File → Open Folder…** → select `Stockera_v1`.
Open a terminal: **Terminal → New Terminal** (Ctrl + backtick).
The included `.vscode/settings.json` points VS Code at `.venv`, so new terminals auto-activate it once the Python extension has loaded.

### 2. Create the virtual environment inside the folder

**Git Bash:**

```bash
python -m venv .venv
source .venv/Scripts/activate
```

**PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script ("running scripts is disabled"), allow it for your user once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

**Command Prompt (cmd):**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

When it's active, the prompt starts with `(.venv)`.

### 3. Install the dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Select the interpreter in VS Code

**Ctrl + Shift + P → "Python: Select Interpreter"** → choose `.\.venv\Scripts\python.exe`.
New terminals will then activate the environment automatically.

### 5. Run the app

```powershell
streamlit run app.py
```

Your browser opens at <http://localhost:8501>. Stop the app with **Ctrl + C** in the terminal.

If you get `streamlit: command not found`, the venv isn't active. Run Streamlit through the venv's Python directly:

```bash
.venv/Scripts/python.exe -m streamlit run app.py      # Git Bash
```

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py    # PowerShell
```

> **Miniconda/Anaconda users:** if your prompt shows `(base)`, a bare `python` or `pip` may point at conda instead of `.venv`. The launchers and the commands above always use `.venv`, so they avoid this.

### Troubleshooting

| Error | Cause | Fix |
| --- | --- | --- |
| `..venvScriptsActivate.ps1: command not found` | PowerShell command typed in Git Bash | `source .venv/Scripts/activate`, or use `./run.sh` |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | PowerShell execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `streamlit: command not found` | venv not active | Use a launcher, or `.venv/Scripts/python.exe -m streamlit run app.py` |
| `ModuleNotFoundError: No module named 'streamlit'` | Packages installed into a different Python (e.g. conda) | `.venv/Scripts/python.exe -m pip install -r requirements.txt` |
| `Port 8501 is already in use` | App already running in another terminal | Close the other terminal, or add `--server.port 8502` |

---

## Paid tier: AI Action Plan

The nine analysis pages and the Excel action report stay **free** and need no sign-in. Paid accounts sign in with email and password and unlock the **AI Action Plan** page: a meeting-ready, prioritised action list written by Claude (default model **Claude Haiku 4.5**) from the figures the app has already calculated.

Each plan, on screen and in every download (**PDF, PowerPoint, Word, Excel**), contains in this order:

1. **What your data says**: a two-sentence summary.
2. **Actionable recommendations**: 4–8 actions, most urgent first, each with impact, timeframe and the figure behind it.
3. **Reorder priorities**: the top 15 items to order (P1 first), with suggested quantity and value.
4. **Charts**: stock value by expiry window, SKU stock status, value by therapeutic category, ABC-VEN matrix.
5. **Filters and thresholds** used for the plan (one line at the end).

**Nothing urgent is left out.** Before each request, code lists every urgent issue in the data: Vital stockouts, expired stock, expired controlled drugs, Vital items that will run out before delivery, batches expiring within 30 days, unknown expiry dates and other stockouts. The AI must cover each one. Any it misses gets a recommendation added by code, labelled on screen as *added by the urgent-issue check*.

Only a compact summary goes to Anthropic's API: KPIs, the urgent-issue list and the top rows of each action list. The raw uploaded file is never sent. Users can see the exact text under **What is sent for AI analysis**.

### Token budget

Each paid user gets **5,000 tokens per calendar month (UTC)**. The count covers input and output. It is stored in `data/stockera.db`, so it survives restarts.

- On the sample data a plan costs about **2,950 tokens** with Haiku 4.5 (≈2,300 in, ≈650 written). **With the default allowance that is one plan a month.** Raise `MONTHLY_TOKEN_LIMIT` if that is too tight.
- Tokens are reserved before the request (the input is counted exactly with Anthropic's free token-counting endpoint). The output is capped at what remains, and the reservation is settled to the billed amount afterwards. Two tabs cannot overspend. A plan that cannot finish within the remaining allowance is refused **before** any tokens are spent.
- Every plan is saved, so it can be reopened and downloaded again at no token cost.
- To use a stronger model, set `ANTHROPIC_MODEL` (for example `claude-sonnet-5` or `claude-opus-5`). The app adds the `effort` setting and server-side fallback only for models that support them.

### Setup

1. Put your key in a `.env` file (never commit it; it is git- and docker-ignored):

   ```bash
   cp .env.example .env      # then edit: ANTHROPIC_API_KEY=sk-ant-...
   ```

   Setting `ANTHROPIC_API_KEY` as a real environment variable works too, and takes precedence over `.env`.

2. Create paid accounts. There is no self-service sign-up or payment integration yet:

   ```bash
   python auth.py add-user alice@example.com --tier paid     # prompts for a password (min 10 chars)
   python auth.py set-tier alice@example.com free            # downgrade
   python auth.py list                                       # accounts + this month's token usage
   ```

   Use `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (macOS) if the venv is not activated.

Security notes: passwords are stored as salted PBKDF2-SHA256 hashes, five failed sign-ins lock an email for 15 minutes, and sessions expire after 60 idle minutes. Sign-in lasts for the browser session, so a page refresh signs the user out. AI output is rendered with all HTML and markdown neutralised. The API key is only ever read from the environment.

### Docker (Windows and macOS)

Requires Docker Desktop (WSL 2 backend on Windows). The image builds natively for Intel/AMD and Apple Silicon.

```bash
cp .env.example .env                  # add ANTHROPIC_API_KEY
docker compose up -d --build          # http://localhost:8501
docker compose exec app python auth.py add-user alice@example.com --tier paid
```

Accounts, token usage and saved reports live in the `stockera-data` named volume and survive rebuilds. To publish one image for both architectures: `docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/stockera:latest --push .`

All settings (model, effort, limits, timeouts) are listed in [.env.example](.env.example).

---

## Using your own data

1. Open **📤 Data Upload & Quality** and download the **sample dataset** or the **blank template**.
2. Put **one row per batch/lot per location** in your file.
3. Upload it as CSV or `.xlsx`. The data-quality report lists anything that was fixed or needs attention.

**Required columns:** `Drug_Name`, `Batch_No`, `Expiry_Date`, `Qty_On_Hand`, `Unit_Cost`, `Units_Sold_90D`
(or `Avg_Daily_Usage` instead of `Units_Sold_90D`).

**Optional columns:** `Drug_ID`, `Generic_Name`, `Strength`, `Dosage_Form`, `Therapeutic_Category`, `Drug_Class` (Prescription-Only / Narcotic / OTC), `VEN_Class` (V/E/N), `Storage_Type` (Room Temperature / Cold Chain (2-8°C) / Frozen), `Manufacture_Date`, `Unit_Price`, `Last_Sale_Date`, `Lead_Time_Days`, `Reorder_Level`, `Max_Stock_Level`, `Supplier`, `Location`, `Seasonal` (Yes/No).

### Sample CSV (first rows — copy into a `.csv` file to test)

The full 63-row sample is in [sample_data/pharmastock_sample.csv](sample_data/pharmastock_sample.csv). Its dates were generated relative to 19 Sep 2026. The in-app **Reload built-in sample data** button regenerates them relative to today, so the demo scenarios never go stale.

```csv
Drug_ID,Drug_Name,Generic_Name,Strength,Dosage_Form,Therapeutic_Category,Drug_Class,VEN_Class,Storage_Type,Batch_No,Manufacture_Date,Expiry_Date,Qty_On_Hand,Unit_Cost,Unit_Price,Units_Sold_90D,Last_Sale_Date,Lead_Time_Days,Reorder_Level,Max_Stock_Level,Supplier,Location,Seasonal
PS-001,Paracetamol,Acetaminophen,500mg,Tablet,Analgesic,OTC,E,Room Temperature,PARA-2410-A,2024-10-14,2026-10-14,4000,0.02,0.05,3789,2026-09-19,7,,25000,MedSupply Distributors,Main Pharmacy,No
PS-003,Amoxicillin,Amoxicillin,500mg,Capsule,Anti-infective,Prescription-Only,V,Room Temperature,AMOX-2507-A,2025-07-16,2027-07-16,600,0.09,0.25,9000,2026-09-19,7,,,PharmaLink Wholesale,Main Pharmacy,No
PS-006,Lantus SoloStar,Insulin Glargine,100IU/mL,Pen,Endocrine,Prescription-Only,V,Cold Chain (2-8°C),LANT-2501-A,2025-01-17,2027-01-17,35,18.5,32.0,540,2026-09-19,10,,,ColdChain Biologics Ltd,Main Pharmacy,No
PS-007,NovoRapid FlexPen,Insulin Aspart,100IU/mL,Pen,Endocrine,Prescription-Only,V,Cold Chain (2-8°C),NOVO-2409-A,2024-09-14,2026-09-14,20,16.0,28.0,360,2026-09-18,10,,,ColdChain Biologics Ltd,Main Pharmacy,No
PS-014,Morphine Sulfate,Morphine,10mg/mL,Ampoule,Analgesic (Opioid),Narcotic,V,Room Temperature,MORP-2408-A,2024-08-30,2026-08-30,40,1.8,4.0,57,2026-09-19,7,,,Controlled Drugs Depot,ICU Satellite Store,No
PS-024,Influenza Vaccine QIV,Influenza vaccine (quadrivalent),0.5mL,Prefilled Syringe,Vaccine,Prescription-Only,E,Cold Chain (2-8°C),INFL-2603-A,2026-03-08,2027-03-08,1800,9.5,18.0,900,2026-09-19,21,,,National Vaccine Program,Main Pharmacy,Yes
PS-038,Humira,Adalimumab,40mg/0.4mL,Pen,Immunology (Biologic),Prescription-Only,E,Cold Chain (2-8°C),HUMI-2510-A,2025-10-24,2027-04-17,40,480.0,720.0,18,2026-09-15,14,,20,ColdChain Biologics Ltd,Main Pharmacy,No
PS-032,Multivitamin,Multivitamin,Adult,Tablet,Supplement,OTC,N,Room Temperature,MULT-2507-A,2025-07-06,2027-07-06,1200,0.06,0.2,0,2026-05-02,7,,,MedSupply Distributors,Main Pharmacy,No
```

### Defensive data handling

- **Flexible headers:** `Lot No`, `Batch`, `Expiry`, `Qty`, `Cost Price`, `Item Name`, `Schedule` and many other aliases map automatically.
- **Dates:** ISO, day-first (`31/03/2027`), month-first, Excel serial numbers, and pack-style `03/2027`, which is read as the **last day of the month**.
- **Numbers:** currency symbols, thousands separators and text are cleaned. Negatives become 0.
- **Missing values:** a missing expiry is kept and flagged "Unknown expiry" (never silently dropped). A missing batch is flagged as a recall-traceability gap. A missing VEN defaults to Essential and is flagged.
- **Bad files:** empty files, header-only files, missing required columns and corrupt Excel files show a clear message, and the previous dataset stays active.

---

## Key calculations

| Metric | Formula |
| --- | --- |
| ADU (average daily usage) | Units sold in 90 days ÷ 90, summed per SKU (drug × location) |
| Usable stock | Qty on hand excluding expired batches |
| Days on hand | Usable qty ÷ ADU |
| Turnover (annual) | ADU × 365 × unit cost ÷ usable stock value |
| Safety stock | ADU × safety days (V 14 · E 7 · N 3, configurable) |
| Reorder point | `Reorder_Level` if supplied, else ADU × lead time + safety stock |
| Suggested order | ADU × (lead time + cover days) + safety − usable, capped at `Max_Stock_Level` |
| Overstock excess | Usable − target max (`Max_Stock_Level`, else ADU × overstock days) |
| FEFO projected loss | Batch qty − max(0, ADU × days to expiry − qty of earlier-expiring batches) |
| ABC | Cumulative share of annual consumption value: A ≤ 80 %, B ≤ 95 %, C rest |
| ABC-VEN category | I: AV AE AN BV CV · II: BE CE BN · III: CN |
| Priority | Urgency (Out 3 · Critical 2 · Reorder 1) × VEN weight (V 3 · E 2 · N 1): P1 ≥ 6, P2 ≥ 3 |

All thresholds can be adjusted in the sidebar under **⚙️ Thresholds & settings**.

---

## Guide & reports

- **📘 How-to-Use & Compliance Guide**: in-app page, also a standalone file at [assets/guide.html](assets/guide.html) (double-click to open in a browser).
- **Excel action report** (sidebar): a summary plus expiry, reorder, overstock, slow-moving, ABC-VEN and full batch sheets. Keep a dated copy as compliance evidence.
- Every table has its own **Download CSV** button.

## Regenerating the sample CSV

```powershell
python -m pharmastock.sample_data
```

> PharmaStock is a decision-support tool. Final clinical and regulatory decisions remain with the responsible pharmacist. Follow your national regulator and controlled-drug legislation where they differ from the guidance here.
