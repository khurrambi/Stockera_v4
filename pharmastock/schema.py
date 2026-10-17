"""Dataset schema, file loading, cleaning and data-quality validation.

Every uploaded file passes through :func:`load_file` and then :func:`clean_dataset`.
Nothing in here raises on bad user data - problems are collected into a
:class:`QualityReport` so the UI can show them instead of crashing.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Canonical schema
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "Drug_Name",
    "Batch_No",
    "Expiry_Date",
    "Qty_On_Hand",
    "Unit_Cost",
    "Units_Sold_90D",
]

OPTIONAL_COLUMNS = [
    "Drug_ID",
    "Generic_Name",
    "Strength",
    "Dosage_Form",
    "Therapeutic_Category",
    "Drug_Class",
    "VEN_Class",
    "Storage_Type",
    "Manufacture_Date",
    "Unit_Price",
    "Last_Sale_Date",
    "Lead_Time_Days",
    "Reorder_Level",
    "Max_Stock_Level",
    "Supplier",
    "Location",
    "Seasonal",
]

ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

COLUMN_DESCRIPTIONS = {
    "Drug_ID": "Unique product/SKU code. Derived from name + strength if absent.",
    "Drug_Name": "Brand or trade name as dispensed.",
    "Generic_Name": "International non-proprietary name (INN).",
    "Strength": "e.g. 500mg, 100IU/mL.",
    "Dosage_Form": "Tablet, Capsule, Vial, Ampoule, Pen, Syrup ...",
    "Therapeutic_Category": "Clinical grouping, e.g. Anti-infective, Cardiovascular.",
    "Drug_Class": "Prescription-Only (Rx), Narcotic / Controlled, or OTC.",
    "VEN_Class": "Medical criticality: V (Vital), E (Essential), N (Non-essential).",
    "Storage_Type": "Room Temperature, Cold Chain (2-8°C) or Frozen.",
    "Batch_No": "Manufacturer batch / lot number (traceability & recalls).",
    "Manufacture_Date": "Date of manufacture.",
    "Expiry_Date": "Expiry date. MM/YYYY is read as the last day of that month.",
    "Qty_On_Hand": "Units physically in stock for this batch.",
    "Unit_Cost": "Purchase cost per unit.",
    "Unit_Price": "Selling / charge-out price per unit. Defaults to Unit_Cost.",
    "Units_Sold_90D": "Units dispensed/consumed from this batch in the last 90 days.",
    "Last_Sale_Date": "Date the product was last dispensed.",
    "Lead_Time_Days": "Supplier lead time in days. Default 7.",
    "Reorder_Level": "Optional fixed reorder point (units). Computed if blank.",
    "Max_Stock_Level": "Optional maximum stock (units). Used for overstock checks.",
    "Supplier": "Supplier / wholesaler name.",
    "Location": "Store, branch or ward.",
    "Seasonal": "Yes / No. Seasonal items such as flu vaccines.",
}

# Header aliases: normalised header (lowercase alphanumerics only) -> canonical name.
_ALIASES: dict[str, list[str]] = {
    "Drug_ID": ["drugid", "sku", "skuid", "itemcode", "productcode", "productid", "itemid", "ndc", "code"],
    "Drug_Name": ["drugname", "name", "productname", "itemname", "medicine", "medicinename", "drug", "brandname", "tradename", "description"],
    "Generic_Name": ["genericname", "generic", "inn", "molecule", "activeingredient"],
    "Strength": ["strength", "dose", "dosage"],
    "Dosage_Form": ["dosageform", "form", "formulation"],
    "Therapeutic_Category": ["therapeuticcategory", "category", "therapeuticclass", "therapeuticgroup", "atcgroup", "group"],
    "Drug_Class": ["drugclass", "class", "schedule", "legalclass", "classification", "rxstatus", "legalstatus"],
    "VEN_Class": ["venclass", "ven", "vencategory", "criticality"],
    "Storage_Type": ["storagetype", "storage", "storagerequirement", "storagecondition", "temperature"],
    "Batch_No": ["batchno", "batch", "batchnumber", "lot", "lotno", "lotnumber", "batchlot", "batchlotno"],
    "Manufacture_Date": ["manufacturedate", "mfgdate", "mfg", "manufacturingdate", "productiondate"],
    "Expiry_Date": ["expirydate", "expiry", "exp", "expdate", "expirationdate", "expiration", "bestbefore", "useby"],
    "Qty_On_Hand": ["qtyonhand", "quantityonhand", "qty", "quantity", "onhand", "stock", "stockqty", "currentstock", "soh", "stockonhand", "balance"],
    "Unit_Cost": ["unitcost", "cost", "costprice", "purchaseprice", "unitpurchaseprice", "buyprice"],
    "Unit_Price": ["unitprice", "price", "sellingprice", "mrp", "retailprice", "saleprice"],
    "Units_Sold_90D": ["unitssold90d", "sold90d", "sales90d", "unitssoldlast90days", "qtysold90d", "consumption90d", "usage90d", "dispensed90d", "unitssold"],
    "Last_Sale_Date": ["lastsaledate", "lastsale", "lastdispensed", "lastdispenseddate", "lastmovementdate", "lastissuedate"],
    "Lead_Time_Days": ["leadtimedays", "leadtime", "supplierleadtime"],
    "Reorder_Level": ["reorderlevel", "reorderpoint", "rop", "minstock", "minimumstock", "minlevel"],
    "Max_Stock_Level": ["maxstocklevel", "maxstock", "maximumstock", "maxlevel", "par", "parlevel"],
    "Supplier": ["supplier", "vendor", "wholesaler", "distributor"],
    "Location": ["location", "store", "branch", "site", "ward", "warehouse"],
    "Seasonal": ["seasonal", "isseasonal", "season"],
}

# Alternative demand input: average daily usage -> converted to 90-day units.
_ADU_ALIASES = ["avgdailyusage", "averagedailyusage", "adu", "dailyusage", "avgdailysales", "dailyconsumption"]

DRUG_CLASSES = ["Prescription-Only (Rx)", "Narcotic / Controlled", "OTC"]
VEN_LABELS = {"V": "Vital", "E": "Essential", "N": "Non-essential"}
STORAGE_TYPES = ["Room Temperature", "Cold Chain (2-8°C)", "Frozen"]


def _as_text(series: pd.Series) -> pd.Series:
    """Missing-safe string conversion (pandas 3 keeps NaN through ``astype(str)``)."""
    text = series.astype(object).where(series.notna(), "").astype(str).str.strip()
    return text.mask(text.str.lower().isin(["nan", "none", "null", "nat", "<na>"]), "")


def _norm(header: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


@dataclass
class QualityIssue:
    severity: str  # "error" | "warning" | "info"
    column: str
    message: str
    rows: int = 0


@dataclass
class QualityReport:
    source_rows: int = 0
    clean_rows: int = 0
    column_map: dict[str, str] = field(default_factory=dict)
    defaulted_columns: list[str] = field(default_factory=list)
    issues: list[QualityIssue] = field(default_factory=list)
    fatal: bool = False

    def add(self, severity: str, column: str, message: str, rows: int = 0) -> None:
        self.issues.append(QualityIssue(severity, column, message, int(rows)))
        if severity == "error" and rows == -1:
            self.fatal = True

    @property
    def score(self) -> float:
        """0-100 data-quality score: share of rows without any flagged problem."""
        if self.source_rows == 0 or self.fatal:
            return 0.0
        affected = sum(i.rows for i in self.issues if i.severity in ("error", "warning") and i.rows > 0)
        return max(0.0, 100.0 * (1 - min(affected, self.source_rows) / self.source_rows))

    def as_frame(self) -> pd.DataFrame:
        if not self.issues:
            return pd.DataFrame(columns=["Severity", "Column", "Issue", "Rows affected"])
        return pd.DataFrame(
            [{"Severity": i.severity.title(), "Column": i.column, "Issue": i.message,
              "Rows affected": i.rows if i.rows >= 0 else "All"} for i in self.issues]
        )


class DataLoadError(Exception):
    """Raised when a file cannot be read as a table at all."""


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_file(content: bytes, filename: str) -> pd.DataFrame:
    """Read CSV / TSV / TXT / XLSX / XLS bytes into a DataFrame of strings-or-values."""
    if not content or not content.strip():
        raise DataLoadError("The uploaded file is empty.")
    name = (filename or "").lower()

    if name.endswith((".xlsx", ".xlsm", ".xls")):
        try:
            df = pd.read_excel(io.BytesIO(content), sheet_name=0, dtype=object)
        except Exception as exc:  # corrupt workbook, missing engine, password protected ...
            raise DataLoadError(f"Could not read the Excel workbook: {exc}") from exc
    else:
        df = None
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = content.decode(encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
                continue
            try:
                df = pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str,
                                 skip_blank_lines=True, on_bad_lines="skip")
                break
            except pd.errors.EmptyDataError as exc:
                raise DataLoadError("The file has no columns or rows.") from exc
            except Exception as exc:
                last_error = exc
        if df is None:
            raise DataLoadError(f"Could not parse the file as CSV: {last_error}")

    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    if df.empty or len(df.columns) == 0:
        raise DataLoadError("The file contains headers only. No data rows were found.")
    return df


# ---------------------------------------------------------------------------
# Value parsers
# ---------------------------------------------------------------------------

_MONTH_YEAR = re.compile(r"^\s*(\d{1,2})\s*[/\-.]\s*(\d{4})\s*$")
_YEAR_MONTH = re.compile(r"^\s*(\d{4})\s*[/\-.]\s*(\d{1,2})\s*$")


def parse_dates(series: pd.Series, month_end: bool = False) -> pd.Series:
    """Parse a column of mixed-format dates.

    Handles ISO dates, day-first and month-first dates (whichever parses more
    rows wins), Excel serial numbers, datetime objects from Excel and
    pharmaceutical month/year formats (``03/2027``, ``2027-03``). When
    ``month_end`` is true, month/year values resolve to the last day of the
    month - the standard reading of an expiry printed as MM/YYYY.
    """
    if series.empty:
        return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    raw = series.copy()

    # Already datetime-like values (from Excel)
    is_dt = raw.map(lambda v: isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year") and hasattr(v, "month"))
    if is_dt.any():
        result.loc[is_dt] = pd.to_datetime(raw[is_dt], errors="coerce")

    text = _as_text(raw[~is_dt])
    text = text[~text.str.lower().isin(["", "-", "n/a", "na"])]
    if text.empty:
        return result

    # Month/year formats
    for pattern, month_group, year_group in ((_MONTH_YEAR, 1, 2), (_YEAR_MONTH, 2, 1)):
        m = text.str.extract(pattern)
        hit = m.notna().all(axis=1)
        if hit.any():
            months = pd.to_numeric(m.loc[hit, month_group - 1], errors="coerce")
            years = pd.to_numeric(m.loc[hit, year_group - 1], errors="coerce")
            valid = months.between(1, 12) & years.between(1900, 2200)
            idx = months[valid].index
            if len(idx):
                stamps = pd.to_datetime(
                    pd.DataFrame({"year": years[valid].astype(int), "month": months[valid].astype(int), "day": 1}),
                    errors="coerce",
                )
                if month_end:
                    stamps = stamps + pd.offsets.MonthEnd(0)
                result.loc[idx] = stamps
            text = text.drop(index=hit[hit].index)

    if text.empty:
        return result

    # Excel serial numbers (e.g. 46023)
    numeric = pd.to_numeric(text, errors="coerce")
    serial = numeric.between(20000, 80000)
    if serial.any():
        result.loc[serial[serial].index] = pd.to_datetime("1899-12-30") + pd.to_timedelta(numeric[serial], unit="D")
        text = text[~serial]
    if text.empty:
        return result

    iso = pd.to_datetime(text, errors="coerce", format="ISO8601")
    remaining = text[iso.isna()]
    if not remaining.empty:
        month_first = pd.to_datetime(remaining, errors="coerce", format="mixed", dayfirst=False)
        day_first = pd.to_datetime(remaining, errors="coerce", format="mixed", dayfirst=True)
        # Values with a first number > 12 can only be day-first; prefer whichever parses more.
        best = day_first if day_first.notna().sum() > month_first.notna().sum() else month_first
        iso.loc[remaining.index] = best
    result.loc[iso.index] = iso
    return result


def parse_numbers(series: pd.Series) -> pd.Series:
    """Parse numbers that may contain currency symbols, thousands separators or spaces."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").astype(float)
    text = _as_text(series)
    negative_paren = text.str.match(r"^\(.*\)$").astype(bool)
    cleaned = text.str.replace(r"[^\d.\-eE]", "", regex=True)
    values = pd.to_numeric(cleaned, errors="coerce")
    values[negative_paren] = -values[negative_paren].abs()
    return values.astype(float)


