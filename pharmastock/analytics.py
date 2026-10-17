"""Inventory analytics for pharmacy stock.

Two levels of analysis:

* **Batch level** (one row per batch/lot): expiry status, FEFO projected
  loss, compliance flags and recommended action.
* **SKU level** (one row per Drug_ID × Location): demand, days on hand,
  turnover, movement class, stockout risk and reorder suggestion, overstock
  excess, ABC, VEN and the ABC-VEN matrix category.

Expired stock is never counted as usable: it cannot be dispensed, so it does
not protect against a stockout and it does not count toward days on hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

EXPIRY_BUCKETS = [
    "Expired",
    "≤30 days",
    "31–60 days",
    "61–90 days",
    "91–180 days",
    ">180 days",
    "Unknown expiry",
]

MOVEMENT_CLASSES = ["Fast-moving", "Normal", "Slow-moving", "Non-moving", "Out of stock"]
STOCK_STATUSES = ["Stocked out", "Critical (below lead time)", "Reorder now", "Healthy", "Overstock", "No demand"]
ABC_VEN_CATEGORY = {
    "AV": "I", "AE": "I", "AN": "I", "BV": "I", "CV": "I",
    "BE": "II", "CE": "II", "BN": "II",
    "CN": "III",
}
ABC_VEN_CATEGORY_POLICY = {
    "I": "Tight control: weekly review, never out of stock (Vital) or lean ordering (high value).",
    "II": "Moderate control: monthly review, standard safety stock.",
    "III": "Low priority: quarterly review, minimal stock, candidate for formulary rationalisation.",
}
_VEN_RANK = {"V": 0, "E": 1, "N": 2}
_VEN_WEIGHT = {"V": 3, "E": 2, "N": 1}
_URGENCY = {"Stocked out": 3, "Critical (below lead time)": 2, "Reorder now": 1}


@dataclass(frozen=True)
class Settings:
    reference_date: date = field(default_factory=date.today)
    slow_moving_doh: int = 180
    non_moving_days: int = 90
    fast_turnover: float = 12.0
    overstock_doh: int = 120
    target_cover_days: int = 30
    safety_days_v: int = 14
    safety_days_e: int = 7
    safety_days_n: int = 3
    abc_a_pct: float = 80.0
    abc_b_pct: float = 95.0

    def safety_days(self, ven: str) -> int:
        return {"V": self.safety_days_v, "E": self.safety_days_e}.get(ven, self.safety_days_n)


@dataclass
class Analysis:
    batches: pd.DataFrame
    sku: pd.DataFrame
    kpis: dict
    settings: Settings


# ---------------------------------------------------------------------------
# Batch level
# ---------------------------------------------------------------------------

def _expiry_bucket(days: pd.Series) -> pd.Series:
    bucket = pd.Series("Unknown expiry", index=days.index, dtype=object)
    bucket[days < 0] = "Expired"
    bucket[(days >= 0) & (days <= 30)] = "≤30 days"
    bucket[(days > 30) & (days <= 60)] = "31–60 days"
    bucket[(days > 60) & (days <= 90)] = "61–90 days"
    bucket[(days > 90) & (days <= 180)] = "91–180 days"
    bucket[days > 180] = ">180 days"
    return pd.Categorical(bucket, categories=EXPIRY_BUCKETS, ordered=True)


def enrich_batches(df: pd.DataFrame, s: Settings) -> pd.DataFrame:
    b = df.copy()
    ref = pd.Timestamp(s.reference_date)
    b["SKU_Key"] = b["Drug_ID"].astype(str) + " | " + b["Location"].astype(str)
    b["Days_To_Expiry"] = (b["Expiry_Date"] - ref).dt.days
    b["Expiry_Bucket"] = _expiry_bucket(b["Days_To_Expiry"])
    b["Is_Expired"] = b["Days_To_Expiry"] < 0
    b["Usable_Qty"] = np.where(b["Is_Expired"], 0.0, b["Qty_On_Hand"])
    b["Stock_Value"] = b["Qty_On_Hand"] * b["Unit_Cost"]
    b["Usable_Value"] = b["Usable_Qty"] * b["Unit_Cost"]
    b["Retail_Value"] = b["Qty_On_Hand"] * b["Unit_Price"]
    return b


def _fefo_projection(b: pd.DataFrame, adu: pd.Series) -> pd.DataFrame:
    """Project how much of each batch will NOT be dispensed before it expires.

    Batches are consumed First-Expiry-First-Out at the SKU's average daily
    usage. A batch's sellable volume is the demand between today and its
    expiry, minus what earlier-expiring batches already absorb.
    """
    b = b.copy()
    b["_adu"] = b["SKU_Key"].map(adu).fillna(0.0)
    b["Projected_Unsold_Qty"] = 0.0

    live = b[~b["Is_Expired"] & b["Days_To_Expiry"].notna()].sort_values(["SKU_Key", "Expiry_Date", "Batch_No"])
    if not live.empty:
        prior = live.groupby("SKU_Key")["Qty_On_Hand"].cumsum() - live["Qty_On_Hand"]
        demand_until_expiry = live["_adu"] * live["Days_To_Expiry"].clip(lower=0)
        sellable = (demand_until_expiry - prior).clip(lower=0)
        sellable = np.minimum(sellable, live["Qty_On_Hand"])
        b.loc[live.index, "Projected_Unsold_Qty"] = (live["Qty_On_Hand"] - sellable).round(0)

    b.loc[b["Is_Expired"], "Projected_Unsold_Qty"] = b.loc[b["Is_Expired"], "Qty_On_Hand"]
    b["Projected_Loss_Value"] = b["Projected_Unsold_Qty"] * b["Unit_Cost"]
    return b.drop(columns="_adu")


def _batch_actions(b: pd.DataFrame) -> pd.DataFrame:
    b = b.copy()
    narcotic = b["Drug_Class"].eq("Narcotic / Controlled")
    cold = b["Storage_Type"].ne("Room Temperature")
    bucket = b["Expiry_Bucket"].astype(str)
    unsold = b["Projected_Unsold_Qty"]

    action = pd.Series("No action needed: within shelf life", index=b.index, dtype=object)
    action[bucket.eq("91–180 days") & (unsold > 0)] = "Plan ahead: surplus projected at expiry. Slow reorders and offer an inter-branch transfer."
    action[bucket.eq("61–90 days")] = "Monitor: flag on shelf, enforce FEFO rotation, stop reordering this batch."
    action[bucket.eq("61–90 days") & (unsold > 0)] = "Act now: surplus will expire. Arrange a supplier return, credit or transfer."
    action[bucket.eq("31–60 days")] = "Dispense these first (FEFO); ask the supplier for a return or credit on any surplus."
    action[bucket.eq("≤30 days")] = "Urgent: dispense first, return/transfer surplus, prepare quarantine at expiry."
    action[bucket.eq("Expired")] = "Quarantine now: remove from dispensing stock and arrange return or destruction."
    action[bucket.eq("Expired") & narcotic] = (
        "Quarantine in the CD cabinet. Witnessed destruction and a controlled-drug register entry are required."
    )
    action[bucket.eq("Unknown expiry")] = "Physically verify expiry date and correct the stock record."
    b["Recommended_Action"] = action

    flags = pd.DataFrame(index=b.index)
    flags["expired"] = np.where(bucket.eq("Expired"), "EXPIRED: do not dispense", "")
    flags["cd"] = np.where(narcotic, "Controlled drug", "")
    flags["cold"] = np.where(cold, "Cold chain: check temp. log", "")
    flags["batch"] = np.where(b["Batch_No"].eq("UNKNOWN-BATCH"), "No batch no. (recall risk)", "")
    flags["expiry"] = np.where(bucket.eq("Unknown expiry"), "Expiry not recorded", "")
    b["Compliance_Flags"] = flags.apply(lambda r: " · ".join(v for v in r if v), axis=1)
    return b


# ---------------------------------------------------------------------------
# SKU level
# ---------------------------------------------------------------------------

def _most_critical_ven(values: pd.Series) -> str:
    vals = [v for v in values if v in _VEN_RANK]
    return min(vals, key=_VEN_RANK.get) if vals else "E"


def build_sku(b: pd.DataFrame, s: Settings) -> pd.DataFrame:
    ref = pd.Timestamp(s.reference_date)
    live_expiry = b["Expiry_Date"].where(~b["Is_Expired"])
    b = b.assign(_live_expiry=live_expiry)

    g = b.groupby("SKU_Key", sort=False)
    sku = g.agg(
        Drug_ID=("Drug_ID", "first"),
        Location=("Location", "first"),
        Drug_Name=("Drug_Name", "first"),
        Generic_Name=("Generic_Name", "first"),
        Strength=("Strength", "first"),
        Dosage_Form=("Dosage_Form", "first"),
        Therapeutic_Category=("Therapeutic_Category", "first"),
        Drug_Class=("Drug_Class", "first"),
        VEN_Class=("VEN_Class", _most_critical_ven),
        Storage_Type=("Storage_Type", "first"),
        Supplier=("Supplier", "first"),
        Seasonal=("Seasonal", "any"),
        Lead_Time_Days=("Lead_Time_Days", "max"),
        Reorder_Level=("Reorder_Level", "max"),
        Max_Stock_Level=("Max_Stock_Level", "max"),
        Batches=("Batch_No", "nunique"),
        Qty_On_Hand=("Qty_On_Hand", "sum"),
        Usable_Qty=("Usable_Qty", "sum"),
        Units_Sold_90D=("Units_Sold_90D", "sum"),
        Last_Sale_Date=("Last_Sale_Date", "max"),
        Stock_Value=("Stock_Value", "sum"),
        Usable_Value=("Usable_Value", "sum"),
        Projected_Loss_Value=("Projected_Loss_Value", "sum"),
        Nearest_Expiry=("_live_expiry", "min"),
        _mean_cost=("Unit_Cost", "mean"),
        _mean_price=("Unit_Price", "mean"),
    )
    sku["Expired_Qty"] = sku["Qty_On_Hand"] - sku["Usable_Qty"]
    sku["Expired_Value"] = sku["Stock_Value"] - sku["Usable_Value"]

    qty = sku["Qty_On_Hand"]
    sku["Unit_Cost"] = np.where(qty > 0, sku["Stock_Value"] / qty.replace(0, np.nan), sku["_mean_cost"])
    sku["Unit_Price"] = sku["_mean_price"]
    sku = sku.drop(columns=["_mean_cost", "_mean_price"])

    # --- Demand, cover and turnover -------------------------------------------
    adu = sku["Units_Sold_90D"] / 90.0
    sku["Avg_Daily_Usage"] = adu
    usable = sku["Usable_Qty"]
    with np.errstate(divide="ignore", invalid="ignore"):
        doh = np.where(adu > 0, usable / adu, np.where(usable > 0, np.inf, 0.0))
    sku["Days_On_Hand"] = doh
    sku["Annual_Usage_Value"] = adu * 365 * sku["Unit_Cost"]
    sku["Turnover_Annual"] = np.where(sku["Usable_Value"] > 0,
                                      sku["Annual_Usage_Value"] / sku["Usable_Value"].replace(0, np.nan), np.nan)
    sku["Days_Since_Last_Sale"] = (ref - sku["Last_Sale_Date"]).dt.days
    sku["Days_Since_Last_Sale"] = sku["Days_Since_Last_Sale"].astype(float)

    # --- Movement class (slow / non-moving) ------------------------------------
    since = sku["Days_Since_Last_Sale"]
    movement = pd.Series("Normal", index=sku.index, dtype=object)
    movement[sku["Turnover_Annual"] >= s.fast_turnover] = "Fast-moving"
    movement[sku["Days_On_Hand"] > s.slow_moving_doh] = "Slow-moving"
    movement[(sku["Units_Sold_90D"] <= 0) | (since > s.non_moving_days)] = "Non-moving"
    movement[usable <= 0] = "Out of stock"
    sku["Movement_Class"] = movement
    sku["Slow_Moving_Value"] = np.where(movement.isin(["Slow-moving", "Non-moving"]), sku["Usable_Value"], 0.0)

    # --- Reorder point, overstock and stock status -------------------------------
    safety_days = sku["VEN_Class"].map(s.safety_days)
    sku["Safety_Stock"] = (adu * safety_days).round(1)
    computed_rop = adu * sku["Lead_Time_Days"] + sku["Safety_Stock"]
    sku["Reorder_Point"] = sku["Reorder_Level"].fillna(computed_rop).round(1)
    sku["ROP_Source"] = np.where(sku["Reorder_Level"].notna(), "Supplied", "Calculated")

    has_max = sku["Max_Stock_Level"].notna()
    target_max = sku["Max_Stock_Level"].where(has_max, adu * s.overstock_doh)
    overstock = (usable > target_max) & ((adu > 0) | has_max)
    sku["Is_Overstock"] = overstock
    sku["Target_Max_Qty"] = target_max.round(0)
    sku["Excess_Qty"] = np.where(overstock, (usable - target_max).round(0), 0.0)
    sku["Excess_Value"] = sku["Excess_Qty"] * sku["Unit_Cost"]

    status = pd.Series("Healthy", index=sku.index, dtype=object)
    status[overstock] = "Overstock"
    status[(adu <= 0) & (usable > 0) & ~has_max] = "No demand"
    status[(usable <= sku["Reorder_Point"]) & (adu > 0)] = "Reorder now"
    status[(sku["Days_On_Hand"] < sku["Lead_Time_Days"]) & (adu > 0)] = "Critical (below lead time)"
    # A zero balance is a stockout when patients need it (demand, or Vital by definition);
    # otherwise it is simply an item nobody is asking for.
    status[(usable <= 0) & ((adu > 0) | sku["VEN_Class"].eq("V"))] = "Stocked out"
    status[(usable <= 0) & (adu <= 0) & sku["VEN_Class"].ne("V")] = "No demand"
    sku["Stock_Status"] = status

    finite_doh = pd.Series(doh, index=sku.index).replace(np.inf, np.nan)
    sku["Projected_Stockout_Date"] = ref + pd.to_timedelta(finite_doh.where(adu > 0).round(0), unit="D")
    sku["Stockout_Before_Delivery"] = (finite_doh < sku["Lead_Time_Days"]) & (adu > 0)

    needs_order = status.isin(list(_URGENCY))
    order_up_to = adu * (sku["Lead_Time_Days"] + s.target_cover_days) + sku["Safety_Stock"]
    order_qty = np.ceil((order_up_to - usable).clip(lower=0))
    order_qty = np.where(has_max, np.minimum(order_qty, (sku["Max_Stock_Level"] - usable).clip(lower=0)), order_qty)
    # Vital items with no recent demand (e.g. antidotes) still need a minimum emergency stock.
    vital_floor = np.ceil(sku["Reorder_Level"].fillna(1.0))
    order_qty = np.where(sku["VEN_Class"].eq("V") & (adu <= 0), np.maximum(order_qty, vital_floor - usable), order_qty)
    sku["Suggested_Order_Qty"] = np.where(needs_order, order_qty, 0.0)
    sku["Suggested_Order_Value"] = sku["Suggested_Order_Qty"] * sku["Unit_Cost"]
    sku["Daily_Revenue_At_Risk"] = np.where(status.eq("Stocked out"), adu * sku["Unit_Price"], 0.0)

    score = status.map(_URGENCY).fillna(0) * sku["VEN_Class"].map(_VEN_WEIGHT).fillna(1)
    sku["Priority_Score"] = score
    sku["Priority"] = np.select([score >= 6, score >= 3, score > 0],
                                ["P1 (immediate)", "P2 (urgent)", "P3 (routine)"], default="")

    # --- ABC & ABC-VEN ---------------------------------------------------------
    sku = _abc(sku, s)
    sku["ABC_VEN"] = sku["ABC_Class"] + sku["VEN_Class"]
    sku["ABC_VEN_Category"] = sku["ABC_VEN"].map(ABC_VEN_CATEGORY).fillna("II")
    return sku.reset_index()


def _abc(sku: pd.DataFrame, s: Settings) -> pd.DataFrame:
    sku = sku.copy()
    value = sku["Annual_Usage_Value"].fillna(0)
    total = value.sum()
    if total <= 0:
        sku["Cum_Value_Pct"] = 100.0
        sku["ABC_Class"] = "C"
        return sku
    order = value.sort_values(ascending=False, kind="mergesort").index
    cum = value.loc[order].cumsum() / total * 100
    prev = cum.shift(fill_value=0)
    abc = pd.Series("C", index=order, dtype=object)
    abc[prev < s.abc_b_pct] = "B"
    abc[prev < s.abc_a_pct] = "A"
    abc[value.loc[order] <= 0] = "C"
    sku["Cum_Value_Pct"] = cum
    sku["ABC_Class"] = abc
    return sku


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _safe_ratio(num: float, den: float) -> float:
    return float(num / den) if den else float("nan")


def compute_kpis(b: pd.DataFrame, sku: pd.DataFrame) -> dict:
    annual_cogs = float(sku["Annual_Usage_Value"].sum())
    usable_value = float(sku["Usable_Value"].sum())
    vital = sku[sku["VEN_Class"].eq("V")]
    bucket = b["Expiry_Bucket"].astype(str)
    near = bucket.isin(["≤30 days", "31–60 days", "61–90 days"])
    return {
        "sku_count": int(len(sku)),
        "batch_count": int(len(b)),
        "location_count": int(b["Location"].nunique()),
        "total_value": float(b["Stock_Value"].sum()),
        "retail_value": float(b["Retail_Value"].sum()),
        "usable_value": usable_value,
        "expired_value": float(b.loc[bucket.eq("Expired"), "Stock_Value"].sum()),
        "expired_batches": int(bucket.eq("Expired").sum()),
        "expired_cd_batches": int((bucket.eq("Expired") & b["Drug_Class"].eq("Narcotic / Controlled")).sum()),
        "near_expiry_value": float(b.loc[near, "Stock_Value"].sum()),
        "near_expiry_batches": int(near.sum()),
        "exp30_batches": int(bucket.eq("≤30 days").sum()),
        "exp30_value": float(b.loc[bucket.eq("≤30 days"), "Stock_Value"].sum()),
        "exp60_value": float(b.loc[bucket.eq("31–60 days"), "Stock_Value"].sum()),
        "exp90_value": float(b.loc[bucket.eq("61–90 days"), "Stock_Value"].sum()),
        "unknown_expiry_batches": int(bucket.eq("Unknown expiry").sum()),
        "projected_loss_value": float(b.loc[~b["Is_Expired"], "Projected_Loss_Value"].sum()),
        "stocked_out": int(sku["Stock_Status"].eq("Stocked out").sum()),
        "vital_stocked_out": int((vital["Stock_Status"] == "Stocked out").sum()),
        "critical_items": int(sku["Stock_Status"].eq("Critical (below lead time)").sum()),
        "vital_critical": int((vital["Stock_Status"] == "Critical (below lead time)").sum()),
        "reorder_items": int(sku["Stock_Status"].isin(list(_URGENCY)).sum()),
        "reorder_value": float(sku["Suggested_Order_Value"].sum()),
        "overstock_items": int(sku["Is_Overstock"].sum()),
        "excess_value": float(sku["Excess_Value"].sum()),
        "slow_items": int(sku["Movement_Class"].eq("Slow-moving").sum()),
        "non_moving_items": int(sku["Movement_Class"].eq("Non-moving").sum()),
        "slow_value": float(sku["Slow_Moving_Value"].sum()),
        "turnover": _safe_ratio(annual_cogs, usable_value),
        "doh": _safe_ratio(usable_value, annual_cogs / 365) if annual_cogs else float("nan"),
        "availability": _safe_ratio((sku["Usable_Qty"] > 0).sum(), len(sku)) * 100 if len(sku) else float("nan"),
        "vital_availability": _safe_ratio((vital["Usable_Qty"] > 0).sum(), len(vital)) * 100 if len(vital) else float("nan"),
        "cold_chain_value": float(b.loc[b["Storage_Type"].ne("Room Temperature"), "Stock_Value"].sum()),
        "cd_batches": int(b["Drug_Class"].eq("Narcotic / Controlled").sum()),
        "daily_revenue_at_risk": float(sku["Daily_Revenue_At_Risk"].sum()),
    }


def run_analysis(df: pd.DataFrame, s: Settings) -> Analysis:
    """Full pipeline on a cleaned dataset (see ``schema.clean_dataset``)."""
    b = enrich_batches(df, s)
    # Demand is a SKU property: batch-level units sold are summed per SKU first.
    adu = b.groupby("SKU_Key")["Units_Sold_90D"].sum() / 90.0
    b = _fefo_projection(b, adu)
    b = _batch_actions(b)
    sku = build_sku(b, s)
    b = b.merge(sku[["SKU_Key", "ABC_Class", "ABC_VEN", "ABC_VEN_Category", "Stock_Status", "Movement_Class"]],
                on="SKU_Key", how="left")
    return Analysis(batches=b, sku=sku, kpis=compute_kpis(b, sku), settings=s)
