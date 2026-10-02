"""Presentation helpers: global CSS, KPI cards, alert banners and formatted tables."""

from __future__ import annotations

import html
import math

import numpy as np
import pandas as pd
import streamlit as st

CSS = """
<style>
:root {
  --ps-ink: #0b0b0b; --ps-ink-2: #52514e; --ps-muted: #6f6d68;
  --ps-line: rgba(11,11,11,0.10); --ps-card: #ffffff; --ps-brand: #1c5cab;
  --ps-critical: #d03b3b; --ps-serious: #ec835a; --ps-warning: #fab219; --ps-good: #0ca30c; --ps-info: #2a78d6;
  --ps-nav-active: #1c5cab; --ps-nav-hover: rgba(28,92,171,0.09);
}
.block-container { padding-top: 3.6rem; padding-bottom: 3rem; max-width: 1480px; }
h1, h2, h3 { letter-spacing: -0.01em; }

.ps-header { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; flex-wrap:wrap;
  border-bottom:1px solid var(--ps-line); padding-bottom:12px; margin-bottom:18px; }
.ps-header h1 { font-size:1.75rem; margin:0; padding:0; color:var(--ps-ink); }
.ps-header .ps-sub { color:var(--ps-muted); font-size:0.92rem; margin-top:4px; }
.ps-chip { display:inline-block; font-size:0.78rem; padding:3px 10px; border-radius:999px;
  background:rgba(28,92,171,0.08); color:var(--ps-brand); border:1px solid rgba(28,92,171,0.18); margin-left:6px; }
.ps-chip.sample { background:rgba(250,178,25,0.14); color:#7a5200; border-color:rgba(250,178,25,0.4); }

.ps-kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(190px, 1fr)); gap:12px; margin:4px 0 18px; }
.ps-kpi { background:var(--ps-card); border:1px solid var(--ps-line); border-radius:12px; padding:14px 16px 12px;
  border-top:3px solid var(--ps-info); box-shadow:0 1px 2px rgba(11,11,11,0.04); }
.ps-kpi.critical { border-top-color:var(--ps-critical); }
.ps-kpi.serious { border-top-color:var(--ps-serious); }
.ps-kpi.warning { border-top-color:var(--ps-warning); }
.ps-kpi.good { border-top-color:var(--ps-good); }
.ps-kpi.neutral { border-top-color:#c3c2b7; }
.ps-kpi .lbl { font-size:0.78rem; font-weight:600; text-transform:uppercase; letter-spacing:0.04em; color:var(--ps-muted); }
.ps-kpi .val { font-size:1.65rem; font-weight:700; color:var(--ps-ink); margin-top:4px; line-height:1.15; }
.ps-kpi .sub { font-size:0.82rem; color:var(--ps-ink-2); margin-top:4px; }
.ps-kpi .tag { display:inline-block; font-size:0.72rem; font-weight:600; margin-top:6px; padding:1px 8px; border-radius:6px; }
.ps-kpi.critical .tag { background:rgba(208,59,59,0.10); color:#a32424; }
.ps-kpi.serious .tag { background:rgba(236,131,90,0.14); color:#9a4418; }
.ps-kpi.warning .tag { background:rgba(250,178,25,0.16); color:#7a5200; }
.ps-kpi.good .tag { background:rgba(12,163,12,0.10); color:#006300; }

.ps-alert { display:flex; gap:12px; align-items:flex-start; border-radius:10px; padding:12px 16px; margin:0 0 10px;
  border:1px solid var(--ps-line); border-left-width:5px; background:#fff; }
.ps-alert .ic { font-size:1.25rem; line-height:1.3; }
.ps-alert .tt { font-weight:700; color:var(--ps-ink); }
.ps-alert .bd { color:var(--ps-ink-2); font-size:0.92rem; margin-top:2px; }
.ps-alert.critical { border-left-color:var(--ps-critical); background:#fdf1f1; }
.ps-alert.serious { border-left-color:var(--ps-serious); background:#fdf4ef; }
.ps-alert.warning { border-left-color:var(--ps-warning); background:#fef9ec; }
.ps-alert.info { border-left-color:var(--ps-info); background:#f1f6fd; }
.ps-alert.good { border-left-color:var(--ps-good); background:#f0f9f0; }

.ps-section { font-size:1.05rem; font-weight:700; color:var(--ps-ink); margin:18px 0 2px; }
.ps-section-sub { font-size:0.86rem; color:var(--ps-muted); margin-bottom:8px; }
.ps-callout { background:#f4f7fb; border:1px solid rgba(28,92,171,0.15); border-radius:10px; padding:12px 16px;
  font-size:0.9rem; color:var(--ps-ink-2); margin:6px 0 14px; }
.ps-callout b { color:var(--ps-ink); }

section[data-testid="stSidebar"] .ps-brand { display:flex; gap:10px; align-items:center; margin:-8px 0 22px; min-height:44px; }
section[data-testid="stSidebar"] .ps-brand .logo { width:38px; height:38px; border-radius:10px; background:#1c5cab;
  color:#fff; display:flex; align-items:center; justify-content:center; font-size:20px; }
section[data-testid="stSidebar"] .ps-brand .nm { font-weight:800; font-size:1.2rem; color:#0b0b0b; line-height:1.1; }
section[data-testid="stSidebar"] .ps-brand .tg { font-size:0.75rem; color:#6f6d68; }
section[data-testid="stSidebar"] .ps-source { font-size:0.8rem; color:#52514e; background:#fff; border:1px solid var(--ps-line);
  border-radius:8px; padding:8px 10px; margin-bottom:8px; }

/* The scroll-reset helper is a zero-height components.html iframe; keep it
   in the flow so its script still runs, but take up no space.            */
div[data-testid="stElementContainer"]:has(> iframe[data-testid="stCustomComponentV1"]) {
  height:0 !important; min-height:0 !important;
  margin:0 !important; padding:0 !important; overflow:hidden; }
iframe[data-testid="stCustomComponentV1"] { border:0; }

/* --- Sidebar navigation --------------------------------------------------
   Each page is an st.button; row spacing comes from the container's native
   gap. Targeted by .stButton rather than the container key, and the layout
   properties carry !important so Streamlit's own button styles cannot win.
   st.download_button renders as .stDownloadButton, so the Excel button in
   the sidebar is not affected.                                           */
section[data-testid="stSidebar"] .stButton { width:100%; margin:0; }
section[data-testid="stSidebar"] .stButton > button {
  display:flex !important; align-items:center !important;
  justify-content:flex-start !important; text-align:left !important;
  width:100%; min-height:44px; padding:11px 14px !important; margin:0;
  border-radius:10px; border:1px solid transparent !important;
  background:transparent; box-shadow:none !important;
  color:var(--ps-ink-2); font-size:0.92rem; font-weight:500; line-height:1.3;
  transition:background-color .15s ease, color .15s ease; }
/* the label markup inside the button must not re-centre itself */
section[data-testid="stSidebar"] .stButton > button > div,
section[data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] {
  width:100%; text-align:left !important; justify-content:flex-start !important;
  color:inherit; }
section[data-testid="stSidebar"] .stButton > button p {
  margin:0; text-align:left !important;
  font-size:inherit; font-weight:inherit; color:inherit; }

section[data-testid="stSidebar"] .stButton > button:hover {
  background:var(--ps-nav-hover); color:var(--ps-brand); }
section[data-testid="stSidebar"] .stButton > button:focus-visible {
  border-color:var(--ps-brand) !important; }

/* active page */
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .stButton > button[data-testid$="-primary"],
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
section[data-testid="stSidebar"] .stButton > button[data-testid$="-primary"]:hover,
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:focus,
section[data-testid="stSidebar"] .stButton > button[data-testid$="-primary"]:focus {
  background:var(--ps-nav-active); border-color:var(--ps-nav-active) !important;
  color:#fff; font-weight:600; }
</style>
"""

