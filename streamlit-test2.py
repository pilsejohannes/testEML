import json
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import streamlit as st

# ==========================================================
# EML-prototype – v0.6 (database→scenario, ryddet)
# ----------------------------------------------------------
# - Fjerner alle referanser til start_mode (nå to faner)
# - Excel importerer ALLE rader → lagres i databasen
# - Faner: 📚 Database (filtrering/utvalg) og 📈 Scenario (beregning)
# - Maskinell og manuell EML-sats; kumulesummer per scenario
# ==========================================================

st.set_page_config(page_title="EML-prototype", layout="wide")
VERSION = "0.6"
st.title(f"EML-prototype (v{VERSION})")
st.caption(f"Kjører fil: {Path(__file__).resolve()}")

# ------------------------------
# Konfig
# ------------------------------
DB_FILENAME = "risiko_db.json"
DEFAULT_TERSKEL = 800_000_000  # 800 MNOK

EXPECTED_COLS = {
    "kumulenr": "Kumulenr",
    "gnr": "GNR",
    "bnr": "BNR",
    "adresse": "Adresse",
    "kumulesum": "Kumulesum",
    "eml_sum": "EML sum",
    "eml_sats_type": "EML sats type",
    "eml_sats": "EML sats",
    "kundenavn": "Kundenavn",
    "forsnr": "Forsnr",
    "risikonr": "Risikonr",
    "fstednr": "Fsted.nr",
    "bygnnr": "Bygn.nr",
    "grunnrisiko": "Grunnrisiko",
    "tariffsum": "Tariffsum",
    "bransjetekst": "Bransjetekst",
    "virksomhet": "Virksomhet",
    "intorg3navn": "Intorg 3 navn (samh)",
    "intorg8nr": "Intorg 8 nr",
    "intorg8navn": "Intorg 8 navn",
    "brannkasse": "Brannkasse",
    "kommune_navn": "kommune navn",
}

# ------------------------------
# Hjelpefunksjoner
# ------------------------------
def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def load_db_from_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_db_to_file(path: str, db: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True, None
    except Exception as e:
        return False, str(e)

# Enkel maskinell EML-modell
def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

BASE = 0.6
ALPHA = [1.00, 1.15, 1.35, 1.60]
BETA = [0.40, 0.30, 0.20, 0.10]
GAMMA = [0.05, 0.10, 0.15, 0.20]
EXPO = [1.30, 1.15, 1.00, 0.85]

def calc_eml_rate_machine(rec: Dict[str, Any]) -> float:
    try:
        b = int(rec.get("brannrisiko", 0))
        lim = int(rec.get("begrensende_faktorer", 0))
        prot = int(rec.get("deteksjon_beskyttelse", 0))
        expo = int(rec.get("eksponering_nabo", 0))
        rate = BASE * ALPHA[b] * EXPO[expo]
        rate *= (1 - BETA[prot])
        rate *= (1 - GAMMA[lim])
        return clamp01(rate)
    except Exception:
        return 0.0

def calc_eml_rate_effective(rec: Dict[str, Any]) -> float:
    if rec.get("eml_rate_manual_on"):
        return clamp01(float(rec.get("eml_rate_manual", 0.0)))
    return calc_eml_rate_machine(rec)

def calc_eml_effective(rec: Dict[str, Any]) -> int:
    try:
        si = float(rec.get("sum_forsikring", 0))
        rate = calc_eml_rate_effective(rec)
        return int(round(si * rate))
    except Exception:
        return 0

def eml_source_label(rec: Dict[str, Any]) -> str:
    return "Manuell sats" if rec.get("eml_rate_manual_on") else "Maskinell sats"

# ------------------------------
# Init session
# ------------------------------
if "db" not in st.session_state:
    st.session_state.db = load_db_from_file(DB_FILENAME) or {}
db = st.session_state.db

# ------------------------------
# Faner: Database og Scenario
# ------------------------------
tab_db, tab_scen = st.tabs(["📚 Database", "📈 EML-scenario"])

# ==========================================================
# 📚 DATABASE
# ==========================================================
with tab_db:
    st.header("Database – import og filtrering")
    up_xlsx = st.file_uploader("Last opp Excel (.xlsx)", type=["xlsx"])
    if up_xlsx is not None:
        try:
            import pandas as pd, io
            df = pd.read_excel(io.BytesIO(up_xlsx.read()), engine="openpyxl")
            df.columns = [str(c).strip() for c in df.columns]
            lower_to_orig = {c.lower(): c for c in df.columns}
            def col(key): 
                return lower_to_orig.get(EXPECTED_COLS[key].lower())
            for _, row in df.iterrows():
                kumule = str(row.get(col("kumulenr"), ""))
                risiko = str(row.get(col("risikonr"), ""))
                adresse = str(row.get(col("adresse"), ""))
                navn = f"{kumule}-{risiko}-{adresse}".strip("-")
                rec = {
                    "kumulesone": kumule,
                    "risikonr": risiko,
                    "adresse": adresse,
                    "kundenavn": str(row.get(col("kundenavn"), "")),
                    "sum_forsikring": float(row.get(col("tariffsum"), 0) or 0),
                    "eml_rate_manual_on": False,
                    "eml_rate_manual": 0.0,
                    "include": False,
                    "scenario": "Standard",
                    "updated": now_iso(),
                }
                db[navn] = rec
            save_db_to_file(DB_FILENAME, db)
            st.success(f"Importert {len(df)} rader til databasen.")
        except Exception as e:
            st.error(f"Kunne ikke lese Excel: {e}")

    # Filter og visning
    import pandas as pd
    if db:
        df = pd.DataFrame([
            {"Objekt": k, "Kumulesone": v.get("kumulesone"), "Risikonr": v.get("risikonr"),
             "Kunde": v.get("kundenavn"), "Adresse": v.get("adresse"),
             "Sum forsikring": v.get("sum_forsikring"), "Inkluder": v.get("include")}
            for k, v in db.items()
        ])
        st.dataframe(df.sort_values(["Kumulesone", "Risikonr"]), use_container_width=True)
    else:
        st.info("Ingen data i databasen.")

# ==========================================================
# 📈 SCENARIO
# ==========================================================
with tab_scen:
    st.header("EML-scenario – beregning")
    chosen_scenario = st.text_input("Scenario-navn", value="Standard")
    import pandas as pd
    rows = []
    for name, r in db.items():
        if r.get("include") and r.get("scenario") == chosen_scenario:
            rows.append({
                "Kumulesone": r.get("kumulesone"),
                "Risikonr": r.get("risikonr"),
                "Kunde": r.get("kundenavn"),
                "Sum forsikring": r.get("sum_forsikring"),
                "Sats (%)": round(calc_eml_rate_effective(r)*100, 2),
                "EML (effektiv)": calc_eml_effective(r),
            })
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        grp = df.groupby("Kumulesone")["EML (effektiv)"].sum().reset_index()
        st.subheader("Kumule-summer")
        st.dataframe(grp, use_container_width=True)
        st.metric("Total EML i scenario", f"{df['EML (effektiv)'].sum():,.0f}".replace(",", " "))
    else:
        st.info("Ingen risikoer markert for scenarioet.")
