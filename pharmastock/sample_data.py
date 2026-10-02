"""Deterministic sample dataset for demos and testing.

Dates are generated relative to a reference date so the demo always shows
expired, near-expiry, stockout, overstock and slow-moving scenarios no matter
when it is run. Run this module directly to (re)write the sample CSV:

    python -m pharmastock.sample_data
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

MAIN = "Main Pharmacy"
ICU = "ICU Satellite Store"

SUP_GEN = "MedSupply Distributors"
SUP_WHS = "PharmaLink Wholesale"
SUP_BIO = "ColdChain Biologics Ltd"
SUP_VAC = "National Vaccine Program"
SUP_CD = "Controlled Drugs Depot"

RX, CD, OTC = "Prescription-Only", "Narcotic", "OTC"
ROOM, COLD = "Room Temperature", "Cold Chain (2-8°C)"

# (id, name, generic, strength, form, category, class, VEN, storage, cost, price,
#  supplier, lead_days, seasonal, units_sold_90d, last_sale_days_ago, location,
#  [(qty, days_to_expiry), ...], max_stock)
CATALOGUE = [
    ("PS-001", "Paracetamol", "Acetaminophen", "500mg", "Tablet", "Analgesic", OTC, "E", ROOM, 0.02, 0.05, SUP_GEN, 7, "No", 18000, 0, MAIN, [(4000, 25), (9000, 400), (6000, 640)], 25000),
    ("PS-002", "Ibuprofen", "Ibuprofen", "400mg", "Tablet", "Analgesic", OTC, "N", ROOM, 0.04, 0.10, SUP_GEN, 7, "No", 5400, 1, MAIN, [(1500, 50), (3000, 500)], None),
    ("PS-003", "Amoxicillin", "Amoxicillin", "500mg", "Capsule", "Anti-infective", RX, "V", ROOM, 0.09, 0.25, SUP_WHS, 7, "No", 9000, 0, MAIN, [(600, 300)], None),
    ("PS-004", "Ceftriaxone", "Ceftriaxone", "1g", "Vial", "Anti-infective", RX, "V", ROOM, 1.10, 2.90, SUP_WHS, 7, "No", 1350, 0, MAIN, [(420, 280), (300, 540)], None),
    ("PS-005", "Azithromycin", "Azithromycin", "250mg", "Tablet", "Anti-infective", RX, "E", ROOM, 0.30, 0.80, SUP_WHS, 7, "No", 900, 2, MAIN, [(200, -12), (1400, 380)], None),
    ("PS-006", "Lantus SoloStar", "Insulin Glargine", "100IU/mL", "Pen", "Endocrine", RX, "V", COLD, 18.50, 32.00, SUP_BIO, 10, "No", 540, 0, MAIN, [(35, 120)], None),
    ("PS-007", "NovoRapid FlexPen", "Insulin Aspart", "100IU/mL", "Pen", "Endocrine", RX, "V", COLD, 16.00, 28.00, SUP_BIO, 10, "No", 360, 1, MAIN, [(20, -5)], None),
    ("PS-008", "Metformin", "Metformin HCl", "500mg", "Tablet", "Endocrine", RX, "E", ROOM, 0.03, 0.09, SUP_GEN, 7, "No", 13500, 0, MAIN, [(6000, 45), (10000, 700)], None),
    ("PS-009", "Amlodipine", "Amlodipine besylate", "5mg", "Tablet", "Cardiovascular", RX, "E", ROOM, 0.03, 0.10, SUP_GEN, 7, "No", 6300, 0, MAIN, [(5000, 420)], None),
    ("PS-010", "Atorvastatin", "Atorvastatin", "20mg", "Tablet", "Cardiovascular", RX, "E", ROOM, 0.06, 0.18, SUP_GEN, 7, "No", 5400, 1, MAIN, [(3000, 80), (4500, 600)], None),
    ("PS-011", "Losartan", "Losartan potassium", "50mg", "Tablet", "Cardiovascular", RX, "E", ROOM, 0.05, 0.15, SUP_GEN, 7, "No", 2700, 0, MAIN, [(300, 365)], None),
    ("PS-012", "Ventolin Evohaler", "Salbutamol", "100mcg/dose", "Inhaler", "Respiratory", RX, "V", ROOM, 2.10, 4.50, SUP_WHS, 7, "No", 540, 0, MAIN, [(90, 28), (60, 400)], None),
    ("PS-013", "Adrenaline", "Epinephrine", "1mg/mL", "Ampoule", "Emergency", RX, "V", ROOM, 0.90, 2.50, SUP_WHS, 7, "No", 90, 2, ICU, [(12, 15)], None),
    ("PS-014", "Morphine Sulfate", "Morphine", "10mg/mL", "Ampoule", "Analgesic (Opioid)", CD, "V", ROOM, 1.80, 4.00, SUP_CD, 7, "No", 270, 0, ICU, [(40, -20), (150, 210)], None),
    ("PS-015", "Durogesic", "Fentanyl", "25mcg/h", "Transdermal Patch", "Analgesic (Opioid)", CD, "E", ROOM, 3.20, 7.50, SUP_CD, 7, "No", 45, 3, MAIN, [(60, 55)], None),
    ("PS-016", "OxyNorm", "Oxycodone", "5mg", "Capsule", "Analgesic (Opioid)", CD, "E", ROOM, 0.35, 0.90, SUP_CD, 7, "No", 1800, 0, MAIN, [(900, 330)], None),
    ("PS-017", "Tramadol", "Tramadol HCl", "50mg", "Capsule", "Analgesic (Opioid)", CD, "E", ROOM, 0.08, 0.25, SUP_CD, 7, "No", 180, 4, MAIN, [(1500, 500)], None),
    ("PS-018", "Valium", "Diazepam", "5mg", "Tablet", "CNS", CD, "E", ROOM, 0.04, 0.12, SUP_CD, 7, "No", 450, 1, MAIN, [(300, 40), (500, 610)], None),
    ("PS-019", "Midazolam", "Midazolam", "5mg/mL", "Ampoule", "CNS", CD, "V", ROOM, 1.20, 3.00, SUP_CD, 7, "No", 180, 6, ICU, [(0, 300)], None),
    ("PS-020", "Ketalar", "Ketamine", "50mg/mL", "Vial", "Anaesthetic", CD, "E", ROOM, 4.50, 9.00, SUP_CD, 7, "No", 36, 5, ICU, [(30, 150)], None),
    ("PS-021", "Naloxone", "Naloxone HCl", "0.4mg/mL", "Ampoule", "Emergency", RX, "V", ROOM, 2.80, 6.00, SUP_WHS, 7, "No", 27, 9, ICU, [(25, 75)], None),
    ("PS-022", "Omeprazole", "Omeprazole", "20mg", "Capsule", "Gastrointestinal", RX, "E", ROOM, 0.04, 0.12, SUP_GEN, 7, "No", 7200, 0, MAIN, [(2500, 20), (5000, 480)], None),
    ("PS-023", "Pantoprazole IV", "Pantoprazole", "40mg", "Vial", "Gastrointestinal", RX, "E", ROOM, 1.50, 3.80, SUP_WHS, 7, "No", 360, 2, MAIN, [(1200, 400)], None),
    ("PS-024", "Influenza Vaccine QIV", "Influenza vaccine (quadrivalent)", "0.5mL", "Prefilled Syringe", "Vaccine", RX, "E", COLD, 9.50, 18.00, SUP_VAC, 21, "Yes", 900, 0, MAIN, [(1800, 170)], None),
    ("PS-025", "Engerix-B", "Hepatitis B vaccine", "20mcg/mL", "Vial", "Vaccine", RX, "V", COLD, 7.00, 14.00, SUP_VAC, 21, "No", 270, 1, MAIN, [(15, 60)], None),
    ("PS-026", "Clexane", "Enoxaparin sodium", "40mg/0.4mL", "Prefilled Syringe", "Anticoagulant", RX, "V", ROOM, 3.90, 8.50, SUP_WHS, 7, "No", 1080, 0, MAIN, [(400, 260)], None),
    ("PS-027", "Heparin", "Heparin sodium", "5000IU/mL", "Vial", "Anticoagulant", RX, "V", ROOM, 2.20, 5.00, SUP_WHS, 7, "No", 450, 0, ICU, [(80, 88), (100, 520)], None),
    ("PS-028", "Warfarin", "Warfarin sodium", "5mg", "Tablet", "Anticoagulant", RX, "E", ROOM, 0.05, 0.15, SUP_GEN, 7, "No", 1350, 1, MAIN, [(900, 58)], None),
    ("PS-029", "Eltroxin", "Levothyroxine", "50mcg", "Tablet", "Endocrine", RX, "E", ROOM, 0.04, 0.12, SUP_GEN, 7, "No", 2700, 0, MAIN, [(2500, 240)], None),
    ("PS-030", "ORS Sachet", "Oral rehydration salts", "20.5g", "Sachet", "Gastrointestinal", OTC, "V", ROOM, 0.15, 0.40, SUP_GEN, 7, "No", 2250, 0, MAIN, [(700, 300)], None),
    ("PS-031", "Vitamin C", "Ascorbic acid", "500mg", "Tablet", "Supplement", OTC, "N", ROOM, 0.03, 0.10, SUP_GEN, 7, "No", 900, 3, MAIN, [(4000, 35)], None),
    ("PS-032", "Multivitamin", "Multivitamin", "Adult", "Tablet", "Supplement", OTC, "N", ROOM, 0.06, 0.20, SUP_GEN, 7, "No", 0, 140, MAIN, [(1200, 290)], None),
    ("PS-033", "Zinc Sulfate", "Zinc sulfate", "20mg", "Dispersible Tablet", "Supplement", OTC, "N", ROOM, 0.04, 0.12, SUP_GEN, 7, "No", 0, 180, MAIN, [(800, -40)], None),
    ("PS-034", "Cetirizine", "Cetirizine HCl", "10mg", "Tablet", "Antihistamine", OTC, "N", ROOM, 0.02, 0.08, SUP_GEN, 7, "Yes", 2700, 0, MAIN, [(2000, 150)], None),
    ("PS-035", "Loratadine", "Loratadine", "10mg", "Tablet", "Antihistamine", OTC, "N", ROOM, 0.03, 0.09, SUP_GEN, 7, "Yes", 1800, 12, MAIN, [(0, 365)], None),
    ("PS-036", "Dexamethasone", "Dexamethasone sodium phosphate", "4mg/mL", "Ampoule", "Emergency", RX, "V", ROOM, 0.60, 1.50, SUP_WHS, 7, "No", 540, 0, ICU, [(300, 85)], None),
    ("PS-037", "Hydrocortisone Cream", "Hydrocortisone", "1% 15g", "Cream", "Dermatology", OTC, "N", ROOM, 0.80, 2.00, SUP_GEN, 7, "No", 90, 2, MAIN, [(150, 44)], None),
    ("PS-038", "Humira", "Adalimumab", "40mg/0.4mL", "Pen", "Immunology (Biologic)", RX, "E", COLD, 480.00, 720.00, SUP_BIO, 14, "No", 18, 4, MAIN, [(40, 210)], 20),
    ("PS-039", "Herceptin", "Trastuzumab", "440mg", "Vial", "Oncology", RX, "V", COLD, 1250.00, 1800.00, SUP_BIO, 14, "No", 27, 3, MAIN, [(6, 95)], None),
    ("PS-040", "Eprex", "Epoetin alfa", "4000IU/0.4mL", "Prefilled Syringe", "Haematology", RX, "E", COLD, 38.00, 70.00, SUP_BIO, 14, "No", 90, 1, MAIN, [(12, 18), (8, -3)], None),
    ("PS-041", "Tamiflu", "Oseltamivir", "75mg", "Capsule", "Anti-infective", RX, "E", ROOM, 1.20, 3.00, SUP_WHS, 7, "Yes", 45, 8, MAIN, [(600, 400)], None),
    ("PS-042", "Sunscreen SPF50", "Sunscreen", "100mL", "Lotion", "Dermatology", OTC, "N", ROOM, 4.00, 9.50, SUP_GEN, 7, "Yes", 0, 100, MAIN, [(180, 380)], None),
    ("PS-043", "Nicotine Patch", "Nicotine", "21mg/24h", "Transdermal Patch", "Smoking Cessation", OTC, "N", ROOM, 1.10, 2.80, SUP_GEN, 7, "No", 90, 6, MAIN, [(300, 500)], None),
    ("PS-044", "Lasix", "Furosemide", "10mg/mL", "Ampoule", "Cardiovascular", RX, "V", ROOM, 0.35, 0.90, SUP_WHS, 7, "No", 720, 0, ICU, [(250, 400)], None),
    ("PS-045", "Glyceryl Trinitrate", "Nitroglycerin", "0.5mg", "Sublingual Tablet", "Cardiovascular", RX, "V", ROOM, 0.05, 0.20, SUP_GEN, 7, "No", 270, 1, MAIN, [(100, 12), (200, 330)], None),
    ("PS-046", "GlucaGen HypoKit", "Glucagon", "1mg", "Kit", "Emergency", RX, "V", ROOM, 22.00, 40.00, SUP_BIO, 10, "No", 18, 7, ICU, [(8, 65)], None),
    ("PS-047", "Cough Syrup DM", "Dextromethorphan", "15mg/5mL 100mL", "Syrup", "Respiratory", OTC, "N", ROOM, 1.50, 3.50, SUP_GEN, 7, "Yes", 450, 1, MAIN, [(900, 230)], None),
    ("PS-048", "Zofran", "Ondansetron", "4mg/2mL", "Ampoule", "Gastrointestinal", RX, "E", ROOM, 0.50, 1.40, SUP_WHS, 7, "No", 360, 0, MAIN, [(250, -8), (400, 190)], None),
]

_SHELF_LIFE_DAYS = {"Vaccine": 365, "Immunology (Biologic)": 540, "Oncology": 540, "Haematology": 540}


def generate_sample(reference: date | None = None) -> pd.DataFrame:
    ref = reference or date.today()
    rows = []
    for (drug_id, name, generic, strength, form, category, cls, ven, storage, cost, price,
         supplier, lead, seasonal, sold90, last_sale_ago, location, batches, max_stock) in CATALOGUE:
        total_qty = sum(q for q, _ in batches) or 1
        prefix = "".join(ch for ch in name.upper() if ch.isalpha())[:4]
        shelf_life = _SHELF_LIFE_DAYS.get(category, 730)
        for i, (qty, dte) in enumerate(batches):
            expiry = ref + timedelta(days=dte)
            mfg = expiry - timedelta(days=shelf_life)
            # Split 90-day sales across batches in proportion to their quantity;
            # a single batch carries the full SKU demand.
            share = qty / total_qty if len(batches) > 1 else 1.0
            rows.append({
                "Drug_ID": drug_id,
                "Drug_Name": name,
                "Generic_Name": generic,
                "Strength": strength,
                "Dosage_Form": form,
                "Therapeutic_Category": category,
                "Drug_Class": cls,
                "VEN_Class": ven,
                "Storage_Type": storage,
                "Batch_No": f"{prefix}-{mfg:%y%m}-{chr(65 + i)}",
                "Manufacture_Date": mfg.isoformat(),
                "Expiry_Date": expiry.isoformat(),
                "Qty_On_Hand": qty,
                "Unit_Cost": cost,
                "Unit_Price": price,
                "Units_Sold_90D": round(sold90 * share),
                "Last_Sale_Date": (ref - timedelta(days=last_sale_ago)).isoformat(),
                "Lead_Time_Days": lead,
                "Reorder_Level": "",
                "Max_Stock_Level": "" if max_stock is None else max_stock,
                "Supplier": supplier,
                "Location": location,
                "Seasonal": seasonal,
            })
    return pd.DataFrame(rows)


def sample_csv_bytes(reference: date | None = None) -> bytes:
    return generate_sample(reference).to_csv(index=False).encode("utf-8")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "sample_data" / "pharmastock_sample.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    generate_sample().to_csv(out, index=False)
    print(f"Wrote {out}")
