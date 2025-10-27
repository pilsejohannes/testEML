import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import streamlit as st

st.set_page_config(page_title="EML-prototype", layout="wide")
VERSION = "0.9"
st.title(f"EML-prototype (v{VERSION})")
st.caption(f"Kjører fil: {Path(__file__).resolve()}")

# ==========================================================
# Konfig
# ==========================================================
DB_FILENAME = "risiko_db.json"
SCENARIOS = ["Brann", "Skred", "Flom", "Annet"]

# Forventede kolonner (case-insensitiv matching)
EXPECTED_COLS = {
    "kumulenr": "Kumulenr",
    "risikonr": "Risikonr",
    "forsnr": "Forsnr",
    "adresse": "Adresse",
    "kundenavn": "Kundenavn",
    "tariffsum": "Tariffsum",
}

# ==========================================================
# Hjelpere
# ==========================================================

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


# --- Enkel maskinell EML-modell (rate) ---
BASE = 0.6
ALPHA = [1.00, 1.15, 1.35, 1.60]
BETA = [0.40, 0.30, 0.20, 0.10]
GAMMA = [0.05, 0.10, 0.15, 0.20]
EXPO = [1.30, 1.15, 1.00, 0.85]


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def calc_eml_rate_machine(rec: Dict[str, Any]) -> float:
    # Prototyp – inntil vi kobler faktorer; gi 30 % default hvis mangler
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
        return 0.30


def calc_eml_rate_effective(rec: Dict[str, Any]) -> float:
    if rec.get("eml_rate_manual_on"):
        return clamp01(float(rec.get("eml_rate_manual", 0.0)))
    return calc_eml_rate_machine(rec)


def calc_eml_effective(rec: Dict[str, Any]) -> int:
    try:
        si = float(rec.get("sum_forsikring", 0) or 0)
        return int(round(si * calc_eml_rate_effective(rec)))
    except Exception:
        return 0


# ==========================================================
# Session
# ==========================================================
if "db" not in st.session_state:
    st.session_state.db = load_db_from_file(DB_FILENAME) or {}
db: Dict[str, Any] = st.session_state.db

# ==========================================================
# Sidebar – Import/eksport
# ==========================================================
with st.sidebar:
    st.header("📁 Import / eksport")
    up_json = st.file_uploader("Last opp database (JSON)", type=["json"], key="json_up")
    if up_json is not None:
        try:
            loaded = json.load(up_json)
            if isinstance(loaded, dict):
                db.update(loaded)
                save_db_to_file(DB_FILENAME, db)
                st.success("Database importert.")
                st.experimental_rerun()
            else:
                st.error("Filen må være et JSON-objekt (dict)")
        except Exception as e:
            st.error(f"Ugyldig JSON: {e}")

    st.download_button(
        "⬇️ Last ned database (JSON)",
        data=json.dumps(db, ensure_ascii=False, indent=2),
        file_name="risiko_db.json",
        mime="application/json",
    )

# ==========================================================
# Faner: Database og Scenario
# ==========================================================
tab_db, tab_scen = st.tabs(["📚 Database", "📈 EML-scenario"])