def _normalise_drug_class(value: object) -> str:
    v = str(value).strip().lower()
    if not v or v in ("nan", "none"):
        return "Prescription-Only (Rx)"
    if any(k in v for k in ("narc", "control", "cd", "schedule ii", "schedule 2", "opioid", "psychotropic", "sch-x", "schedule x")):
        return "Narcotic / Controlled"
    if any(k in v for k in ("otc", "over the counter", "over-the-counter", "gsl", "general sale", "non-prescription", "pharmacy medicine")):
        return "OTC"
    return "Prescription-Only (Rx)"


def _normalise_ven(value: object) -> str | None:
    v = str(value).strip().lower()
    if v.startswith("v"):
        return "V"
    if v.startswith("e"):
        return "E"
    if v.startswith("n") and v not in ("nan", "none", "null"):
        return "N"
    return None


def _normalise_storage(value: object) -> str:
    v = str(value).strip().lower()
    if any(k in v for k in ("frozen", "freez", "-20", "-25", "-70", "-80", "ultra")):
        return "Frozen"
    if any(k in v for k in ("cold", "fridge", "refrig", "2-8", "2 - 8", "2°", "2 to 8", "chill")):
        return "Cold Chain (2-8°C)"
    return "Room Temperature"


def _normalise_bool(value: object) -> bool:
    return str(value).strip().lower() in ("y", "yes", "true", "1", "seasonal", "t")