ICONS = {"critical": "⛔", "serious": "⚠️", "warning": "⏳", "info": "ℹ️", "good": "✅"}


def inject_css() -> None:
    st.html(CSS)


def money(v: float | None, cur: str, decimals: int = 0) -> str:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "–"
    a = abs(v)
    if a >= 1_000_000:
        return f"{cur}{v / 1_000_000:,.2f}M"
    if a >= 100_000:
        return f"{cur}{v / 1_000:,.1f}K"
    return f"{cur}{v:,.{decimals}f}"


def num(v: float | None, decimals: int = 0, suffix: str = "") -> str:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "–"
    return f"{v:,.{decimals}f}{suffix}"


def header(title: str, subtitle: str, source: str, is_sample: bool) -> None:
    chip = f'<span class="ps-chip{" sample" if is_sample else ""}">{html.escape(source)}</span>'
    st.markdown(
        f'<div class="ps-header"><div><h1>{html.escape(title)}</h1>'
        f'<div class="ps-sub">{subtitle}{chip}</div></div></div>',
        unsafe_allow_html=True,
    )


def kpi_cards(cards: list[dict]) -> None:
    """cards: dicts with label, value, optional sub, tone (critical|serious|warning|good|info|neutral), tag."""
    parts = []
    for c in cards:
        tone = c.get("tone", "info")
        tag = f'<div class="tag">{html.escape(c["tag"])}</div>' if c.get("tag") else ""
        sub = f'<div class="sub">{c["sub"]}</div>' if c.get("sub") else ""
        title = html.escape(c.get("help", ""), quote=True)
        parts.append(
            f'<div class="ps-kpi {tone}" title="{title}"><div class="lbl">{html.escape(c["label"])}</div>'
            f'<div class="val">{html.escape(str(c["value"]))}</div>{sub}{tag}</div>'
        )
    st.markdown(f'<div class="ps-kpis">{"".join(parts)}</div>', unsafe_allow_html=True)


