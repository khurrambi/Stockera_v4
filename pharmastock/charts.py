"""Plotly figures for PharmaStock.

Colour is assigned by the job it does: status colours only for states
(expired, stocked out ...), a single blue ramp for magnitude, and fixed
categorical slots for identity. Every status colour is paired with a text label.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .analytics import EXPIRY_BUCKETS, STOCK_STATUSES

# Chart chrome
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# Status palette (reserved for states)
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"

# Categorical slots (fixed order) and blue ramp
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE = {100: "#cde2fb", 150: "#b7d3f6", 200: "#9ec5f4", 250: "#86b6ef", 300: "#6da7ec", 350: "#5598e7",
        400: "#3987e5", 450: "#2a78d6", 500: "#256abf", 550: "#1c5cab", 600: "#184f95", 650: "#104281", 700: "#0d366b"}

EXPIRY_COLORS = {
    "Expired": CRITICAL,
    "≤30 days": SERIOUS,
    "31–60 days": WARNING,
    "61–90 days": BLUE[250],
    "91–180 days": BLUE[400],
    ">180 days": BLUE[600],
    "Unknown expiry": MUTED,
}
STATUS_COLORS = {
    "Stocked out": CRITICAL,
    "Critical (below lead time)": SERIOUS,
    "Reorder now": WARNING,
    "Healthy": GOOD,
    "Overstock": BLUE[450],
    "No demand": MUTED,
}
MOVEMENT_COLORS = {
    "Fast-moving": BLUE[600],
    "Normal": BLUE[300],
    "Slow-moving": WARNING,
    "Non-moving": SERIOUS,
    "Out of stock": MUTED,
}
DRUG_CLASS_COLORS = {"Prescription-Only (Rx)": CAT[0], "Narcotic / Controlled": CAT[1], "OTC": CAT[2]}


# Dark mode is selected, not flipped: each light colour maps to its documented
# dark step. Chrome moves to dark inks/hairlines, categorical slots take their
# dark steps, and the heatmap's sequential ramp reverses so "near zero" recedes
# into the dark surface. Status colours and the ordinal blue steps (all >= 2:1
# on the dark surface) are unchanged.
_DARK = {
    INK: "#f5f5f2", INK_2: "#c3c2b7", GRID: "#2c2c2a", BASELINE: "#4a4a47",
    "#ffffff": "#262624",   # hover label background
    "#fcfcfb": "#121211",   # marker ring = page surface
    CAT[0]: "#3987e5", CAT[1]: "#d95926", CAT[2]: "#199e70", CAT[3]: "#c98500",
    CAT[4]: "#d55181", CAT[6]: "#9085e9", CAT[7]: "#e66767",
    BLUE[100]: BLUE[700], BLUE[650]: BLUE[200],
}


def _recolor(node, mapping: dict[str, str]):
    if isinstance(node, dict):
        return {k: _recolor(v, mapping) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_recolor(v, mapping) for v in node]
    if isinstance(node, np.ndarray) and node.dtype == object:
        return [_recolor(v, mapping) for v in node.tolist()]
    if isinstance(node, str):
        return mapping.get(node.lower(), node)
    return node


def _luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def _cell_ink(colorscale: list, fraction: float) -> str:
    """Dark or light ink for a heatmap cell, from the colour at ``fraction`` of the scale."""
    stops = [(float(pos), _luminance(color)) for pos, color in colorscale]
    lum = stops[-1][1]
    for (p0, l0), (p1, l1) in zip(stops, stops[1:]):
        if fraction <= p1:
            lum = l0 + (l1 - l0) * ((fraction - p0) / (p1 - p0) if p1 > p0 else 0)
            break
    return INK if lum > 150 else "#f5f5f2"


def _ink_heatmap_text(trace: dict, source) -> None:
    """Colour each cell label for contrast. Plotly does this itself on a light
    page, but the Streamlit dark template forces one light label colour.

    Values are read from ``source`` (the original trace): ``to_dict`` packs
    numeric arrays into a binary form."""
    text, z = source.text, source.z
    scale = trace.get("colorscale")
    if text is None or z is None or not scale:
        return
    zmin = float(source.zmin) if source.zmin is not None else 0.0
    zmax = float(source.zmax) if source.zmax is not None else 1.0
    out = []
    for row_text, row_z in zip(text, z):
        row = []
        for t, v in zip(row_text, row_z):
            ink = _cell_ink(scale, min(max((float(v) - zmin) / ((zmax - zmin) or 1.0), 0.0), 1.0))
            parts = [p.replace("<span style='", f"<span style='color:{ink};", 1) if p.startswith("<span style='")
                     else f"<span style='color:{ink}'>{p}</span>" for p in str(t).split("<br>")]
            row.append("<br>".join(parts))
        out.append(row)
    trace["text"] = out


def themed(fig: go.Figure, mode: str) -> go.Figure:
    """Return ``fig`` styled for ``mode`` ("light" or "dark"). Figures are built light."""
    if mode != "dark":
        return fig
    mapping = {k.lower(): v for k, v in _DARK.items()}
    spec = _recolor(fig.to_dict(), mapping)
    for trace, source in zip(spec.get("data", []), fig.data):
        if trace.get("type") == "heatmap":
            _ink_heatmap_text(trace, source)
    return go.Figure(spec)


def _money(v: float, cur: str) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    a = abs(v)
    if a >= 1_000_000:
        return f"{cur}{v / 1_000_000:.2f}M"
    if a >= 10_000:
        return f"{cur}{v / 1_000:.1f}K"
    return f"{cur}{v:,.0f}"


def _layout(fig: go.Figure, height: int = 360, showlegend: bool = False, **kw) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=16, t=16, b=8),
        font=dict(family=FONT, size=13, color=INK_2),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=showlegend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                    font=dict(color=INK_2)),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=BASELINE, font=dict(family=FONT, color=INK, size=12)),
        bargap=0.25,
        **kw,
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=BASELINE, zerolinecolor=BASELINE, tickfont=dict(color=MUTED),
                     title_font=dict(color=INK_2))
    fig.update_yaxes(gridcolor=GRID, linecolor=BASELINE, zerolinecolor=BASELINE, tickfont=dict(color=MUTED),
                     title_font=dict(color=INK_2))
    return fig


def empty_figure(message: str = "No data for the current filters", height: int = 240) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(color=MUTED, size=14), x=0.5, y=0.5,
                       xref="paper", yref="paper")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _layout(fig, height=height)


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def expiry_bucket_bar(b: pd.DataFrame, cur: str, height: int = 340) -> go.Figure:
    if b.empty:
        return empty_figure()
    g = (b.groupby("Expiry_Bucket", observed=False)
          .agg(value=("Stock_Value", "sum"), batches=("Batch_No", "count"), qty=("Qty_On_Hand", "sum"))
          .reindex(EXPIRY_BUCKETS).fillna(0).reset_index())
    g = g[(g["batches"] > 0) | g["Expiry_Bucket"].isin(EXPIRY_BUCKETS[:4])]
    fig = go.Figure(go.Bar(
        x=g["Expiry_Bucket"], y=g["value"],
        marker=dict(color=[EXPIRY_COLORS[k] for k in g["Expiry_Bucket"]], line=dict(width=0),
                    cornerradius=4),
        text=[_money(v, cur) for v in g["value"]], textposition="outside", textfont=dict(color=INK_2),
        customdata=np.stack([g["batches"], g["qty"]], axis=-1),
        hovertemplate="<b>%{x}</b><br>Value at cost: " + cur + "%{y:,.0f}<br>Batches: %{customdata[0]:.0f}"
                      "<br>Units: %{customdata[1]:,.0f}<extra></extra>",
        cliponaxis=False,
    ))
    fig.update_yaxes(title="Stock value at cost", tickprefix=cur, rangemode="tozero")
    return _layout(fig, height=height)


def expiry_timeline(b: pd.DataFrame, cur: str, reference: pd.Timestamp, horizon: int = 180,
                    height: int = 380) -> go.Figure:
    d = b[(b["Days_To_Expiry"].notna()) & (b["Days_To_Expiry"] <= horizon) & (b["Qty_On_Hand"] > 0)]
    if d.empty:
        return empty_figure(f"No batches expiring within {horizon} days")
    fig = go.Figure()
    for cls, color in DRUG_CLASS_COLORS.items():
        part = d[d["Drug_Class"] == cls]
        if part.empty:
            continue
        fig.add_trace(go.Scatter(
            x=part["Expiry_Date"], y=part["Stock_Value"], mode="markers", name=cls,
            marker=dict(size=11, color=color, line=dict(color="#fcfcfb", width=2),
                        symbol=np.where(part["Storage_Type"].ne("Room Temperature"), "diamond", "circle")),
            customdata=np.stack([part["Drug_Name"], part["Batch_No"], part["Qty_On_Hand"],
                                 part["Days_To_Expiry"], part["Storage_Type"], part["Location"]], axis=-1),
            hovertemplate="<b>%{customdata[0]}</b> · Batch %{customdata[1]}<br>Expires %{x|%d %b %Y} "
                          "(%{customdata[3]:.0f} days)<br>Qty %{customdata[2]:,.0f} · Value " + cur +
                          "%{y:,.0f}<br>%{customdata[4]} · %{customdata[5]}<extra></extra>",
        ))
    ref = pd.Timestamp(reference)
    for days, label in ((0, "Today"), (30, "30 d"), (60, "60 d"), (90, "90 d")):
        x = ref + pd.Timedelta(days=days)
        fig.add_vline(x=x, line=dict(color=CRITICAL if days == 0 else BASELINE, width=1, dash="dot"))
        fig.add_annotation(x=x, y=1, yref="paper", text=label, showarrow=False, yanchor="bottom",
                           font=dict(size=11, color=MUTED))
    fig.update_yaxes(title="Batch value at cost", tickprefix=cur, rangemode="tozero")
    fig.update_xaxes(title=None)
    _layout(fig, height=height, showlegend=True)
    fig.update_layout(margin=dict(l=8, r=16, t=28, b=8), legend=dict(y=-0.12, yanchor="top"))
    return fig


# ---------------------------------------------------------------------------
# Stock status / movement
# ---------------------------------------------------------------------------

def status_bar(sku: pd.DataFrame, height: int = 340) -> go.Figure:
    if sku.empty:
        return empty_figure()
    g = sku["Stock_Status"].value_counts().reindex(STOCK_STATUSES).fillna(0)
    g = g[g > 0][::-1]
    fig = go.Figure(go.Bar(
        y=g.index, x=g.values, orientation="h",
        marker=dict(color=[STATUS_COLORS[k] for k in g.index], cornerradius=4),
        text=[f"{int(v)}" for v in g.values], textposition="outside", textfont=dict(color=INK_2),
        hovertemplate="<b>%{y}</b><br>%{x} SKUs<extra></extra>", cliponaxis=False,
    ))
    fig.update_xaxes(title="Number of SKUs", range=[0, g.max() * 1.12])
    return _layout(fig, height=height)


def movement_value_bar(sku: pd.DataFrame, cur: str, height: int = 320) -> go.Figure:
    if sku.empty:
        return empty_figure()
    order = ["Fast-moving", "Normal", "Slow-moving", "Non-moving"]
    g = sku.groupby("Movement_Class")["Usable_Value"].sum().reindex(order).fillna(0)
    counts = sku["Movement_Class"].value_counts().reindex(order).fillna(0)
    fig = go.Figure(go.Bar(
        x=g.index, y=g.values, marker=dict(color=[MOVEMENT_COLORS[k] for k in g.index], cornerradius=4),
        text=[_money(v, cur) for v in g.values], textposition="outside", textfont=dict(color=INK_2),
        customdata=counts.values,
        hovertemplate="<b>%{x}</b><br>Usable value " + cur + "%{y:,.0f}<br>%{customdata:.0f} SKUs<extra></extra>",
        cliponaxis=False,
    ))
    fig.update_yaxes(title="Usable stock value", tickprefix=cur, rangemode="tozero")
    return _layout(fig, height=height)


def top_items_bar(df: pd.DataFrame, value_col: str, cur: str, color: str = BLUE[450], top: int = 12,
                  hover_cols: dict[str, str] | None = None, height: int | None = None,
                  x_title: str = "Value") -> go.Figure:
    d = df[df[value_col] > 0].nlargest(top, value_col)
    if d.empty:
        return empty_figure()
    d = d.iloc[::-1]
    labels = d["Drug_Name"] + " " + d["Strength"].astype(str)
    hover_cols = hover_cols or {}
    custom = np.stack([d[c].astype(str) for c in hover_cols], axis=-1) if hover_cols else None
    extra = "".join(f"<br>{label}: %{{customdata[{i}]}}" for i, label in enumerate(hover_cols.values()))
    fig = go.Figure(go.Bar(
        y=labels, x=d[value_col], orientation="h", marker=dict(color=color, cornerradius=4),
        text=[_money(v, cur) for v in d[value_col]], textposition="outside", textfont=dict(color=INK_2),
        customdata=custom, cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>" + x_title + ": " + cur + "%{x:,.0f}" + extra + "<extra></extra>",
    ))
    fig.update_xaxes(title=x_title, tickprefix=cur, range=[0, d[value_col].max() * 1.18])
    return _layout(fig, height=height or max(260, 34 * len(d) + 60))


def cover_vs_leadtime(sku: pd.DataFrame, top: int = 15, height: int | None = None) -> go.Figure:
    d = sku[sku["Stock_Status"].isin(["Stocked out", "Critical (below lead time)", "Reorder now"])].copy()
    if d.empty:
        return empty_figure("No SKUs at or below their reorder point")
    d["cover"] = d["Days_On_Hand"].replace(np.inf, np.nan).fillna(0)
    d = d.sort_values(["Priority_Score", "cover"], ascending=[False, True]).head(top).iloc[::-1]
    labels = d["Drug_Name"] + " (" + d["VEN_Class"] + ")"
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=d["cover"], orientation="h", name="Days of cover", showlegend=False,
        marker=dict(color=[STATUS_COLORS[s] for s in d["Stock_Status"]], cornerradius=4),
        text=["OUT" if v <= 0 else f"{v:.0f} d" for v in d["cover"]], textposition="outside",
        textfont=dict(color=INK_2), cliponaxis=False,
        customdata=np.stack([d["Stock_Status"], d["Usable_Qty"], d["Avg_Daily_Usage"]], axis=-1),
        hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>Days of cover: %{x:.1f}<br>Usable qty: "
                      "%{customdata[1]:,.0f}<br>Avg daily usage: %{customdata[2]:.1f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        y=labels, x=d["Lead_Time_Days"], mode="markers", name="Supplier lead time",
        marker=dict(symbol="line-ns", size=18, color=INK, line=dict(width=3, color=INK)),
        hovertemplate="<b>%{y}</b><br>Lead time: %{x:.0f} days<extra></extra>",
    ))
    fig.update_xaxes(title="Days", range=[0, max(d["cover"].max(), d["Lead_Time_Days"].max()) * 1.15])
    return _layout(fig, height=height or max(280, 32 * len(d) + 80), showlegend=True)


# ---------------------------------------------------------------------------
# ABC-VEN
# ---------------------------------------------------------------------------

def abc_ven_heatmap(sku: pd.DataFrame, metric: str, cur: str, height: int = 340) -> go.Figure:
    if sku.empty:
        return empty_figure()
    abc = ["A", "B", "C"]
    ven = ["V", "E", "N"]
    if metric == "value":
        pivot = sku.pivot_table(index="ABC_Class", columns="VEN_Class", values="Annual_Usage_Value",
                                aggfunc="sum", fill_value=0)
    else:
        pivot = sku.pivot_table(index="ABC_Class", columns="VEN_Class", values="SKU_Key",
                                aggfunc="count", fill_value=0)
    pivot = pivot.reindex(index=abc, columns=ven).fillna(0)
    cat = [[{"AV": "I", "AE": "I", "AN": "I", "BV": "I", "CV": "I", "BE": "II", "CE": "II", "BN": "II",
             "CN": "III"}[a + v] for v in ven] for a in abc]
    text = [[(_money(pivot.loc[a, v], cur) if metric == "value" else f"{int(pivot.loc[a, v])} SKUs")
             + f"<br><span style='font-size:11px'>{a}{v} · Cat {cat[i][j]}</span>"
             for j, v in enumerate(ven)] for i, a in enumerate(abc)]
    z = pivot.values
    zmax = z.max() if z.max() > 0 else 1
    fig = go.Figure(go.Heatmap(
        z=z, x=["Vital (V)", "Essential (E)", "Non-essential (N)"], y=["A (high value)", "B (medium)", "C (low value)"],
        colorscale=[[0, BLUE[100]], [0.5, BLUE[350]], [1, BLUE[650]]], zmin=0, zmax=zmax, showscale=False,
        text=text, texttemplate="%{text}", textfont=dict(size=14), xgap=3, ygap=3,
        customdata=cat,
        hovertemplate="<b>%{y} × %{x}</b><br>Category %{customdata}<br>"
                      + ("Annual consumption " + cur + "%{z:,.0f}" if metric == "value" else "%{z} SKUs")
                      + "<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(side="top", showgrid=False)
    return _layout(fig, height=height)


def pareto_curve(sku: pd.DataFrame, a_pct: float, b_pct: float, height: int = 340) -> go.Figure:
    d = sku[sku["Annual_Usage_Value"] > 0].sort_values("Annual_Usage_Value", ascending=False)
    if d.empty:
        return empty_figure("No consumption value to rank")
    d = d.assign(rank_pct=np.arange(1, len(d) + 1) / len(d) * 100)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["rank_pct"], y=d["Cum_Value_Pct"], mode="lines", line=dict(color=BLUE[450], width=2),
                             hoverinfo="skip", showlegend=False))
    for cls, color in (("A", CAT[0]), ("B", CAT[1]), ("C", CAT[2])):
        part = d[d["ABC_Class"] == cls]
        if part.empty:
            continue
        fig.add_trace(go.Scatter(
            x=part["rank_pct"], y=part["Cum_Value_Pct"], mode="markers", name=f"Class {cls}",
            marker=dict(size=9, color=color, line=dict(color="#fcfcfb", width=2)),
            customdata=np.stack([part["Drug_Name"], part["Annual_Usage_Value"]], axis=-1),
            hovertemplate="<b>%{customdata[0]}</b><br>Cumulative value %{y:.1f}%<br>Top %{x:.0f}% of items"
                          "<extra>Class " + cls + "</extra>",
        ))
    for y, label in ((a_pct, f"A ≤ {a_pct:.0f}%"), (b_pct, f"B ≤ {b_pct:.0f}%")):
        fig.add_hline(y=y, line=dict(color=BASELINE, width=1, dash="dot"))
        fig.add_annotation(x=1, y=y, text=label, showarrow=False, xanchor="left", yanchor="bottom",
                           font=dict(size=11, color=MUTED))
    fig.update_xaxes(title="% of items (ranked by annual consumption value)", ticksuffix="%", range=[0, 102])
    fig.update_yaxes(title="Cumulative % of value", ticksuffix="%", range=[0, 105])
    return _layout(fig, height=height, showlegend=True)


# ---------------------------------------------------------------------------
# Turnover / DOH / availability
# ---------------------------------------------------------------------------

DOH_BINS = [(-0.1, 0, "0 (out)"), (0, 15, "1–15"), (15, 30, "16–30"), (30, 60, "31–60"), (60, 90, "61–90"),
            (90, 180, "91–180"), (180, np.inf, ">180"), (np.inf, np.inf, "No demand")]


def doh_distribution(sku: pd.DataFrame, overstock_doh: int, height: int = 320) -> go.Figure:
    if sku.empty:
        return empty_figure()
    doh = sku["Days_On_Hand"]
    labels, counts, colors = [], [], []
    for lo, hi, label in DOH_BINS:
        if label == "No demand":
            n = int(np.isinf(doh).sum())
            color = MUTED
        elif label == "0 (out)":
            n = int((doh <= 0).sum())
            color = CRITICAL
        else:
            n = int(((doh > lo) & (doh <= hi) & np.isfinite(doh)).sum()) if np.isfinite(hi) else int(
                ((doh > lo) & np.isfinite(doh)).sum())
            color = SERIOUS if hi <= 15 else (BLUE[450] if lo >= overstock_doh else BLUE[300])
        labels.append(label)
        counts.append(n)
        colors.append(color)
    fig = go.Figure(go.Bar(
        x=labels, y=counts, marker=dict(color=colors, cornerradius=4),
        text=counts, textposition="outside", textfont=dict(color=INK_2), cliponaxis=False,
        hovertemplate="<b>%{x} days on hand</b><br>%{y} SKUs<extra></extra>",
    ))
    fig.update_xaxes(title="Days on hand (usable stock ÷ average daily usage)")
    fig.update_yaxes(title="Number of SKUs", rangemode="tozero")
    return _layout(fig, height=height)


def turnover_by_group(sku: pd.DataFrame, group: str, height: int | None = None) -> go.Figure:
    if sku.empty:
        return empty_figure()
    g = sku.groupby(group).agg(cogs=("Annual_Usage_Value", "sum"), inv=("Usable_Value", "sum"),
                               n=("SKU_Key", "count"))
    g = g[g["inv"] > 0]
    if g.empty:
        return empty_figure("No usable stock value in scope")
    g["turnover"] = g["cogs"] / g["inv"]
    g["doh"] = np.where(g["cogs"] > 0, g["inv"] / (g["cogs"] / 365), np.nan)
    g = g.sort_values("turnover")
    fig = go.Figure(go.Bar(
        y=g.index, x=g["turnover"], orientation="h", marker=dict(color=BLUE[450], cornerradius=4),
        text=[f"{v:.1f}×" for v in g["turnover"]], textposition="outside", textfont=dict(color=INK_2),
        customdata=np.stack([g["doh"], g["n"]], axis=-1), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Turnover %{x:.1f}× per year<br>Days on hand %{customdata[0]:.0f}"
                      "<br>%{customdata[1]:.0f} SKUs<extra></extra>",
    ))
    fig.update_xaxes(title="Annual inventory turnover (×)", range=[0, g["turnover"].max() * 1.15])
    return _layout(fig, height=height or max(260, 30 * len(g) + 70))


def availability_by(sku: pd.DataFrame, group: str, labels: dict[str, str] | None = None,
                    height: int = 300) -> go.Figure:
    if sku.empty:
        return empty_figure()
    g = sku.groupby(group).agg(total=("SKU_Key", "count"), avail=("Usable_Qty", lambda s: int((s > 0).sum())))
    g["pct"] = g["avail"] / g["total"] * 100
    if labels:
        g = g.reindex([k for k in labels if k in g.index])
        names = [labels[k] for k in g.index]
    else:
        names = list(g.index)
    colors = [GOOD if p >= 98 else WARNING if p >= 90 else CRITICAL for p in g["pct"]]
    fig = go.Figure(go.Bar(
        x=names, y=g["pct"], marker=dict(color=colors, cornerradius=4),
        text=[f"{p:.1f}%" for p in g["pct"]], textposition="outside", textfont=dict(color=INK_2),
        customdata=np.stack([g["avail"], g["total"]], axis=-1), cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>Availability %{y:.1f}%<br>%{customdata[0]:.0f} of %{customdata[1]:.0f} "
                      "SKUs in stock<extra></extra>",
    ))
    fig.add_hline(y=98, line=dict(color=BASELINE, width=1, dash="dot"))
    fig.add_annotation(x=1, xref="paper", y=98, text="98% target", showarrow=False, xanchor="right",
                       yanchor="bottom", font=dict(size=11, color=MUTED))
    fig.update_yaxes(title="SKUs with usable stock", ticksuffix="%", range=[0, 110])
    return _layout(fig, height=height)


def value_by_category(sku: pd.DataFrame, cur: str, top: int = 12, height: int | None = None) -> go.Figure:
    if sku.empty:
        return empty_figure()
    g = sku.groupby("Therapeutic_Category")["Stock_Value"].sum().nlargest(top)[::-1]
    fig = go.Figure(go.Bar(
        y=g.index, x=g.values, orientation="h", marker=dict(color=BLUE[450], cornerradius=4),
        text=[_money(v, cur) for v in g.values], textposition="outside", textfont=dict(color=INK_2),
        cliponaxis=False, hovertemplate="<b>%{y}</b><br>Stock value " + cur + "%{x:,.0f}<extra></extra>",
    ))
    fig.update_xaxes(title="Stock value at cost", tickprefix=cur, range=[0, g.max() * 1.18])
    return _layout(fig, height=height or max(280, 28 * len(g) + 70))