# ---------------------------------------------------------------------------
# Cleaning pipeline
# ---------------------------------------------------------------------------

def map_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str], bool]:
    """Rename user headers to canonical names. Returns (frame, mapping, used_adu)."""
    mapping: dict[str, str] = {}
    lookup: dict[str, str] = {}
    for canonical, aliases in _ALIASES.items():
        lookup[_norm(canonical)] = canonical
        for alias in aliases:
            lookup.setdefault(alias, canonical)

    used: set[str] = set()
    for col in df.columns:
        canonical = lookup.get(_norm(col))
        if canonical and canonical not in used:
            mapping[col] = canonical
            used.add(canonical)

    out = df.rename(columns=mapping)
    used_adu = False
    if "Units_Sold_90D" not in out.columns:
        for col in df.columns:
            if _norm(col) in _ADU_ALIASES and col not in mapping:
                out["Units_Sold_90D"] = parse_numbers(df[col]) * 90
                mapping[col] = "Units_Sold_90D (from daily usage × 90)"
                used_adu = True
                break
    return out, mapping, used_adu


def clean_dataset(raw: pd.DataFrame) -> tuple[pd.DataFrame, QualityReport]:
    """Map, type-cast, default and validate an uploaded dataset."""
    report = QualityReport(source_rows=len(raw))
    if raw is None or raw.empty:
        report.add("error", "-", "No data rows found.", -1)
        return pd.DataFrame(columns=ALL_COLUMNS), report

    df, mapping, used_adu = map_columns(raw.copy())
    report.column_map = mapping
    if used_adu:
        report.add("info", "Units_Sold_90D", "Demand derived from average daily usage × 90.")

    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    # Batch number can be defaulted (flagged as a traceability gap); others are fatal.
    fatal_missing = [c for c in missing_required if c != "Batch_No"]
    if fatal_missing:
        report.add("error", ", ".join(fatal_missing),
                   "Required column(s) not found. Rename your headers or use the sample template.", -1)
        return pd.DataFrame(columns=ALL_COLUMNS), report
    if "Batch_No" in missing_required:
        df["Batch_No"] = ""
        report.add("warning", "Batch_No", "No batch/lot column, so batch traceability is unavailable.", len(df))

    # --- Text columns --------------------------------------------------------
    for col in ("Drug_Name", "Batch_No", "Generic_Name", "Strength", "Dosage_Form",
                "Therapeutic_Category", "Supplier", "Location", "Drug_ID"):
        if col in df.columns:
            df[col] = _as_text(df[col])

    no_name = df["Drug_Name"].eq("")
    if no_name.any():
        report.add("warning", "Drug_Name", "Rows without a drug name were removed.", int(no_name.sum()))
        df = df[~no_name].copy()
    if df.empty:
        report.add("error", "Drug_Name", "No rows with a drug name remain.", -1)
        return pd.DataFrame(columns=ALL_COLUMNS), report

    defaults_text = {
        "Generic_Name": "",
        "Strength": "",
        "Dosage_Form": "Unspecified",
        "Therapeutic_Category": "Unclassified",
        "Supplier": "Unknown supplier",
        "Location": "Main Pharmacy",
    }
    for col, default in defaults_text.items():
        if col not in df.columns:
            df[col] = default
            report.defaulted_columns.append(col)
        else:
            df[col] = df[col].replace("", default)

    if "Drug_ID" not in df.columns:
        df["Drug_ID"] = ""
        report.defaulted_columns.append("Drug_ID")
    derived_id = (df["Drug_Name"] + " " + df["Strength"]).str.strip().str.upper()
    df["Drug_ID"] = df["Drug_ID"].where(df["Drug_ID"].ne(""), derived_id)

    missing_batch = df["Batch_No"].eq("")
    if missing_batch.any() and "Batch_No" not in missing_required:
        report.add("warning", "Batch_No", "Missing batch/lot number. These rows cannot be traced in a recall.",
                   int(missing_batch.sum()))
    df.loc[missing_batch, "Batch_No"] = "UNKNOWN-BATCH"

    # --- Categorical columns --------------------------------------------------
    if "Drug_Class" in df.columns:
        df["Drug_Class"] = df["Drug_Class"].map(_normalise_drug_class)
    else:
        df["Drug_Class"] = "Prescription-Only (Rx)"
        report.defaulted_columns.append("Drug_Class")

    if "VEN_Class" in df.columns:
        ven = df["VEN_Class"].map(_normalise_ven)
        bad_ven = ven.isna()
        if bad_ven.any():
            report.add("warning", "VEN_Class",
                       "Missing/unrecognised VEN class defaulted to 'E' (Essential). Review clinically.",
                       int(bad_ven.sum()))
        df["VEN_Class"] = ven.fillna("E")
    else:
        df["VEN_Class"] = "E"
        report.defaulted_columns.append("VEN_Class")
        report.add("warning", "VEN_Class", "No VEN column, so all items are treated as Essential.", len(df))

    if "Storage_Type" in df.columns:
        df["Storage_Type"] = df["Storage_Type"].map(_normalise_storage)
    else:
        df["Storage_Type"] = "Room Temperature"
        report.defaulted_columns.append("Storage_Type")

    if "Seasonal" in df.columns:
        df["Seasonal"] = df["Seasonal"].map(_normalise_bool)
    else:
        df["Seasonal"] = False
        report.defaulted_columns.append("Seasonal")

    # --- Dates -----------------------------------------------------------------
    df["Expiry_Date"] = parse_dates(df["Expiry_Date"], month_end=True)
    bad_expiry = df["Expiry_Date"].isna()
    if bad_expiry.any():
        report.add("error", "Expiry_Date",
                   "Missing or unreadable expiry date. Rows are kept and flagged 'Unknown expiry' for a physical check.",
                   int(bad_expiry.sum()))

    for col in ("Manufacture_Date", "Last_Sale_Date"):
        if col in df.columns:
            original_present = _as_text(df[col]).ne("")
            df[col] = parse_dates(df[col])
            unreadable = original_present & df[col].isna()
            if unreadable.any():
                report.add("warning", col, "Unreadable dates ignored.", int(unreadable.sum()))
        else:
            df[col] = pd.NaT
            report.defaulted_columns.append(col)

    if "Manufacture_Date" in df.columns:
        inverted = df["Manufacture_Date"].notna() & df["Expiry_Date"].notna() & (df["Manufacture_Date"] > df["Expiry_Date"])
        if inverted.any():
            report.add("warning", "Manufacture_Date", "Manufacture date is after expiry date. Check the data entry.",
                       int(inverted.sum()))

    # --- Numbers ---------------------------------------------------------------
    for col in ("Qty_On_Hand", "Unit_Cost", "Units_Sold_90D"):
        values = parse_numbers(df[col])
        unreadable = values.isna()
        if unreadable.any():
            report.add("warning", col, "Missing or non-numeric values treated as 0.", int(unreadable.sum()))
        negative = values < 0
        if negative.any():
            report.add("warning", col, "Negative values set to 0.", int(negative.sum()))
        df[col] = values.fillna(0).clip(lower=0)

    zero_cost = df["Unit_Cost"].eq(0)
    if zero_cost.any():
        report.add("info", "Unit_Cost", "Zero unit cost: these items carry no value in ABC or cash metrics.",
                   int(zero_cost.sum()))

    if "Unit_Price" in df.columns:
        price = parse_numbers(df["Unit_Price"]).clip(lower=0)
        df["Unit_Price"] = price.fillna(df["Unit_Cost"])
    else:
        df["Unit_Price"] = df["Unit_Cost"]
        report.defaulted_columns.append("Unit_Price")

    if "Lead_Time_Days" in df.columns:
        lead = parse_numbers(df["Lead_Time_Days"])
        df["Lead_Time_Days"] = lead.where(lead > 0).fillna(7)
    else:
        df["Lead_Time_Days"] = 7.0
        report.defaulted_columns.append("Lead_Time_Days")

    for col in ("Reorder_Level", "Max_Stock_Level"):
        if col in df.columns:
            v = parse_numbers(df[col])
            df[col] = v.where(v > 0)
        else:
            df[col] = np.nan
            report.defaulted_columns.append(col)

    # --- Duplicates ------------------------------------------------------------
    dup = df.duplicated(subset=["Drug_ID", "Batch_No", "Location"], keep=False) & df["Batch_No"].ne("UNKNOWN-BATCH")
    if dup.any():
        report.add("warning", "Batch_No",
                   "Duplicate Drug + Batch + Location rows found. Quantities are summed per SKU.",
                   int(dup.sum()))

    if report.defaulted_columns:
        report.add("info", ", ".join(report.defaulted_columns), "Optional column(s) not supplied; defaults applied.")

    df = df[ALL_COLUMNS].reset_index(drop=True)
    report.clean_rows = len(df)
    return df, report


def template_frame() -> pd.DataFrame:
    """A one-row template showing every supported column."""
    return pd.DataFrame(
        [{
            "Drug_ID": "PS-001", "Drug_Name": "Paracetamol", "Generic_Name": "Acetaminophen",
            "Strength": "500mg", "Dosage_Form": "Tablet", "Therapeutic_Category": "Analgesic",
            "Drug_Class": "OTC", "VEN_Class": "E", "Storage_Type": "Room Temperature",
            "Batch_No": "PCM-2409-A", "Manufacture_Date": "2025-01-15", "Expiry_Date": "2027-01-31",
            "Qty_On_Hand": 5000, "Unit_Cost": 0.02, "Unit_Price": 0.05, "Units_Sold_90D": 18000,
            "Last_Sale_Date": "2026-09-18", "Lead_Time_Days": 7, "Reorder_Level": "",
            "Max_Stock_Level": "", "Supplier": "MedSupply Distributors", "Location": "Main Pharmacy",
            "Seasonal": "No",
        }],
        columns=[c for c in COLUMN_DESCRIPTIONS],
    )