def alert(kind: str, title: str, body: str = "") -> None:
    icon = ICONS.get(kind, "ℹ️")
    st.markdown(
        f'<div class="ps-alert {kind}" role="alert"><div class="ic">{icon}</div><div>'
        f'<div class="tt">{title}</div><div class="bd">{body}</div></div></div>',
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str = "") -> None:
    sub = f'<div class="ps-section-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="ps-section">{title}</div>{sub}', unsafe_allow_html=True)


def callout(body: str) -> None:
    st.markdown(f'<div class="ps-callout">{body}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

LABELS = {
    "Drug_ID": "Drug ID", "Drug_Name": "Drug", "Generic_Name": "Generic", "Strength": "Strength",
    "Dosage_Form": "Form", "Therapeutic_Category": "Category", "Drug_Class": "Class", "VEN_Class": "VEN",
    "Storage_Type": "Storage", "Batch_No": "Batch / Lot", "Expiry_Date": "Expiry", "Days_To_Expiry": "Days to expiry",
    "Expiry_Bucket": "Expiry window", "Qty_On_Hand": "Qty on hand", "Usable_Qty": "Usable qty",
    "Expired_Qty": "Expired qty", "Unit_Cost": "Unit cost", "Stock_Value": "Stock value", "Usable_Value": "Usable value",
    "Projected_Unsold_Qty": "Projected unsold qty", "Projected_Loss_Value": "Projected loss",
    "Recommended_Action": "Recommended action", "Compliance_Flags": "Compliance flags", "Location": "Location",
    "Supplier": "Supplier", "Units_Sold_90D": "Sold (90 d)", "Avg_Daily_Usage": "Avg daily use",
    "Days_On_Hand": "Days on hand", "Turnover_Annual": "Turnover (×/yr)", "Days_Since_Last_Sale": "Days since last sale",
    "Last_Sale_Date": "Last sale", "Movement_Class": "Movement", "Slow_Moving_Value": "Tied-up value",
    "Stock_Status": "Status", "Reorder_Point": "Reorder point", "ROP_Source": "ROP source",
    "Safety_Stock": "Safety stock", "Lead_Time_Days": "Lead time (d)", "Suggested_Order_Qty": "Suggested order qty",
    "Suggested_Order_Value": "Order value", "Priority": "Priority", "Projected_Stockout_Date": "Projected stockout",
    "Target_Max_Qty": "Target max qty", "Excess_Qty": "Excess qty", "Excess_Value": "Excess value",
    "Seasonal": "Seasonal", "Annual_Usage_Value": "Annual consumption value", "Cum_Value_Pct": "Cumulative %",
    "ABC_Class": "ABC", "ABC_VEN": "ABC-VEN", "ABC_VEN_Category": "Matrix category", "Batches": "Batches",
    "Nearest_Expiry": "Nearest expiry", "Daily_Revenue_At_Risk": "Daily revenue at risk",
    "Manufacture_Date": "Manufactured", "Expired_Value": "Expired value",
}

MONEY_COLS = {"Unit_Cost", "Stock_Value", "Usable_Value", "Projected_Loss_Value", "Slow_Moving_Value",
              "Suggested_Order_Value", "Excess_Value", "Annual_Usage_Value", "Daily_Revenue_At_Risk", "Expired_Value"}
QTY_COLS = {"Qty_On_Hand", "Usable_Qty", "Expired_Qty", "Projected_Unsold_Qty", "Units_Sold_90D", "Reorder_Point",
            "Safety_Stock", "Suggested_Order_Qty", "Target_Max_Qty", "Excess_Qty", "Days_To_Expiry",
            "Days_Since_Last_Sale", "Lead_Time_Days", "Batches"}
DEC1_COLS = {"Avg_Daily_Usage", "Days_On_Hand", "Turnover_Annual", "Cum_Value_Pct"}
DATE_COLS = {"Expiry_Date", "Last_Sale_Date", "Projected_Stockout_Date", "Nearest_Expiry", "Manufacture_Date"}


def prepare(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    cols = [c for c in cols if c in df.columns]
    out = df[cols].copy()
    for c in out.columns:
        if pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].replace([np.inf, -np.inf], np.nan)
        if c == "Expiry_Bucket":
            out[c] = out[c].astype(str)
        if c == "Seasonal":
            out[c] = out[c].map({True: "Yes", False: "No"})
    return out


def table(df: pd.DataFrame, cols: list[str], cur: str, key: str, height: int | str = "auto",
          file_name: str | None = None, extra_config: dict | None = None) -> None:
    d = prepare(df, cols)
    if d.empty:
        st.info("No records match the current filters.")
        return
    cfg: dict = {}
    for c in d.columns:
        label = LABELS.get(c, c.replace("_", " "))
        if c in MONEY_COLS:
            cfg[c] = st.column_config.NumberColumn(label, format=f"{cur}%,.2f" if c == "Unit_Cost" else f"{cur}%,.0f")
        elif c in QTY_COLS:
            cfg[c] = st.column_config.NumberColumn(label, format="%,.0f")
        elif c in DEC1_COLS:
            cfg[c] = st.column_config.NumberColumn(label, format="%,.1f")
        elif c in DATE_COLS:
            cfg[c] = st.column_config.DateColumn(label, format="DD MMM YYYY")
        else:
            cfg[c] = st.column_config.TextColumn(label)
    if "Days_On_Hand" in d.columns:
        cfg["Days_On_Hand"] = st.column_config.NumberColumn(
            "Days on hand", format="%,.1f", help="Usable stock ÷ average daily usage. Blank = no recent demand.")
    if extra_config:
        cfg.update(extra_config)
    st.dataframe(d, hide_index=True, column_config=cfg, height=height, key=key, placeholder="–")
    export = d.rename(columns={c: LABELS.get(c, c) for c in d.columns})
    st.download_button(
        "Download CSV", export.to_csv(index=False).encode("utf-8"),
        file_name=file_name or f"pharmastock_{key}.csv", mime="text/csv", key=f"dl_{key}", icon=":material/download:",
    )