# ----------------------------------------------------------
# 📚 DATABASE – Import, filtrering og utvalg pr. kumulesone
# ----------------------------------------------------------
with tab_db:
    st.subheader("1) Last opp Excel og importer alle rader")
    with st.expander("Forventede Excel-kolonner", expanded=False):
        st.write("\n".join([f"• {col}" for col in EXPECTED_COLS.values()]))

    up_xlsx = st.file_uploader("Last opp Excel (.xlsx)", type=["xlsx"], key="xlsx_all")
    if up_xlsx is not None:
        try:
            import pandas as pd, io
            df = pd.read_excel(io.BytesIO(up_xlsx.read()), engine="openpyxl")
            df.columns = [str(c).strip() for c in df.columns]
            lower = {c.lower(): c for c in df.columns}

            def col(k: str) -> Optional[str]:
                return lower.get(EXPECTED_COLS[k].lower())

            required = ["kumulenr", "risikonr"]
            missing = [EXPECTED_COLS[k] for k in required if col(k) is None]
            if missing:
                st.error("Mangler påkrevde kolonner: " + ", ".join(missing))
            else:
                imported = 0
                for _, row in df.iterrows():
                    kumule = str(row.get(col("kumulenr"), ""))
                    risiko = str(row.get(col("risikonr"), ""))
                    forsnr = str(row.get(col("forsnr"), ""))
                    adresse = str(row.get(col("adresse"), ""))
                    kunde = str(row.get(col("kundenavn"), ""))
                    navn = f"{kumule}-{risiko}-{adresse}".strip("-")

                    # Forsikringssum fra Tariffsum (kan utvides)
                    try:
                        si = float(row.get(col("tariffsum"), 0) or 0)
                    except Exception:
                        si = 0.0

                    rec = db.get(navn, {})
                    rec.update({
                        "kumulesone": kumule,
                        "risikonr": risiko,
                        "forsnr": forsnr,
                        "adresse": adresse,
                        "kundenavn": kunde,
                        "sum_forsikring": si,
                        # Overstyringsfelter (kan brukes i detalj-editor eller scenario)
                        "eml_rate_manual_on": rec.get("eml_rate_manual_on", False),
                        "eml_rate_manual": rec.get("eml_rate_manual", 0.0),
                        # Utvalg til scenario
                        "include": rec.get("include", False),
                        "scenario": rec.get("scenario", SCENARIOS[0]),  # default Brann
                        "updated": now_iso(),
                    })
                    db[navn] = rec
                    imported += 1
                save_db_to_file(DB_FILENAME, db)
                st.success(f"Importert {imported} rader til databasen.")
        except Exception as e:
            st.error(f"Kunne ikke lese Excel: {e}")

    st.markdown("---")
    st.subheader("2) Filtrer og velg per kumulesone")

    # Tekstfiltre
    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        filt_kunde = st.text_input("Filter: Kunde inneholder", value="")
    with colf2:
        filt_adresse = st.text_input("Filter: Adresse inneholder", value="")
    with colf3:
        filt_kumule = st.text_input("Filter: Kumulesone inneholder", value="")

    # Bygg DataFrame innenfor appen
    try:
        import pandas as pd
        rows = []
        for key, r in db.items():
            if not isinstance(r, dict):
                continue
            rows.append({
                "_key": key,
                "Kumulesone": r.get("kumulesone", ""),
                "Forsnr": r.get("forsnr", ""),
                "Risikonr": r.get("risikonr", ""),
                "Kunde": r.get("kundenavn", ""),
                "Adresse": r.get("adresse", ""),
                "Sum forsikring": float(r.get("sum_forsikring", 0) or 0),
                "Inkluder": bool(r.get("include", False)),
                "Scenario": r.get("scenario", SCENARIOS[0]),
                "EML (effektiv)": calc_eml_effective(r),
            })
        df = pd.DataFrame(rows)

        if df.empty:
            st.info("Ingen data i databasen. Last opp Excel over.")
        else:
            # Bruk filtrene
            m = pd.Series([True] * len(df))
            if filt_kunde:
                m &= df["Kunde"].astype(str).str.contains(filt_kunde, case=False, na=False)
            if filt_adresse:
                m &= df["Adresse"].astype(str).str.contains(filt_adresse, case=False, na=False)
            if filt_kumule:
                m &= df["Kumulesone"].astype(str).str.contains(filt_kumule, case=False, na=False)
            dfv = df[m].copy()

            # Group per kumulesone
            for kumule, grp in dfv.groupby("Kumulesone", dropna=False):
                total_si = int(grp["Sum forsikring"].sum())
                total_eml_inc = int(
                    df[(df["Kumulesone"] == kumule) & (df["Inkluder"])]["EML (effektiv)"].sum()
                )
                with st.expander(
                    f"Kumulesone {kumule} – {len(grp)} risikoer | Sum SI: {total_si:,.0f} | Sum EML (inkluderte): {total_eml_inc:,.0f}".replace(",", " "),
                    expanded=False,
                ):
                    # Scenario-valg for massevalg i denne kumulen
                    sc_col1, sc_col2, sc_col3 = st.columns([2, 1, 1])
                    with sc_col1:
                        scen_label = st.selectbox(
                            f"Scenario for kumule {kumule}", options=SCENARIOS, index=0, key=f"scen_{kumule}"
                        )
                    with sc_col2:
                        if st.button("Velg ALLE i kumule", key=f"selall_{kumule}"):
                            for idx, row in grp.iterrows():
                                k = row["_key"]
                                db[k]["include"] = True
                                db[k]["scenario"] = scen_label
                            save_db_to_file(DB_FILENAME, db)
                            st.experimental_rerun()
                    with sc_col3:
                        if st.button("Fjern ALLE i kumule", key=f"clrall_{kumule}"):
                            for idx, row in grp.iterrows():
                                k = row["_key"]
                                db[k]["include"] = False
                            save_db_to_file(DB_FILENAME, db)
                            st.experimental_rerun()

                    # Radvis avhuking med mer info
                    changed_include: Dict[str, bool] = {}
                    changed_scenario: Dict[str, str] = {}
                    st.write("**Risikoer i kumulesonen:**")
                    for idx, row in grp.sort_values(["Risikonr"]).iterrows():
                        k = row["_key"]
                        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([1.2, 1.2, 1.2, 3, 3, 1.6, 1, 1.6])
                        c1.write(str(row["Forsnr"]))
                        c2.write(str(row["Risikonr"]))
                        c3.write(str(row["Kunde"]))
                        c4.write(str(row["Adresse"]))
                        c5.write(f"{int(row['Sum forsikring']):,}".replace(",", " "))
                        c6.write(f"EML≈ {int(row['EML (effektiv)']):,}".replace(",", " "))
                        changed_include[k] = c7.checkbox("Inkl.", value=bool(row["Inkluder"]), key=f"inc_{k}")
                        changed_scenario[k] = c8.selectbox("Scen.", options=SCENARIOS, index=SCENARIOS.index(row["Scenario"]) if row["Scenario"] in SCENARIOS else 0, key=f"sce_{k}")

                    if st.button("💾 Lagre utvalg i denne kumulesonen", key=f"save_{kumule}"):
                        for k, val in changed_include.items():
                            if k in db:
                                db[k]["include"] = bool(val)
                                db[k]["scenario"] = changed_scenario.get(k, db[k].get("scenario", SCENARIOS[0])) if val else db[k].get("scenario", SCENARIOS[0])
                                db[k]["updated"] = now_iso()
                        save_db_to_file(DB_FILENAME, db)
                        st.success("Valg lagret for kumulesonen.")
    except Exception as e:
        st.error(f"Visningsfeil: {e}")

