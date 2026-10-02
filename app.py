"""PharmaStock - Pharmacy inventory optimisation, compliance & visualisation.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import html
import math
import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import agents
import auth
import config
import token_counter
from pharmastock import __version__
from pharmastock import charts as ch
from pharmastock import ui
from pharmastock.analytics import ABC_VEN_CATEGORY_POLICY, Analysis, Settings, run_analysis
from pharmastock.exports import build_excel_report
from pharmastock.sample_data import sample_csv_bytes
from pharmastock.schema import (
    COLUMN_DESCRIPTIONS,
    REQUIRED_COLUMNS,
    DataLoadError,
    QualityReport,
    clean_dataset,
    load_file,
    template_frame,
)

st.set_page_config(
    page_title="PharmaStock · Pharmacy Inventory Intelligence",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parent
GUIDE_PATH = ROOT / "assets" / "guide.html"

PAGES = [
    "Executive Dashboard",
    "Data Upload & Quality",
    "Expiry & Compliance",
    "Slow-Moving Stock",
    "Overstock",
    "Stockout Risk & Reorder",
    "ABC-VEN Matrix",
    "Turnover, DOH & Availability",
    "AI Action Plan",
    "How-to-Use & Compliance Guide",
]
AI_PAGE = "AI Action Plan"
CURRENCIES = ["$", "€", "£", "Rs ", "₹", "AED ", "SAR ", "PKR ", "¥"]
VEN_NAMES = {"V": "Vital", "E": "Essential", "N": "Non-essential"}
PLOT_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}

ui.inject_css()


@st.cache_resource(show_spinner=False)
def _init_storage() -> bool:
    config.init_db()
    return True


_init_storage()
user = auth.current_user()


# ---------------------------------------------------------------------------
# Cached data pipeline
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=8)
def load_and_clean(content: bytes, name: str) -> tuple[pd.DataFrame, pd.DataFrame, QualityReport]:
    raw = load_file(content, name)
    clean, report = clean_dataset(raw)
    return raw, clean, report


@st.cache_data(show_spinner="Analysing inventory…", max_entries=16)
def analyse(df: pd.DataFrame, settings: Settings) -> Analysis:
    return run_analysis(df, settings)


@st.cache_data(show_spinner=False)
def sample_bytes(ref: date) -> bytes:
    return sample_csv_bytes(ref)


@st.cache_data(show_spinner=False, max_entries=4)
def excel_report(df: pd.DataFrame, settings: Settings, cur: str) -> bytes:
    return build_excel_report(analyse(df, settings), cur)


@st.cache_data(show_spinner=False)
def guide_html() -> str:
    try:
        text = GUIDE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"<!--GUIDE-START-->(.*)<!--GUIDE-END-->", text, flags=re.S)
    return m.group(1) if m else text


def use_sample() -> None:
    st.session_state["dataset"] = {
        "content": sample_bytes(date.today()),
        "name": "pharmastock_sample.csv",
        "label": "Built-in sample data",
        "is_sample": True,
    }


if "dataset" not in st.session_state:
    use_sample()


def _select_page(name: str) -> None:
    """Nav click handler. Runs before the rerun, so the script renders the
    new page once instead of starting a run that st.rerun() throws away."""
    st.session_state["page"] = name


def fmt_pct(v: float) -> str:
    return "–" if v is None or math.isnan(v) else f"{v:.1f}%"


def fmt_x(v: float, suffix: str = "×") -> str:
    return "–" if v is None or math.isnan(v) or math.isinf(v) else f"{v:.1f}{suffix}"


# ---------------------------------------------------------------------------
# Account (paid tier)
# ---------------------------------------------------------------------------

def login_form(key: str) -> None:
    """Email sign-in. Form submit buttons are used (not st.button) so the
    sidebar nav styling, which targets .stButton, does not apply to them."""
    with st.form(key, border=False, enter_to_submit=True):
        email = st.text_input("Email", key=f"{key}_email", autocomplete="email")
        password = st.text_input("Password", type="password", key=f"{key}_pw", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
    if submitted:
        try:
            auth.login(auth.authenticate(email, password))
        except auth.AuthError as exc:
            st.session_state["_auth_msg"] = str(exc)
        else:
            st.session_state.pop("_auth_msg", None)
        st.rerun()
    msg = st.session_state.get("_auth_msg")
    if msg:
        st.error(msg, icon=":material/lock:")


def sidebar_account() -> None:
    if user is None:
        with st.expander("🔐 Paid plan sign-in", expanded=False):
            login_form("login_sidebar")
        return
    plan = "Paid plan" if user.is_paid else "Free plan"
    body = f"👤 <b>{html.escape(user.email)}</b><br>{plan}"
    if user.is_paid:
        u = token_counter.get_usage(user.email)
        body += (f" · AI tokens {u.used:,} / {u.limit:,}"
                 f'<div style="height:6px;border-radius:3px;background:rgba(11,11,11,.08);margin-top:6px">'
                 f'<div style="height:6px;border-radius:3px;width:{u.fraction * 100:.0f}%;'
                 f'background:{"#d03b3b" if u.fraction >= 0.9 else "#1c5cab"}"></div></div>')
    st.markdown(f'<div class="ps-source">{body}</div>', unsafe_allow_html=True)
    with st.form("logout_form", border=False):
        if st.form_submit_button("Sign out", width="stretch"):
            auth.logout()
            st.rerun()


# ---------------------------------------------------------------------------
# Sidebar: brand, navigation, filters, settings
# ---------------------------------------------------------------------------

dataset = st.session_state["dataset"]
load_error: str | None = None
try:
    raw_df, clean_df, report = load_and_clean(dataset["content"], dataset["name"])
except DataLoadError as exc:
    load_error = str(exc)
    raw_df, clean_df, report = pd.DataFrame(), pd.DataFrame(), QualityReport()

with st.sidebar:
    st.markdown(
        '<div class="ps-brand"><div class="logo">💊</div><div><div class="nm">PharmaStock</div>'
        '<div class="tg">Pharmacy Inventory Intelligence</div></div></div>',
        unsafe_allow_html=True,
    )
    # Nav rows are buttons, not a radio: baseweb's radio mark cannot be styled
    # away reliably, and buttons render close to their final form so the
    # sidebar does not reflow once the stylesheet lands.
    if st.session_state.get("page") not in PAGES:
        st.session_state["page"] = PAGES[0]
    with st.container(key="ps-nav", gap=6):
        for i, name in enumerate(PAGES):
            label = f"{name} 🔒" if name == AI_PAGE and not (user and user.is_paid) else name
            st.button(label, key=f"nav_{i}", width="stretch",
                      type="primary" if st.session_state["page"] == name else "tertiary",
                      on_click=_select_page, args=(name,))
    page = st.session_state["page"]
    st.divider()

    src_label = html.escape(dataset["label"])
    st.markdown(
        f'<div class="ps-source">📁 <b>{src_label}</b><br>{report.clean_rows:,} batch rows loaded'
        f'{" · data-quality " + format(report.score, ".0f") + "%" if report.clean_rows else ""}</div>',
        unsafe_allow_html=True,
    )

    with st.expander("⚙️ Thresholds & settings", expanded=False):
        ref_date = st.date_input("Reference date (analysis 'today')", value=date.today(), key="ref_date",
                                 help="Expiry, days since last sale and projected stockout dates are measured from this date.")
        currency = st.selectbox("Currency symbol", CURRENCIES, index=0, key="currency")
        st.caption("Movement")
        slow_doh = st.number_input("Slow-moving if days on hand >", 30, 1000, 180, 10, key="slow_doh")
        non_moving = st.number_input("Non-moving if no sale for (days) >", 14, 365, 90, 7, key="non_moving")
        st.caption("Overstock & replenishment")
        over_doh = st.number_input("Overstock if days on hand >", 30, 720, 120, 10, key="over_doh",
                                   help="Used when no Max_Stock_Level is supplied.")
        cover = st.number_input("Order to cover (days after delivery)", 7, 180, 30, 1, key="cover")
        c1, c2, c3 = st.columns(3)
        ss_v = c1.number_input("Safety V", 0, 90, 14, 1, key="ss_v", help="Safety stock days for Vital items")
        ss_e = c2.number_input("Safety E", 0, 90, 7, 1, key="ss_e", help="Safety stock days for Essential items")
        ss_n = c3.number_input("Safety N", 0, 90, 3, 1, key="ss_n", help="Safety stock days for Non-essential items")
        st.caption("ABC cut-offs (cumulative % of consumption value)")
        abc_a, abc_b = st.slider("A / B boundaries", 50, 99, (80, 95), 1, key="abc")

    settings = Settings(
        reference_date=ref_date if isinstance(ref_date, date) else date.today(),
        slow_moving_doh=int(slow_doh), non_moving_days=int(non_moving), overstock_doh=int(over_doh),
        target_cover_days=int(cover), safety_days_v=int(ss_v), safety_days_e=int(ss_e), safety_days_n=int(ss_n),
        abc_a_pct=float(abc_a), abc_b_pct=float(max(abc_b, abc_a + 1)),
    )

    filtered_df = clean_df
    active_filters = 0
    applied_filters: dict[str, list[str]] = {}  # label -> values, recorded on each AI report
    if not clean_df.empty:
        with st.expander("🔎 Filters", expanded=False):
            for col, label in (("Location", "Location"), ("Therapeutic_Category", "Therapeutic category"),
                               ("Drug_Class", "Drug class"), ("VEN_Class", "VEN class"),
                               ("Storage_Type", "Storage")):
                options = sorted(clean_df[col].dropna().astype(str).unique())
                chosen = st.multiselect(
                    label, options, key=f"f_{col}", placeholder="All",
                    format_func=(lambda v: f"{v} – {VEN_NAMES.get(v, v)}") if col == "VEN_Class" else str,
                )
                if chosen:
                    filtered_df = filtered_df[filtered_df[col].astype(str).isin(chosen)]
                    active_filters += 1
                    applied_filters[label] = chosen
            search = st.text_input("Search drug / generic / batch", key="f_search").strip()
            if search:
                mask = (filtered_df["Drug_Name"].str.contains(search, case=False, regex=False)
                        | filtered_df["Generic_Name"].str.contains(search, case=False, regex=False)
                        | filtered_df["Batch_No"].str.contains(search, case=False, regex=False))
                filtered_df = filtered_df[mask]
                active_filters += 1
                applied_filters["Search"] = [f"'{search}'"]

    analysis: Analysis | None = analyse(filtered_df, settings) if not filtered_df.empty else None

    if analysis is not None:
        st.divider()
        st.download_button(
            "Excel action report", excel_report(filtered_df, settings, currency),
            file_name=f"PharmaStock_Action_Report_{settings.reference_date:%Y-%m-%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/table_view:", width="stretch", type="primary",
            help="All modules in one workbook - keep a dated copy as compliance evidence.",
        )
    st.divider()
    sidebar_account()
    st.caption(f"PharmaStock v{__version__}")

# Scroll handling.
#
# The scroll must NOT be reset when the nav is clicked - that yanks the page
# you are still looking at up to the top before it is replaced. It is reset
# when the incoming page has actually rendered, detected by the <h1> in
# .ps-header changing. So the current page holds its position, and the next
# one opens at the top.
#
# Mounted once and listening on the parent document, because a per-switch
# iframe mounts ~0.8s after the click - far too late (measured).
components.html(
    """
    <script>
    (function () {
      const win = window.parent;
      const doc = win.document;
      if (win.__psNavScrollCleanup) { win.__psNavScrollCleanup(); }

      // Streamlit fades every element it considers stale to opacity .33 while
      // a rerun is in flight, so switching pages flashes the whole view dark
      // and back (measured: 44-57 elements, 100-370ms). The rule cannot go in
      // the injected stylesheet - Streamlit's HTML sanitiser strips any rule
      // mentioning data-stale (verified by diffing the served CSS) - so it is
      // written straight into the parent document here.
      let sheet = doc.getElementById('ps-runtime-css');
      if (!sheet) {
        sheet = doc.createElement('style');
        sheet.id = 'ps-runtime-css';
        doc.head.appendChild(sheet);
      }
      sheet.textContent =
        'div[data-stale="true"], section[data-stale="true"] {' +
        ' opacity: 1 !important; transition: none !important; }';

      const MAIN = 'section[data-testid="stMain"]';
      const NAV = 'section[data-testid="stSidebar"] .stButton button';
      const TITLE = '.ps-header h1';

      let waiting = false;     // a nav click is in flight
      let prevTitle = '';      // title at the moment of the click
      let deadline = 0;        // give up waiting after this
      let pinUntil = 0;        // hold the new page at the top until this
      let raf = null;

      const titleNow = function () {
        const el = doc.querySelector(TITLE);
        return el ? el.textContent.trim() : '';
      };

      const frame = function () {
        raf = null;
        const now = Date.now();

        if (waiting) {
          const t = titleNow();
          if (t && t !== prevTitle) {
            // the incoming page is on screen - now send it to the top
            waiting = false;
            pinUntil = now + 1200;
          } else if (now > deadline) {
            waiting = false;
          }
        }

        if (now < pinUntil) {
          const m = doc.querySelector(MAIN);
          if (m && m.scrollTop !== 0) { m.scrollTop = 0; }
        }

        if (waiting || now < pinUntil) { raf = win.requestAnimationFrame(frame); }
      };

      const kick = function () { if (raf === null) { raf = win.requestAnimationFrame(frame); } };

      const onDown = function (e) {
        const t = e.target;
        if (t && t.closest && t.closest(NAV)) {
          prevTitle = titleNow();
          waiting = true;
          deadline = Date.now() + 5000;
          pinUntil = 0;          // leave the outgoing page exactly where it is
          kick();
        }
      };
      // a deliberate scroll by the user always wins
      const release = function () { pinUntil = 0; };

      doc.addEventListener('mousedown', onDown, true);
      doc.addEventListener('wheel', release, { passive: true });
      doc.addEventListener('touchstart', release, { passive: true });
      doc.addEventListener('keydown', release, { passive: true });

      win.__psNavScrollCleanup = function () {
        doc.removeEventListener('mousedown', onDown, true);
        doc.removeEventListener('wheel', release);
        doc.removeEventListener('touchstart', release);
        doc.removeEventListener('keydown', release);
        waiting = false; pinUntil = 0;
      };
    })();
    </script>
    """,
    height=0,
)

cur = currency
subtitle = (f"Reference date <b>{settings.reference_date:%d %b %Y}</b>"
            + (f" · {active_filters} filter(s) active" if active_filters else ""))


def page_header(title: str) -> None:
    ui.header(title, subtitle, dataset["label"], dataset["is_sample"])


def require_analysis() -> Analysis | None:
    if load_error:
        ui.alert("critical", "The current file could not be read", load_error)
        st.stop()
    if clean_df.empty:
        ui.alert("critical", "No usable data loaded",
                 "Go to <b>Data Upload &amp; Quality</b> to upload a valid file or reload the sample dataset.")
        st.stop()
    if analysis is None:
        ui.alert("warning", "No rows match the current filters", "Clear or widen the sidebar filters.")
        st.stop()
    return analysis


def plot(fig, key: str) -> None:
    st.plotly_chart(fig, config=PLOT_CONFIG, key=key)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_dashboard() -> None:
    page_header("Executive Dashboard")
    a = require_analysis()
    k, b, sku = a.kpis, a.batches, a.sku

    # Critical alerts first: these are patient-safety and legal-compliance items.
    alerts = 0
    if k["vital_stocked_out"]:
        names = ", ".join(sku.loc[(sku["VEN_Class"] == "V") & (sku["Stock_Status"] == "Stocked out"), "Drug_Name"].head(6))
        ui.alert("critical", f"{k['vital_stocked_out']} VITAL medicine(s) stocked out",
                 f"{names}. Place emergency orders, borrow from a nearby site or arrange therapeutic substitution today.")
        alerts += 1
    if k["expired_batches"]:
        cd = f" — including <b>{k['expired_cd_batches']} controlled-drug batch(es)</b> needing witnessed destruction" \
            if k["expired_cd_batches"] else ""
        ui.alert("critical", f"{k['expired_batches']} expired batch(es) still on hand · {ui.money(k['expired_value'], cur)}",
                 f"Quarantine immediately and remove from dispensing stock{cd}.")
        alerts += 1
    if k["vital_critical"]:
        ui.alert("serious", f"{k['vital_critical']} Vital item(s) will run out before a normal delivery arrives",
                 "Days of cover is shorter than supplier lead time. See <b>Stockout Risk &amp; Reorder</b> (P1 list).")
        alerts += 1
    if k["exp30_batches"]:
        ui.alert("serious", f"{k['exp30_batches']} batch(es) expire within 30 days · {ui.money(k['exp30_value'], cur)}",
                 "Dispense first (FEFO), request supplier returns or transfer to a higher-demand site.")
        alerts += 1
    if k["unknown_expiry_batches"]:
        ui.alert("warning", f"{k['unknown_expiry_batches']} batch(es) have no readable expiry date",
                 "Physically verify and correct the stock record — these cannot be expiry-controlled.")
        alerts += 1
    if not alerts:
        ui.alert("good", "No critical alerts", "No Vital stockouts, no expired stock and nothing expiring within 30 days.")

    ui.section("Inventory health")
    ui.kpi_cards([
        {"label": "Inventory value", "value": ui.money(k["total_value"], cur), "tone": "info",
         "sub": f"{k['sku_count']:,} SKUs · {k['batch_count']:,} batches · {k['location_count']} location(s)"},
        {"label": "Expired stock", "value": ui.money(k["expired_value"], cur),
         "tone": "critical" if k["expired_batches"] else "good",
         "sub": f"{k['expired_batches']} batch(es) to quarantine", "tag": "Write-off" if k["expired_batches"] else "Clear"},
        {"label": "Near expiry ≤ 90 days", "value": ui.money(k["near_expiry_value"], cur),
         "tone": "serious" if k["near_expiry_value"] else "good", "sub": f"{k['near_expiry_batches']} batch(es)"},
        {"label": "Projected expiry loss", "value": ui.money(k["projected_loss_value"], cur),
         "tone": "warning" if k["projected_loss_value"] else "good",
         "sub": "Live stock that will expire before it is dispensed (FEFO)"},
    ])
    ui.kpi_cards([
        {"label": "Vital availability", "value": fmt_pct(k["vital_availability"]),
         "tone": "good" if (k["vital_availability"] or 0) >= 98 else "critical",
         "sub": f"All items {fmt_pct(k['availability'])}", "tag": "Target ≥ 98%"},
        {"label": "Stocked out / critical", "value": f"{k['stocked_out']} / {k['critical_items']}",
         "tone": "critical" if k["stocked_out"] else ("serious" if k["critical_items"] else "good"),
         "sub": f"{k['reorder_items']} SKUs to order · {ui.money(k['reorder_value'], cur)}"},
        {"label": "Overstock excess", "value": ui.money(k["excess_value"], cur),
         "tone": "warning" if k["excess_value"] else "good", "sub": f"{k['overstock_items']} overstocked SKUs"},
        {"label": "Slow + non-moving", "value": ui.money(k["slow_value"], cur),
         "tone": "warning" if k["slow_value"] else "good",
         "sub": f"{k['slow_items']} slow · {k['non_moving_items']} non-moving"},
        {"label": "Turnover · DOH", "value": f"{fmt_x(k['turnover'])} · {fmt_x(k['doh'], ' d')}", "tone": "neutral",
         "sub": "Annualised turnover · portfolio days on hand"},
    ])

    c1, c2 = st.columns(2, gap="large")
    with c1:
        ui.section("Stock value by expiry window", "Status colours: red expired · orange ≤30 d · amber 31–60 d · blues later")
        plot(ch.expiry_bucket_bar(b, cur), "d_exp")
    with c2:
        ui.section("SKU stock status", "Each SKU (drug × location) classified by usable stock vs. reorder point")
        plot(ch.status_bar(sku), "d_status")
    c3, c4 = st.columns(2, gap="large")
    with c3:
        ui.section("ABC-VEN matrix (SKU count)", "Category I = tight control · II = moderate · III = low priority")
        plot(ch.abc_ven_heatmap(sku, "count", cur), "d_abcven")
    with c4:
        ui.section("Stock value by therapeutic category")
        plot(ch.value_by_category(sku, cur, height=340), "d_cat")

    ui.section("Today's priority actions", "Top reorder items (P1 first) and batches requiring compliance action")
    t1, t2 = st.tabs(["🚨 Reorder priorities", "⏳ Expiry actions"])
    with t1:
        pri = sku[sku["Priority"] != ""].sort_values(["Priority_Score", "Days_On_Hand"], ascending=[False, True]).head(15)
        ui.table(pri, ["Priority", "Drug_Name", "Strength", "VEN_Class", "Stock_Status", "Usable_Qty", "Days_On_Hand",
                       "Lead_Time_Days", "Suggested_Order_Qty", "Suggested_Order_Value", "Supplier", "Location"],
                 cur, key="dash_reorder")
    with t2:
        act = b[b["Expiry_Bucket"].astype(str).isin(["Expired", "≤30 days", "Unknown expiry"])].sort_values(
            "Days_To_Expiry", na_position="first").head(15)
        ui.table(act, ["Drug_Name", "Strength", "Batch_No", "Expiry_Date", "Days_To_Expiry", "Qty_On_Hand",
                       "Stock_Value", "Compliance_Flags", "Recommended_Action", "Location"], cur, key="dash_expiry")


def page_upload() -> None:
    page_header("Data Upload & Quality")

    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        ui.section("Upload inventory file", "CSV, TXT/TSV or Excel (.xlsx). One row per batch/lot per location.")
        up = st.file_uploader("Upload", type=["csv", "txt", "tsv", "xlsx", "xlsm"], label_visibility="collapsed",
                              key="uploader")
        if up is not None:
            content = up.getvalue()
            sig = (up.name, len(content))
            if st.session_state.get("_last_upload") != sig:
                st.session_state["_last_upload"] = sig
                try:
                    _, new_clean, new_report = load_and_clean(content, up.name)
                except DataLoadError as exc:
                    st.session_state["_upload_msg"] = ("critical", f"Could not read {up.name}", str(exc))
                else:
                    if new_report.fatal or new_clean.empty:
                        errs = "<br>".join(f"• <b>{i.column}</b>: {i.message}" for i in new_report.issues
                                           if i.severity == "error")
                        st.session_state["_upload_msg"] = (
                            "critical", f"{up.name} was not loaded - required data missing",
                            f"{errs}<br>Required columns: <code>{', '.join(REQUIRED_COLUMNS)}</code>. "
                            "The previous dataset is still active.")
                    else:
                        st.session_state["dataset"] = {"content": content, "name": up.name, "label": up.name,
                                                       "is_sample": False}
                        st.session_state["_upload_msg"] = (
                            "good", f"Loaded {up.name}",
                            f"{new_report.clean_rows:,} batch rows ready. All pages now use this file.")
                st.rerun()
        msg = st.session_state.get("_upload_msg")
        if msg:
            ui.alert(*msg)
    with c2:
        ui.section("Sample data & template")
        st.download_button("Download sample dataset (CSV)", sample_bytes(settings.reference_date),
                           file_name="pharmastock_sample.csv", mime="text/csv", icon=":material/download:",
                           width="stretch", key="dl_sample")
        st.download_button("Download blank template (CSV)", template_frame().to_csv(index=False).encode("utf-8"),
                           file_name="pharmastock_template.csv", mime="text/csv", icon=":material/description:",
                           width="stretch", key="dl_template")
        if st.button("Reload built-in sample data", icon=":material/restart_alt:", width="stretch",
                     disabled=dataset["is_sample"]):
            use_sample()
            st.session_state.pop("_upload_msg", None)
            st.session_state.pop("_last_upload", None)
            st.rerun()

    if load_error:
        ui.alert("critical", "The active file could not be read", load_error)
        return

    ui.section("Data-quality report", f"Active dataset: <b>{html.escape(dataset['label'])}</b>")
    errors = sum(1 for i in report.issues if i.severity == "error")
    warnings = sum(1 for i in report.issues if i.severity == "warning")
    ui.kpi_cards([
        {"label": "Rows received", "value": f"{report.source_rows:,}", "tone": "neutral"},
        {"label": "Rows analysed", "value": f"{report.clean_rows:,}", "tone": "info"},
        {"label": "Data-quality score", "value": f"{report.score:.0f}%",
         "tone": "good" if report.score >= 95 else ("warning" if report.score >= 80 else "critical")},
        {"label": "Errors · warnings", "value": f"{errors} · {warnings}",
         "tone": "critical" if errors else ("warning" if warnings else "good")},
    ])
    if report.issues:
        st.dataframe(report.as_frame(), hide_index=True, key="dq_issues")
    else:
        ui.alert("good", "No data-quality issues found")

    with st.expander("Column mapping (your headers → PharmaStock fields)", expanded=False):
        if report.column_map:
            st.dataframe(pd.DataFrame({"Your column": list(report.column_map),
                                       "Mapped to": list(report.column_map.values())}),
                         hide_index=True, key="dq_map")
        else:
            st.caption("No columns mapped.")

    with st.expander("Supported columns", expanded=False):
        st.dataframe(pd.DataFrame({
            "Column": list(COLUMN_DESCRIPTIONS),
            "Required": ["Yes" if c in REQUIRED_COLUMNS else "Optional" for c in COLUMN_DESCRIPTIONS],
            "Description": list(COLUMN_DESCRIPTIONS.values()),
        }), hide_index=True, key="dq_cols")

    ui.section("Cleaned data preview", "After header mapping, type conversion and defaults")
    if not clean_df.empty:
        st.dataframe(clean_df.head(500), hide_index=True, key="dq_preview", height=360, placeholder="–",
                     column_config={c: st.column_config.DateColumn(c, format="YYYY-MM-DD")
                                    for c in ("Expiry_Date", "Manufacture_Date", "Last_Sale_Date")})


def page_expiry() -> None:
    page_header("Expiry & Compliance")
    a = require_analysis()
    k, b = a.kpis, a.batches

    if k["expired_cd_batches"]:
        ui.alert("critical", f"{k['expired_cd_batches']} expired controlled-drug batch(es)",
                 "Segregate in the CD cabinet, mark 'EXPIRED – NOT FOR USE', and arrange witnessed destruction "
                 "with a controlled-drug register entry.")
    cold_near = b[b["Storage_Type"].ne("Room Temperature")
                  & b["Expiry_Bucket"].astype(str).isin(["Expired", "≤30 days", "31–60 days", "61–90 days"])]
    if len(cold_near):
        ui.alert("warning", f"{len(cold_near)} cold-chain batch(es) expired or expiring within 90 days · "
                            f"{ui.money(cold_near['Stock_Value'].sum(), cur)}",
                 "Check fridge temperature logs before any return or transfer; excursion stock must be quarantined.")

    ui.kpi_cards([
        {"label": "Expired", "value": ui.money(k["expired_value"], cur), "tone": "critical" if k["expired_batches"] else "good",
         "sub": f"{k['expired_batches']} batches"},
        {"label": "≤ 30 days", "value": ui.money(k["exp30_value"], cur), "tone": "serious", "sub": f"{k['exp30_batches']} batches"},
        {"label": "31–60 days", "value": ui.money(k["exp60_value"], cur), "tone": "warning"},
        {"label": "61–90 days", "value": ui.money(k["exp90_value"], cur), "tone": "info"},
        {"label": "Projected FEFO loss", "value": ui.money(k["projected_loss_value"], cur), "tone": "warning",
         "sub": "Will expire before being dispensed at current demand"},
    ])

    c1, c2 = st.columns([2, 3], gap="large")
    with c1:
        ui.section("Value by expiry window")
        plot(ch.expiry_bucket_bar(b, cur, height=380), "e_bucket")
    with c2:
        ui.section("Expiry timeline – next 180 days", "Each point is a batch · ◆ = cold chain / frozen · hover for details")
        plot(ch.expiry_timeline(b, cur, pd.Timestamp(settings.reference_date)), "e_timeline")

    ui.callout("<b>How the FEFO projection works:</b> batches are assumed to be dispensed First-Expiry-First-Out at the "
               "product's average daily usage. <i>Projected unsold qty</i> is what will still be on the shelf on the "
               "expiry date — act on it now (return, transfer, stop reordering) instead of writing it off later.")

    ui.section("Batch register")
    windows = ["Expired", "≤30 days", "31–60 days", "61–90 days", "91–180 days", ">180 days", "Unknown expiry"]
    f1, f2 = st.columns([3, 1])
    chosen = f1.multiselect("Expiry windows", windows, default=["Expired", "≤30 days", "31–60 days", "61–90 days",
                                                               "Unknown expiry"], key="e_windows")
    only_loss = f2.toggle("Only projected loss", key="e_loss")
    view = b[b["Expiry_Bucket"].astype(str).isin(chosen or windows)]
    if only_loss:
        view = view[view["Projected_Unsold_Qty"] > 0]
    view = view.sort_values("Days_To_Expiry", na_position="first")
    ui.table(view, ["Drug_Name", "Strength", "Drug_Class", "Storage_Type", "Batch_No", "Expiry_Date", "Days_To_Expiry",
                    "Expiry_Bucket", "Qty_On_Hand", "Stock_Value", "Projected_Unsold_Qty", "Projected_Loss_Value",
                    "Compliance_Flags", "Recommended_Action", "Location", "Supplier"],
             cur, key="expiry_register", height=460, file_name="pharmastock_expiry_register.csv")


def page_slow() -> None:
    page_header("Slow-Moving Stock")
    a = require_analysis()
    k, sku, s = a.kpis, a.sku, a.settings
    slow = sku[sku["Movement_Class"].isin(["Slow-moving", "Non-moving"])].sort_values("Slow_Moving_Value", ascending=False)

    ui.kpi_cards([
        {"label": "Tied-up value", "value": ui.money(k["slow_value"], cur), "tone": "warning" if k["slow_value"] else "good",
         "sub": f"{ui.num(k['slow_value'] / k['usable_value'] * 100 if k['usable_value'] else float('nan'), 1, '%')} of usable stock"},
        {"label": "Slow-moving SKUs", "value": k["slow_items"], "tone": "warning",
         "sub": f"Days on hand > {s.slow_moving_doh}"},
        {"label": "Non-moving SKUs", "value": k["non_moving_items"], "tone": "serious",
         "sub": f"No sale in {s.non_moving_days}+ days"},
        {"label": "Of which expire ≤ 180 d", "value": int((slow["Nearest_Expiry"] <= pd.Timestamp(s.reference_date)
                                                           + pd.Timedelta(days=180)).sum()),
         "tone": "serious", "sub": "Highest write-off risk – act first"},
    ])
    c1, c2 = st.columns([2, 3], gap="large")
    with c1:
        ui.section("Usable value by movement class")
        plot(ch.movement_value_bar(sku, cur), "s_move")
    with c2:
        ui.section("Largest slow & non-moving positions")
        plot(ch.top_items_bar(slow, "Slow_Moving_Value", cur, color=ch.WARNING,
                              hover_cols={"Movement_Class": "Movement", "Location": "Location"},
                              x_title="Tied-up value"), "s_top")
    ui.callout("<b>Recommended actions:</b> stop automatic reorders · transfer to a higher-demand branch or ward · "
               "negotiate supplier return before the return window closes · review formulary need with prescribers · "
               "for seasonal lines, plan next season's order from actual sell-through.")
    ui.section("Slow & non-moving register")
    ui.table(slow, ["Drug_Name", "Strength", "Therapeutic_Category", "VEN_Class", "Movement_Class", "Usable_Qty",
                    "Units_Sold_90D", "Avg_Daily_Usage", "Days_On_Hand", "Days_Since_Last_Sale", "Nearest_Expiry",
                    "Slow_Moving_Value", "Seasonal", "Location"], cur, key="slow_register", height=440)


def page_overstock() -> None:
    page_header("Overstock")
    a = require_analysis()
    k, sku, s = a.kpis, a.sku, a.settings
    over = sku[sku["Is_Overstock"]].sort_values("Excess_Value", ascending=False)
    cold_excess = over.loc[over["Storage_Type"].ne("Room Temperature"), "Excess_Value"].sum()
    seasonal_excess = over.loc[over["Seasonal"], "Excess_Value"].sum()

    ui.kpi_cards([
        {"label": "Excess value", "value": ui.money(k["excess_value"], cur), "tone": "warning" if k["excess_value"] else "good",
         "sub": f"{k['overstock_items']} SKUs above target maximum"},
        {"label": "Cold-chain excess", "value": ui.money(cold_excess, cur), "tone": "serious" if cold_excess else "good",
         "sub": "Costly to store; excursion risk"},
        {"label": "Seasonal excess", "value": ui.money(seasonal_excess, cur), "tone": "warning" if seasonal_excess else "good",
         "sub": "e.g. flu vaccines, antivirals, allergy lines"},
        {"label": "Overstock rule", "value": f"> {s.overstock_doh} days", "tone": "neutral",
         "sub": "or above Max_Stock_Level when supplied"},
    ])
    ui.section("Largest excess positions")
    plot(ch.top_items_bar(over, "Excess_Value", cur, color=ch.BLUE[450],
                          hover_cols={"Storage_Type": "Storage", "Days_On_Hand": "Days on hand"},
                          x_title="Excess value"), "o_top")
    ui.callout("<b>Recommended actions:</b> pause or reduce open purchase orders · redistribute to other sites · "
               "for specialty/biologic items move to order-on-demand per patient · agree returns or consignment with "
               "the supplier · lower max levels in your ordering system to the <i>target max qty</i> shown below.")
    ui.section("Overstock register")
    ui.table(over, ["Drug_Name", "Strength", "Therapeutic_Category", "Storage_Type", "Seasonal", "VEN_Class", "Usable_Qty",
                    "Avg_Daily_Usage", "Days_On_Hand", "Target_Max_Qty", "Excess_Qty", "Excess_Value", "Nearest_Expiry",
                    "Supplier", "Location"], cur, key="over_register", height=440)


def page_stockout() -> None:
    page_header("Stockout Risk & Reorder")
    a = require_analysis()
    k, sku = a.kpis, a.sku
    at_risk = sku[sku["Priority"] != ""].sort_values(["Priority_Score", "Days_On_Hand"], ascending=[False, True])

    p1 = at_risk[at_risk["Priority"].str.startswith("P1")]
    if len(p1):
        ui.alert("critical", f"{len(p1)} P1 item(s) need action today",
                 ", ".join(p1["Drug_Name"].head(8)) + ". Emergency order, inter-site borrowing or therapeutic substitution.")
    ui.kpi_cards([
        {"label": "Stocked out", "value": k["stocked_out"], "tone": "critical" if k["stocked_out"] else "good",
         "sub": f"{k['vital_stocked_out']} Vital"},
        {"label": "Critical (< lead time)", "value": k["critical_items"],
         "tone": "serious" if k["critical_items"] else "good", "sub": f"{k['vital_critical']} Vital"},
        {"label": "To order", "value": k["reorder_items"], "tone": "warning", "sub": ui.money(k["reorder_value"], cur) + " suggested"},
        {"label": "Revenue at risk / day", "value": ui.money(k["daily_revenue_at_risk"], cur, 2), "tone": "serious",
         "sub": "From stocked-out items"},
        {"label": "Vital availability", "value": fmt_pct(k["vital_availability"]),
         "tone": "good" if (k["vital_availability"] or 0) >= 98 else "critical", "sub": "Target ≥ 98%"},
    ])
    ui.section("Days of cover vs. supplier lead time",
               "Bar = days usable stock will last · black tick = lead time. A bar shorter than its tick will run out before delivery.")
    plot(ch.cover_vs_leadtime(sku), "so_cover")
    ui.callout("<b>Priority logic:</b> urgency (Stocked out 3 · Critical 2 · Reorder 1) × VEN weight (V 3 · E 2 · N 1). "
               "<b>P1</b> ≥ 6 · <b>P2</b> ≥ 3 · <b>P3</b> otherwise. Suggested quantity orders up to "
               f"lead time + {a.settings.target_cover_days} days of cover + safety stock, capped at Max_Stock_Level when supplied.")
    ui.section("Reorder worklist")
    pri = st.pills("Priority", ["P1 – Immediate", "P2 – Urgent", "P3 – Routine"], selection_mode="multi",
                   default=["P1 – Immediate", "P2 – Urgent", "P3 – Routine"], key="so_pri")
    view = at_risk[at_risk["Priority"].isin(pri)] if pri else at_risk
    ui.table(view, ["Priority", "Drug_Name", "Strength", "VEN_Class", "Drug_Class", "Stock_Status", "Usable_Qty",
                    "Avg_Daily_Usage", "Days_On_Hand", "Lead_Time_Days", "Projected_Stockout_Date", "Safety_Stock",
                    "Reorder_Point", "ROP_Source", "Suggested_Order_Qty", "Suggested_Order_Value", "Supplier", "Location"],
             cur, key="reorder_list", height=460, file_name="pharmastock_reorder_list.csv")


def page_abc_ven() -> None:
    page_header("ABC-VEN Matrix")
    a = require_analysis()
    sku, s = a.sku, a.settings

    counts = sku["ABC_VEN_Category"].value_counts()
    values = sku.groupby("ABC_VEN_Category")["Annual_Usage_Value"].sum()
    total_v = values.sum() or 1
    ui.kpi_cards([
        {"label": f"Category {c}", "value": f"{int(counts.get(c, 0))} SKUs",
         "tone": {"I": "info", "II": "neutral", "III": "neutral"}[c],
         "sub": f"{values.get(c, 0) / total_v * 100:.0f}% of consumption value · {ABC_VEN_CATEGORY_POLICY[c].split(':')[0]}"}
        for c in ("I", "II", "III")
    ])
    metric = st.segmented_control("Show matrix by", ["SKU count", "Consumption value"], default="SKU count",
                                  key="abc_metric") or "SKU count"
    c1, c2 = st.columns(2, gap="large")
    with c1:
        ui.section("ABC × VEN matrix")
        plot(ch.abc_ven_heatmap(sku, "value" if metric == "Consumption value" else "count", cur, height=380), "a_heat")
    with c2:
        ui.section("ABC Pareto curve", f"A ≤ {s.abc_a_pct:.0f}% · B ≤ {s.abc_b_pct:.0f}% of annual consumption value")
        plot(ch.pareto_curve(sku, s.abc_a_pct, s.abc_b_pct, height=380), "a_pareto")

    ui.callout("<b>Category I</b> (AV, AE, AN, BV, CV) — " + ABC_VEN_CATEGORY_POLICY["I"] +
               "<br><b>Category II</b> (BE, CE, BN) — " + ABC_VEN_CATEGORY_POLICY["II"] +
               "<br><b>Category III</b> (CN) — " + ABC_VEN_CATEGORY_POLICY["III"])
    ui.section("Classification register")
    cats = st.pills("Matrix category", ["I", "II", "III"], selection_mode="multi", default=["I", "II", "III"], key="abc_cat")
    view = sku[sku["ABC_VEN_Category"].isin(cats)] if cats else sku
    view = view.sort_values("Annual_Usage_Value", ascending=False)
    ui.table(view, ["Drug_Name", "Strength", "Therapeutic_Category", "Annual_Usage_Value", "Cum_Value_Pct", "ABC_Class",
                    "VEN_Class", "ABC_VEN", "ABC_VEN_Category", "Stock_Status", "Days_On_Hand", "Location"],
             cur, key="abc_register", height=440)


def page_turnover() -> None:
    page_header("Turnover, DOH & Availability")
    a = require_analysis()
    k, sku, s = a.kpis, a.sku, a.settings
    ui.kpi_cards([
        {"label": "Inventory turnover", "value": fmt_x(k["turnover"]), "tone": "info", "sub": "Annualised, at cost"},
        {"label": "Days on hand", "value": fmt_x(k["doh"], " days"), "tone": "info", "sub": "Usable value ÷ daily consumption"},
        {"label": "Stock availability", "value": fmt_pct(k["availability"]),
         "tone": "good" if (k["availability"] or 0) >= 95 else "warning", "sub": "SKUs with usable stock"},
        {"label": "Vital availability", "value": fmt_pct(k["vital_availability"]),
         "tone": "good" if (k["vital_availability"] or 0) >= 98 else "critical", "sub": "Target ≥ 98%"},
    ])
    c1, c2 = st.columns(2, gap="large")
    with c1:
        ui.section("Days-on-hand distribution", f"Darker blue = beyond the {s.overstock_doh}-day overstock threshold")
        plot(ch.doh_distribution(sku, s.overstock_doh), "t_doh")
    with c2:
        ui.section("Availability by VEN class", "Share of SKUs with usable (non-expired) stock")
        plot(ch.availability_by(sku, "VEN_Class", VEN_NAMES), "t_avail")
    group = st.segmented_control("Turnover by", ["Therapeutic_Category", "Drug_Class", "Storage_Type", "Location"],
                                 default="Therapeutic_Category", key="t_group",
                                 format_func=lambda v: ui.LABELS.get(v, v)) or "Therapeutic_Category"
    ui.section(f"Turnover by {ui.LABELS.get(group, group).lower()}")
    plot(ch.turnover_by_group(sku, group), "t_group_chart")
    ui.section("SKU turnover register")
    ui.table(sku.sort_values("Turnover_Annual", ascending=False, na_position="last"),
             ["Drug_Name", "Strength", "Therapeutic_Category", "VEN_Class", "ABC_Class", "Usable_Qty", "Usable_Value",
              "Avg_Daily_Usage", "Days_On_Hand", "Turnover_Annual", "Movement_Class", "Stock_Status", "Location"],
             cur, key="turnover_register", height=440)


# Model output is shaped by the uploaded file, so every character that could start
# HTML, a markdown construct (links, images, emphasis, tables) or LaTeX ($) is
# replaced by its entity in one pass.
_SAFE_CHARS = str.maketrans({c: f"&#{ord(c)};" for c in "&<>\"'[]*_`~$#|!\\"})


def _safe(text: str) -> str:
    return str(text).translate(_SAFE_CHARS)


@st.cache_data(show_spinner=False, max_entries=32, ttl=3600)
def estimate_input_tokens(context: str) -> int | None:
    try:
        return agents.estimate_input_tokens(context)
    except agents.AgentError:
        return None


# Outcomes shown to users who have not subscribed: customer pain -> result.
PLAN_BENEFITS = [
    ("Never run out of life-critical medicines",
     "Vital stockouts and items that will run out before the next delivery come first, with exactly what to "
     "order today."),
    ("Stop writing off expired stock",
     "Know which batches to dispense first, return or transfer before they expire, and which controlled drugs "
     "need action now."),
    ("Free up cash stuck on the shelf",
     "See where overstock and slow movers are locking up money, and what to pause, return or redistribute."),
    ("Walk into your meeting ready",
     "A prioritised action list, reorder table and charts, downloaded as PDF, PowerPoint, Word or Excel in one "
     "click."),
    ("Nothing urgent slips through",
     "Every critical safety and compliance issue in your data is checked and included, every time."),
    ("Decisions you can defend",
     "Each action shows the figure behind it, plus the filters and thresholds the plan was built on."),
]


def _scope_lines(report: agents.ActionReport, current_scope: str) -> list[str]:
    if report.scope and report.scope != current_scope:
        return [f"Recommendations — {report.scope}", f"Charts and reorder table — {current_scope}"]
    return [report.scope or current_scope]


def _exports(report: agents.ActionReport, a: Analysis, current_scope: str) -> dict[str, bytes]:
    """Build the four files once per report + data view (a few seconds), then reuse."""
    import export_utils  # matplotlib/reportlab load only when a paid report is shown

    key = (report.id, report.created_at, dataset["label"], current_scope, cur)
    cache = st.session_state.get("_plan_exports")
    if not cache or cache[0] != key:
        with st.spinner("Preparing PDF, PowerPoint, Word and Excel files…"):
            bundle = export_utils.build_bundle(a, report, cur, dataset["label"], current_scope)
            cache = (key, export_utils.export_all(bundle))
        st.session_state["_plan_exports"] = cache
    return cache[1]


def render_action_plan(plan: agents.ActionReport, a: Analysis, current_scope: str, sig: str) -> None:
    import export_utils

    if plan.context_sig != sig:
        ui.alert("warning", "This plan was generated for a different data view",
                 "The dataset, filters or settings have changed since it was generated. The recommendations "
                 "reflect the earlier view; the reorder table, charts and downloads use the current view.")

    ui.section("Download for your meeting", f"Generated {html.escape(plan.created_at)} · "
                                            f"{plan.tokens:,} AI tokens")
    files = _exports(plan, a, current_scope)
    stamp = f"{a.settings.reference_date:%Y-%m-%d}"
    icons = {"PDF": ":material/picture_as_pdf:", "PPTX": ":material/slideshow:", "DOCX": ":material/description:",
             "XLSX": ":material/table_view:"}
    for col, (fmt, (_, ext, mime)) in zip(st.columns(4), export_utils.EXPORTERS.items()):
        col.download_button(fmt, files[fmt], file_name=f"PharmaStock_AI_Action_Plan_{stamp}.{ext}", mime=mime,
                            icon=icons[fmt], width="stretch", key=f"dl_plan_{fmt}")

    ui.section(export_utils.SUMMARY_HEADING)
    ui.callout(_safe(plan.summary))

    ui.section(export_utils.RECS_HEADING, "Most urgent first")
    tone = {"High": "critical", "Medium": "warning", "Low": "info"}
    for i, rec in enumerate(plan.recommendations, 1):
        added = " · <i>added by the urgent-issue check</i>" if rec.get("source") == "check" else ""
        ui.alert(tone.get(rec["impact"], "info"), f"{i}. {_safe(rec['action'])}",
                 f"<b>{_safe(rec['impact'])} impact · {_safe(rec['timeframe'])}</b> — {_safe(rec['rationale'])}"
                 f"{added}")

    sku, b = a.sku, a.batches
    ui.section(export_utils.REORDER_HEADING, "P1 first · suggested quantities cover lead time, target cover "
                                             "and safety stock")
    pri = sku[sku["Priority"] != ""].sort_values(["Priority_Score", "Days_On_Hand"], ascending=[False, True]).head(15)
    ui.table(pri, ["Priority", "Drug_Name", "Strength", "VEN_Class", "Stock_Status", "Days_On_Hand",
                   "Suggested_Order_Qty", "Suggested_Order_Value", "Location"], cur, key="plan_reorder",
             file_name="pharmastock_reorder_priorities.csv")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        ui.section("Stock value by expiry window")
        plot(ch.expiry_bucket_bar(b, cur), "plan_exp")
    with c2:
        ui.section("SKU stock status")
        plot(ch.status_bar(sku), "plan_status")
    c3, c4 = st.columns(2, gap="large")
    with c3:
        ui.section("Stock value by therapeutic category")
        plot(ch.value_by_category(sku, cur, height=340), "plan_cat")
    with c4:
        ui.section("ABC-VEN matrix (SKU count)")
        plot(ch.abc_ven_heatmap(sku, "count", cur), "plan_abcven")

    st.markdown('<div class="ps-section-sub">' + "<br>".join(_safe(x) for x in _scope_lines(plan, current_scope))
                + "</div>", unsafe_allow_html=True)




def page_ai_action_plan() -> None:
    page_header(AI_PAGE)

    if user is None or not user.is_paid:
        c1, c2 = st.columns([3, 2], gap="large")
        with c1:
            ui.section("Walk into every stock meeting with a ready-made action plan",
                       "Stop spending hours in spreadsheets working out what to fix first. The AI reads your stock "
                       "position and tells you what to act on, in order of urgency.")
            ui.callout("<br><br>".join(f"<b>{t}</b><br>{d}" for t, d in PLAN_BENEFITS))
            st.caption("Built on the figures PharmaStock already calculates. Only a summary is sent for AI analysis, "
                       "never your uploaded file.")
        with c2:
            if user is None:
                ui.section("Sign in to your Paid plan")
                login_form("login_main")
            else:
                ui.alert("info", "Your account is on the Free plan",
                         "Upgrade to the Paid plan to get your AI Action Plan. Contact your administrator to "
                         "upgrade.")
        return

    a = require_analysis()
    usage = token_counter.get_usage(user.email)
    context = agents.build_context(a, cur, dataset["label"], report.score if report.clean_rows else None,
                                   active_filters)
    current_scope = agents.describe_scope(applied_filters, settings, cur)
    configured = config.api_key_configured()
    est_in = estimate_input_tokens(context) if configured else None

    ui.kpi_cards([
        {"label": "AI tokens used", "value": f"{usage.used:,}",
         "tone": "critical" if usage.fraction >= 0.9 else ("warning" if usage.fraction >= 0.6 else "info"),
         "sub": f"of {usage.limit:,} this month"},
        {"label": "Remaining", "value": f"{usage.remaining:,}", "tone": "neutral",
         "sub": f"Resets {token_counter.next_reset():%d %b %Y}"},
        {"label": "Data sent per plan", "value": f"{est_in:,} tokens" if est_in else "–", "tone": "neutral",
         "sub": f"plus up to {config.AGENT_MAX_OUTPUT_TOKENS:,} tokens written"},
    ])

    with st.expander("What is sent for AI analysis", expanded=False):
        st.caption("Only this summary is sent to Anthropic's API, not your uploaded file.")
        st.code(context, language=None, wrap_lines=True)

    needed = (est_in or 0) + config.AGENT_MIN_OUTPUT_TOKENS
    blocked = not configured or (est_in is not None and usage.remaining < needed)
    if not configured:
        ui.alert("warning", "AI service not configured",
                 "The server has no <code>ANTHROPIC_API_KEY</code>. Ask your administrator to set it.")
    elif est_in is not None and usage.remaining < needed:
        ui.alert("warning", "Not enough tokens left this month for a complete plan",
                 f"A plan needs at least {needed:,} tokens and {usage.remaining:,} remain. Your allowance resets on "
                 f"{token_counter.next_reset():%d %b %Y}. Saved plans below can still be opened and downloaded.")

    if st.button("Generate action plan", type="primary", icon=":material/bolt:", disabled=blocked,
                 key="plan_run"):
        try:
            with st.spinner("Preparing your action plan… this usually takes 10–30 seconds."):
                fresh = agents.run_report(user.email, a, context, dataset["label"], current_scope, cur)
            st.session_state["_plan_report"] = fresh
            st.session_state["plan_saved"] = fresh.id  # set before the selectbox below is created
        except token_counter.TokenLimitExceeded as exc:
            ui.alert("warning", "Monthly AI token limit reached", html.escape(str(exc)))
        except agents.AgentError as exc:
            spent = f" {exc.tokens_spent:,} tokens were used." if exc.tokens_spent else " No tokens were used."
            ui.alert("critical", "The action plan could not be generated", html.escape(str(exc)) + spent)

    saved = agents.list_reports(user.email)
    if not saved:
        ui.callout("No action plans yet. Click <b>Generate action plan</b> to create one for the current view.")
        return
    options = {r["id"]: f"{r['created_at'].replace('T', ' ').rstrip('Z')} UTC · {r['dataset_label']} · "
                        f"{r['tokens']:,} tokens" for r in saved}
    if st.session_state.get("plan_saved") not in options:
        st.session_state["plan_saved"] = saved[0]["id"]
    chosen = st.selectbox("Saved action plans", list(options), format_func=options.get, key="plan_saved",
                          help="Plans are kept so they can be reopened and downloaded again at no token cost.")
    current: agents.ActionReport | None = st.session_state.get("_plan_report")
    if current is None or current.id != chosen:
        current = agents.load_report(user.email, chosen)
        st.session_state["_plan_report"] = current
    if current is not None:
        render_action_plan(current, a, current_scope, agents.context_signature(context, current_scope))


def page_guide() -> None:
    page_header("How-to-Use & Compliance Guide")
    body = guide_html()
    if not body:
        ui.alert("warning", "Guide file not found", f"Expected at <code>{GUIDE_PATH}</code>.")
        return
    try:
        full = GUIDE_PATH.read_bytes()
    except OSError:
        full = body.encode("utf-8")
    st.download_button("Download guide (HTML)", full, file_name="PharmaStock_Guide.html", mime="text/html",
                       icon=":material/download:", key="dl_guide")
    st.html(body)


ROUTES = {
    PAGES[0]: page_dashboard,
    PAGES[1]: page_upload,
    PAGES[2]: page_expiry,
    PAGES[3]: page_slow,
    PAGES[4]: page_overstock,
    PAGES[5]: page_stockout,
    PAGES[6]: page_abc_ven,
    PAGES[7]: page_turnover,
    PAGES[8]: page_ai_action_plan,
    PAGES[9]: page_guide,
}

ROUTES.get(page, page_dashboard)()
