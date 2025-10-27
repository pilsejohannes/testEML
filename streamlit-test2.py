import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import streamlit as st

st.set_page_config(page_title="EML-prototype", layout="wide")
VERSION = "0.7"
st.title(f"EML-prototype (v{VERSION})")
st.caption(f"Kjører fil: {Path(__file__).resolve()}")

# ------------------------------
# Konfig
# ------------------------------
DB_FILENAME = "risiko_db.json"
EXPECTED_COLS = {
    "kumulenr": "Kumulenr",
    "risikonr": "Risikonr",
    "adresse": "Adresse",
    "kundenavn": "Kundenavn",
    "tariffsum": "Tariffsum",
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

def calc_eml_rate_machine(rec):
    return 0.3  # enkel placeholder-rate

def calc_eml_effective(rec):
    try:
        si = float(rec.get("sum_forsikring", 0))
        return round(si * calc_eml_rate_machine(rec))
    except Exception:
        return 0

# ------------------------------
# Session init
# ------------------------------
if "db" not in st.session_state:
    st.session_state.db = load_db_from_file(DB_FILENAME) or {}
db = st.session_state.db

# ------------------------------
# Faner
# ------------------------------
tab_db, tab_scen = st.tabs(["📚 Database", "📈 EML-scenario"])

# ==========================================================
# 📚 DATABASE
# ==========================================================
with tab_db:
    st.header("Database – import og filtrering")

    # --- Import av Excel ---
    up_xlsx = st.file_uploader("Last opp Excel (.xlsx)", type=["xlsx"])
    if up_xlsx is not None:
        import pandas as pd, io
        try:
            df = pd.read_excel(io.BytesIO(up_xlsx.read()), engine="openpyxl")
            df.columns = [str(c).strip() for c in df.columns]
            lower = {c.lower(): c for c in df.columns}

            def col(k): return lower.get(EXPECTED_COLS[k].lower())

            imported = 0
            for _, row in df.iterrows():
                navn = f"{row.get(col('kumulenr'))}-{row.get(col('risikonr'))}-{row.get(col('adresse'))}"
                rec = db.get(navn, {})
                rec.update({
                    "kumulesone": str(row.get(col("kumulenr"), "")),
                    "risikonr": str(row.get(col("risikonr"), "")),
                    "adresse": str(row.get(col("adresse"), "")),
                    "kundenavn": str(row.get(col("kundenavn"), "")),
                    "sum_forsikring": float(row.get(col("tariffsum"), 0) or 0),
                    "include": False,
                    "scenario": "Standard",
                    "updated": now_iso(),
                })
                db[navn] = rec
                imported += 1
            save_db_to_file(DB_FILENAME, db)
            st.success(f"Importert {imported} rader til databasen.")
        except Exception as e:
            st.error(f"Feil ved lesing av Excel: {e}")

    # --- Filtrering ---
    st.subheader("Filtrering")
    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        f_kunde = st.text_input("Filter på kunde")
    with colf2:
        f_adresse = st.text_input("Filter på adresse")
    with colf3:
        f_kumule = st.text_input("Filter på kumulesone")

    # --- Tabell med avhuking ---
    import pandas as pd
    if db:
        data = []
        for name, r in db.items():
            data.append({
                "Objekt": name,
                "Kumulesone": r.get("kumulesone", ""),
                "Risikonr": r.get("risikonr", ""),
                "Kunde": r.get("kundenavn", ""),
                "Adresse": r.get("adresse", ""),
                "Sum forsikring": r.get("sum_forsikring", 0),
                "Inkluder": r.get("include", False),
            })
        df = pd.DataFrame(data)

        # Filtrer
        if f_kunde:
            df = df[df["Kunde"].str.contains(f_kunde, case=False, na=False)]
        if f_adresse:
            df = df[df["Adresse"].str.contains(f_adresse, case=False, na=False)]
        if f_kumule:
            df = df[df["Kumulesone"].astype(str).str.contains(f_kumule, case=False, na=False)]

        st.subheader("Marker risikoer som skal inngå i EML-scenario")
        changed = {}
        for i, row in df.iterrows():
            key = row["Objekt"]
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 4, 1])
            with col1:
                st.write(row["Kumulesone"])
            with col2:
                st.write(row["Risikonr"])
            with col3:
                st.write(row["Kunde"])
            with col4:
                st.write(row["Adresse"])
            with col5:
                changed[key] = st.checkbox("", value=row["Inkluder"], key=f"inc_{key}")

        if st.button("💾 Lagre valg"):
            for key, val in changed.items():
                if key in db:
                    db[key]["include"] = val
                    db[key]["updated"] = now_iso()
            save_db_to_file(DB_FILENAME, db)
            st.success("Valg lagret.")
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
                "Adresse": r.get("adresse"),
                "Sum forsikring": r.get("sum_forsikring"),
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
