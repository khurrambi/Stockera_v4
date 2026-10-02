"""Multi-sheet Excel action report."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from .analytics import Analysis
from .ui import LABELS


def _clean(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    d = df[[c for c in cols if c in df.columns]].copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].replace([np.inf, -np.inf], np.nan)
        elif isinstance(d[c].dtype, pd.CategoricalDtype):
            d[c] = d[c].astype(str)
    return d.rename(columns={c: LABELS.get(c, c) for c in d.columns})


def build_excel_report(a: Analysis, cur: str) -> bytes:
    k = a.kpis
    b, sku = a.batches, a.sku
    summary = pd.DataFrame([
        ("Reference date", str(a.settings.reference_date)),
        ("SKUs (drug × location)", k["sku_count"]),
        ("Batches", k["batch_count"]),
        (f"Inventory value at cost ({cur})", round(k["total_value"], 2)),
        (f"Expired stock value ({cur})", round(k["expired_value"], 2)),
        ("Expired batches", k["expired_batches"]),
        ("Expired controlled-drug batches", k["expired_cd_batches"]),
        (f"Near-expiry ≤90 d value ({cur})", round(k["near_expiry_value"], 2)),
        (f"Projected expiry loss, live stock ({cur})", round(k["projected_loss_value"], 2)),
        ("Stocked-out SKUs", k["stocked_out"]),
        ("Vital SKUs stocked out", k["vital_stocked_out"]),
        ("SKUs needing reorder", k["reorder_items"]),
        (f"Suggested order value ({cur})", round(k["reorder_value"], 2)),
        ("Overstocked SKUs", k["overstock_items"]),
        (f"Overstock excess value ({cur})", round(k["excess_value"], 2)),
        (f"Slow + non-moving value ({cur})", round(k["slow_value"], 2)),
        ("Inventory turnover (×/yr)", round(k["turnover"], 2) if np.isfinite(k["turnover"]) else ""),
        ("Days on hand (portfolio)", round(k["doh"], 1) if np.isfinite(k["doh"]) else ""),
        ("Stock availability %", round(k["availability"], 1) if np.isfinite(k["availability"]) else ""),
        ("Vital availability %", round(k["vital_availability"], 1) if np.isfinite(k["vital_availability"]) else ""),
    ], columns=["Metric", "Value"])

    expiry = b[b["Expiry_Bucket"].astype(str).isin(["Expired", "≤30 days", "31–60 days", "61–90 days", "Unknown expiry"])
               | (b["Projected_Unsold_Qty"] > 0)].sort_values(["Days_To_Expiry"], na_position="first")
    reorder = sku[sku["Suggested_Order_Qty"] > 0].sort_values(["Priority_Score", "Days_On_Hand"], ascending=[False, True])
    over = sku[sku["Is_Overstock"]].sort_values("Excess_Value", ascending=False)
    slow = sku[sku["Movement_Class"].isin(["Slow-moving", "Non-moving"])].sort_values("Slow_Moving_Value", ascending=False)

    sheets = {
        "Summary": summary,
        "Expiry & Compliance": _clean(expiry, [
            "Drug_ID", "Drug_Name", "Strength", "Drug_Class", "Storage_Type", "Batch_No", "Expiry_Date",
            "Days_To_Expiry", "Expiry_Bucket", "Qty_On_Hand", "Stock_Value", "Projected_Unsold_Qty",
            "Projected_Loss_Value", "Compliance_Flags", "Recommended_Action", "Location", "Supplier"]),
        "Reorder List": _clean(reorder, [
            "Priority", "Drug_ID", "Drug_Name", "Strength", "VEN_Class", "Stock_Status", "Usable_Qty",
            "Avg_Daily_Usage", "Days_On_Hand", "Lead_Time_Days", "Reorder_Point", "Suggested_Order_Qty",
            "Suggested_Order_Value", "Projected_Stockout_Date", "Supplier", "Location"]),
        "Overstock": _clean(over, [
            "Drug_ID", "Drug_Name", "Strength", "Therapeutic_Category", "Storage_Type", "Seasonal", "Usable_Qty",
            "Days_On_Hand", "Target_Max_Qty", "Excess_Qty", "Excess_Value", "Supplier", "Location"]),
        "Slow-Moving": _clean(slow, [
            "Drug_ID", "Drug_Name", "Strength", "Movement_Class", "Usable_Qty", "Units_Sold_90D", "Days_On_Hand",
            "Days_Since_Last_Sale", "Nearest_Expiry", "Slow_Moving_Value", "Location"]),
        "ABC-VEN": _clean(sku.sort_values("Annual_Usage_Value", ascending=False), [
            "Drug_ID", "Drug_Name", "Strength", "Annual_Usage_Value", "Cum_Value_Pct", "ABC_Class", "VEN_Class",
            "ABC_VEN", "ABC_VEN_Category", "Location"]),
        "All Batches": _clean(b, [
            "Drug_ID", "Drug_Name", "Generic_Name", "Strength", "Dosage_Form", "Therapeutic_Category", "Drug_Class",
            "VEN_Class", "Storage_Type", "Batch_No", "Manufacture_Date", "Expiry_Date", "Days_To_Expiry",
            "Qty_On_Hand", "Unit_Cost", "Stock_Value", "Location", "Supplier"]),
    }

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl", datetime_format="YYYY-MM-DD", date_format="YYYY-MM-DD") as xw:
        for name, frame in sheets.items():
            frame.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            ws.freeze_panes = "A2"
            for i, col in enumerate(frame.columns, start=1):
                sample = frame[col].head(200).map(lambda v: "" if pd.isna(v) else str(v))
                width = min(48, max(len(str(col)), int(sample.str.len().max() if len(sample) else 8)) + 2)
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    return buf.getvalue()