# ----------------------------------------------------------
# 📈 EML-SCENARIO – Beregn per EN kumulesone + MANUELL overstyring
# ----------------------------------------------------------
with tab_scen:
    st.subheader("Velg kumulesone og scenario for beregning og overstyring")

    # Finn tilgjengelige kumulesoner
    kumuler = sorted({r.get("kumulesone", "") for r in db.values() if isinstance(r, dict)})
    sel_kumule = st.selectbox("Kumulesone", options=[""] + kumuler)
    scen = st.selectbox("Scenario", options=SCENARIOS, index=0)

    if not sel_kumule:
        st.info("Velg en kumulesone for å beregne EML.")
    else:
        try:
            import pandas as pd
            rows = []
            # For lagring av endringer
            changed_manual_on: Dict[str, bool] = {}
            changed_manual_rate: Dict[str, float] = {}

            for k, r in db.items():
                if not isinstance(r, dict):
                    continue
                if str(r.get("kumulesone", "")) != str(sel_kumule):
                    continue
                if not bool(r.get("include", False)):
                    continue
                if str(r.get("scenario", SCENARIOS[0])) != scen:
                    continue

                # Nåværende verdier
                si = float(r.get("sum_forsikring", 0) or 0)
                rate_machine = calc_eml_rate_machine(r)
                manual_on_default = bool(r.get("eml_rate_manual_on", False))
                manual_rate_default = float(r.get("eml_rate_manual", 0.0)) * 100.0

                c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([1.2, 1.2, 2.2, 3, 1.6, 1.6, 1.2, 1.8])
                c1.write(str(r.get("forsnr", "")))
                c2.write(str(r.get("risikonr", "")))
                c3.write(str(r.get("kundenavn", "")))
                c4.write(str(r.get("adresse", "")))
                c5.write(f"SI {int(si):,}".replace(",", " "))
                c6.write(f"Mask.sats {rate_machine*100:.1f}%")
                changed_manual_on[k] = c7.checkbox("Overstyr", value=manual_on_default, key=f"ovr_{k}")
                changed_manual_rate[k] = c8.number_input(
                    "Manuell %", min_value=0.0, max_value=100.0, step=0.5, value=manual_rate_default, key=f"mrate_{k}"
                )

                # Beregn EML live basert på inputs
                eff_rate = (changed_manual_rate[k] / 100.0) if changed_manual_on[k] else rate_machine
                eml_val = int(round(si * eff_rate))
                st.markdown(f"**EML (effektiv):** {eml_val:,.0f} NOK".replace(",", " "))
                st.markdown("---")

            if st.button("💾 Lagre manuelle overstyringer for denne kumulesonen"):
                for k, on_val in changed_manual_on.items():
                    if k in db:
                        db[k]["eml_rate_manual_on"] = bool(on_val)
                        db[k]["eml_rate_manual"] = float(changed_manual_rate.get(k, 0.0)) / 100.0
                        db[k]["updated"] = now_iso()
                save_db_to_file(DB_FILENAME, db)
                st.success("Overstyringer lagret.")

            # Etter visning av alle: totaler
            # Bygg DF på nytt for totalberegning
            rows_tot = []
            for k, r in db.items():
                if not isinstance(r, dict):
                    continue
                if str(r.get("kumulesone", "")) != str(sel_kumule):
                    continue
                if not bool(r.get("include", False)):
                    continue
                if str(r.get("scenario", SCENARIOS[0])) != scen:
                    continue
                si = float(r.get("sum_forsikring", 0) or 0)
                rate = calc_eml_rate_effective(r)
                rows_tot.append({"SI": si, "EML": int(round(si * rate))})
            import pandas as pd
            dft = pd.DataFrame(rows_tot)
            if not dft.empty:
                total_si = int(dft["SI"].sum())
                total_eml = int(dft["EML"].sum())
                st.metric("Sum SI i kumulesone", f"{total_si:,.0f}".replace(",", " "))
                st.metric("Sum EML i kumulesone", f"{total_eml:,.0f}".replace(",", " "))
        except Exception as e:
            st.error(f"Klarte ikke å beregne/oppdatere scenario: {e}")
