import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import date

import streamlit as st

st.set_page_config(page_title="EML-prototype", layout="wide")
import streamlit as st, sys
from pathlib import Path
st.caption(f"DEBUG: fil={Path(__file__).name}  |  Streamlit={st.__version__}")
import traceback
import streamlit as st, traceback
st.set_option("client.showErrorDetails", True)

#def force_rerun():
#    # Streamlit >= 1.36
#    if hasattr(st, "rerun"):
#        st.rerun()
#        return
#    # Eldre Streamlit
#    if hasattr(st, "experimental_rerun"):
#        st.experimental_rerun()
#        return
#    # Nød-løsning: trigge endring i state for å utløse rerun
#    st.session_state["_force_rerun_ts"] = datetime.utcnow().isoformat()

VERSION = "0.1"
st.title(f"EML-prototype Slider (v{VERSION})")
st.caption(f"Kjører fil: {Path(__file__).resolve()}")

# ==========================================================
# Konfig
# ==========================================================
DB_FILENAME = "testSlider_risiko_db.json"
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
DB_FILENAME = "testSlider_risiko_db.json"

def load_db_from_file(path):
    import json
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        st.warning(f"Klarte ikke å lese {path}, oppretter ny database ({e})")
    return {"risikoer": [], "kumuler": []}

def save_db_to_file(path, data):
    import json
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Klarte ikke å lagre til {path}: {e}")

# 👉 Last databasen her:
db = load_db_from_file(DB_FILENAME)
import hashlib
from typing import Dict

def md5_bytes(b: bytes) -> str:
    h = hashlib.md5()
    h.update(b)
    return h.hexdigest()
def force_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    #elif hasattr(st, "experimental_rerun"):
    #    st.experimental_rerun()
    else:
        st.session_state["_force_rerun_ts"] = now_iso()

def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def load_db_from_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        st.error(...); st.stop() #return {}


def save_db_to_file(path: str, db: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True, None
    except Exception as e:
        st.error(f"Feil: {e}")
        st.exception(e)  # viser traceback i appen
        st.stop()

st.write("DEBUG: type(db)=", type(db).__name__) #sjekk at db faktisk inneholder noe


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
                st.rerun()
            else:
                st.error("Filen må være et JSON-objekt (dict)")
        except Exception as e:
            st.error(f"Ugyldig JSON: {e}")

    st.download_button(
        "⬇️ Last ned database (JSON)",
        data=json.dumps(db, ensure_ascii=False, indent=2),
        file_name="testSlider_risiko_db.json",
        mime="application/json",
    )

# ==========================================================
# Faner: Database og Scenario
# ==========================================================
# ---- Last eller opprett database ----



tab_db, tab_scen = st.tabs(["📚 Database", "📈 EML-scenario"])

# ----------------------------------------------------------
# 📚 DATABASE – Import, filtrering og utvalg pr. kumulesone
# ----------------------------------------------------------
with tab_db:
    st.subheader("1) Last opp Excel og importer alle rader")

with st.expander("Forventede Excel-kolonner", expanded=False):
    st.write("\n".join([f"• {col}" for col in EXPECTED_COLS.values()]))

up_xlsx = st.file_uploader("Last opp Excel (.xlsx)", type=["xlsx"], key="xlsx_all")

# Init import-state
if "last_import_md5" not in st.session_state:
    st.session_state.last_import_md5 = None

# Vis knapp kun hvis fil er valgt
can_import = up_xlsx is not None
do_import = st.button("📥 Importer fra valgt fil", disabled=not can_import)

if do_import and up_xlsx is not None:
    try:
        import pandas as pd, io
        raw = up_xlsx.read()
        file_hash = md5_bytes(raw)

        # Hindre dobbelt-import av samme fil
        if file_hash == st.session_state.last_import_md5:
            st.info("Samme fil er allerede importert. Ingen endringer.")
        else:
            df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
            st.caption(f"📄 Kolonner funnet: {list(df.columns)}")

            df.columns = [str(c).strip() for c in df.columns]
            lower = {c.lower(): c for c in df.columns}
            def col(k: str) -> Optional[str]: return lower.get(EXPECTED_COLS[k].lower())

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
                        "eml_rate_manual_on": rec.get("eml_rate_manual_on", False),
                        "eml_rate_manual": rec.get("eml_rate_manual", 0.0),
                        "include": rec.get("include", False),
                        "scenario": rec.get("scenario", SCENARIOS[0]),
                        "updated": now_iso(),
                    })
                    db[navn] = rec
                    imported += 1

                ok, err = save_db_to_file(DB_FILENAME, db)
                if ok:
                    st.success(f"Importert {imported} rader til databasen.")
                    st.session_state.last_import_md5 = file_hash
                    # Ikke rerun automatisk; la brukeren se status og tabell under.
                else:
                    st.error(f"Kunne ikke lagre DB: {err}")
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
# Sikre at filtre finnes (default tomme)
filt_kunde = st.session_state.get("filt_kunde", "")
filt_adresse = st.session_state.get("filt_adresse", "")
filt_kumule = st.session_state.get("filt_kumule", "")

    # Bygg DataFrame innenfor appen
# Bygg DataFrame innenfor appen (robust)
try:
    import pandas as pd

    # Liten statusboks så vi ser at DB faktisk er fylt
    st.caption(f"🔎 Objekter i database: {len(db)}")

    rows = []
    for key, r in db.items():
        if not isinstance(r, dict):
            continue
        rows.append({
            "_key": key,
            "Kumulesone": str(r.get("kumulesone", "")),
            "Forsnr": str(r.get("forsnr", "")),
            "Risikonr": str(r.get("risikonr", "")),
            "Kunde": str(r.get("kundenavn", "")),
            "Adresse": str(r.get("adresse", "")),
            "Sum forsikring": float(r.get("sum_forsikring", 0) or 0),
            "EML (effektiv)": calc_eml_effective(r),
            "Kilde": ("🟩 Manuell" if bool(r.get("eml_rate_manual_on", False)) else "⚙️ Maskinell"),
            "Inkluder": bool(r.get("include", False)),
            "Scenario": r.get("scenario", SCENARIOS[0]),
        })

    df = pd.DataFrame(rows)

    if df.empty:
        st.info("Ingen data i databasen. Last opp Excel over.")
    else:
        # Filtrene
        m = pd.Series([True] * len(df))
        if filt_kunde:
            m &= df["Kunde"].astype(str).str.contains(filt_kunde, case=False, na=False)
        if filt_adresse:
            m &= df["Adresse"].astype(str).str.contains(filt_adresse, case=False, na=False)
        if filt_kumule:
            m &= df["Kumulesone"].astype(str).str.contains(filt_kumule, case=False, na=False)
        dfv = df[m].copy()

        if dfv.empty:
            st.warning("Filtrene dine skjuler alle rader. Tøm filtrene for å se alt.")
        else:
            # Gruppér og vis per kumulesone
            for kumule, grp in dfv.groupby("Kumulesone", dropna=False):
                total_si = int(grp["Sum forsikring"].sum())
                total_eml_inc = int(df[(df["Kumulesone"] == kumule) & (df["Inkluder"])]["EML (effektiv)"].sum())
                with st.expander(
                    f"Kumulesone {kumule} – {len(grp)} risikoer | "
                    f"Sum SI: {total_si:,.0f} | Sum EML (inkluderte): {total_eml_inc:,.0f}".replace(",", " "),
                    expanded=False,
                ):
                    sc_col1, sc_col2, sc_col3 = st.columns([2, 1, 1])
                    with sc_col1:
                        scen_label = st.selectbox(
                            f"Scenario for kumule {kumule}", options=SCENARIOS, index=0, key=f"scen_{kumule}"
                        )
                    with sc_col2:
                        if st.button("Velg ALLE i kumule", key=f"selall_{kumule}"):
                            for _, row in grp.iterrows():
                                k = row["_key"]
                                db[k]["include"] = True
                                db[k]["scenario"] = scen_label
                            save_db_to_file(DB_FILENAME, db)
                            st.rerun()
                    with sc_col3:
                        if st.button("Fjern ALLE i kumule", key=f"clrall_{kumule}"):
                            for _, row in grp.iterrows():
                                k = row["_key"]
                                db[k]["include"] = False
                            save_db_to_file(DB_FILENAME, db)
                            st.rerun()

                    # Radvis avhuking med mer info
                    changed_include: Dict[str, bool] = {}
                    changed_scenario: Dict[str, str] = {}
                    st.write("**Risikoer i kumulesonen:**")
                    for _, row in grp.sort_values(["Risikonr"]).iterrows():
                        k = row["_key"]
                        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([1.2, 1.2, 2.2, 3, 1.6, 1.8, 1, 1.6])
                        c1.write(str(row["Forsnr"]))
                        c2.write(str(row["Risikonr"]))
                        c3.write(str(row["Kunde"]))
                        c4.write(str(row["Adresse"]))
                        c5.write(f"{int(row['Sum forsikring']):,}".replace(",", " "))

                        src_is_manual = bool(db.get(k, {}).get("eml_rate_manual_on", False))
                        c6.write(
                            (
                                f"EML≈ {int(row['EML (effektiv)']):,}\n"
                                f"{'🟩 Manuell' if src_is_manual else '⚙️ Maskinell'}"
                            ).replace(",", " ")
                        )

                        changed_include[k] = c7.checkbox("Inkl.", value=bool(row["Inkluder"]), key=f"inc_{k}")
                        current_scen = row["Scenario"] if row["Scenario"] in SCENARIOS else SCENARIOS[0]
                        changed_scenario[k] = c8.selectbox(
                            "Scen.", options=SCENARIOS, index=SCENARIOS.index(current_scen), key=f"sce_{k}"
                        )

                    if st.button("💾 Lagre utvalg i denne kumulesonen", key=f"save_{kumule}"):
                        for k, val in changed_include.items():
                            if k in db:
                                db[k]["include"] = bool(val)
                                if val:
                                    db[k]["scenario"] = changed_scenario.get(
                                        k, db[k].get("scenario", SCENARIOS[0])
                                    )
                                db[k]["updated"] = now_iso()
                        save_db_to_file(DB_FILENAME, db)
                        st.success("Valg lagret for kumulesonen.")

except Exception as e:
    st.error(f"Visningsfeil: {e}")


# ----------------------------------------------------------
# 📈 EML-SCENARIO – Beregn per EN kumulesone + MANUELL overstyring
# ----------------------------------------------------------
#
#from datetime import date
#import pandas as pd
#import streamlit as st


# Sørg for synlige feildetaljer
st.set_option("client.showErrorDetails", True)

# --- KONFIG for scenario "Brann" ---
BRANN_RISIKO_CHOICES = ["Høy", "Middels", "Lav"]
BRANN_SPREDNING_CHOICES = ["Stor", "Middels", "Liten"]
BRANN_slukke_CHOICES = ["Lang", "Middels", "Kort"]

def _scenario_key(scen: str, kumule: str) -> str:
    return f"{scen}::{kumule}".strip()

with tab_scen:
    st.subheader("EML-scenario – Brann")

    # 1) Finn kumuler og definer kumule_liste (løser NameError)
    kumuler = sorted({str(r.get("kumulesone", "")).strip()
                      for r in db.values() if isinstance(r, dict)} - {""})
    kumule_liste = [""] + kumuler
    sel_kumule = st.selectbox("Kumulesone", options=kumule_liste, index=0)

    scen = st.selectbox("Scenario", options=["Brann"], index=0)

    if not sel_kumule:
        st.info("Velg en kumulesone for å vurdere scenarioet.")
        st.stop()

    # 2) Init meta-nøkkel (scenariobeskrivelse lagres separat)
    meta_key = _scenario_key(scen, sel_kumule)
    if "_scenario_meta" not in db or not isinstance(db.get("_scenario_meta"), dict):
        db["_scenario_meta"] = {}

    existing_desc = db["_scenario_meta"].get(meta_key, {}).get("beskrivelse", "")

    # 3) Filtrer risikoer: kun 'include=True' i valgt kumulesone
    risikoliste = []
    for k, r in db.items():
        if not isinstance(r, dict):
            continue
        if str(r.get("kumulesone", "")) != sel_kumule:
            continue
        if not bool(r.get("include", False)):
            continue
        risikoliste.append((k, r))

    if not risikoliste:
        st.warning("Ingen risikoer med `include=True` i denne kumulesonen.")
        st.stop()

    # 4) Skjema (FIKSER 'Missing Submit Button')
    with st.form("brann_scenario_form"):
        # EML-metadata (nye felt i databasen)
        eml_beregnet_dato = st.text_input("EML beregnet dato (ISO-8601)", value=date.today().isoformat())
        eml_beregnet_av = st.text_input("EML beregnet av", value=st.session_state.get("bruker", ""))
        st.markdown("**Scenariobeskrivelse (lagres, vises ikke på forsiden)**")
        scenariobeskrivelse = st.text_area(
            "Beskrivelse",
            value=existing_desc,
            placeholder="Forutsetninger, særskilte forhold, tiltak, osv.",
            height=120,
            label_visibility="collapsed",
            key=f"desc_{meta_key}"
        )

        changed = {}

        st.write(f"**{len(risikoliste)} risiko(er) i {sel_kumule}**")
        for k, r in risikoliste:
            st.markdown("---")
            colA, colB, colC, colD, colE = st.columns([1.2, 1.2, 2.2, 2.2, 2.2])
            colA.write(f"**{r.get('forsnr','')}**")
            colB.write(f"{r.get('risikonr','')}")
            colC.write(r.get("kundenavn","") or "–")
            colD.write(r.get("adresse","") or "–")
            si = float(r.get("sum_forsikring", 0) or 0)
            colE.write(f"SI: {int(si):,} NOK".replace(",", " "))

            # Defaults fra tidligere valg (hvis finnes)
            brann_cfg = r.get("brann", {}) if isinstance(r.get("brann"), dict) else {}
            risiko_default = brann_cfg.get("risiko_for_brann", "Middels")
            spredning_default = brann_cfg.get("spredning_av_brann", "Middels")
            slukke_default = brann_cfg.get("tid_for_slukkeinnsats", "Middels")

            c1, c2, c3 = st.columns(3)
            risiko_val = c1.selectbox(
                "Risiko for brann", BRANN_RISIKO_CHOICES,
                index=BRANN_RISIKO_CHOICES.index(risiko_default) if risiko_default in BRANN_RISIKO_CHOICES else 1,
                key=f"brann_risiko_{k}"
            )
            spredning_val = c2.selectbox(
                "Spredning av brann", BRANN_SPREDNING_CHOICES,
                index=BRANN_SPREDNING_CHOICES.index(spredning_default) if spredning_default in BRANN_SPREDNING_CHOICES else 1,
                key=f"brann_spredning_{k}"
            )
            slukke_val = c3.selectbox(
                "Tid før slukkeinnsats", BRANN_slukke_CHOICES,
                index=BRANN_slukke_CHOICES.index(slukke_default) if slukke_default in BRANN_slukke_CHOICES else 1,
                key=f"brann_slukke_{k}"
            )

            changed[k] = {
                "brann": {
                    "risiko_for_brann": risiko_val,
                    "spredning_av_brann": spredning_val,
                    "tid_for_slukkeinnsats": slukke_val,
                    "updated": now_iso(),
                }
            }
             


        submitted = st.form_submit_button("💾 Lagre scenario (Brann) for kumulesonen")
               
    
    # 5) Persister ved submit
    if submitted:
        # Lagre meta (beskrivelse) separat
        db["_scenario_meta"][meta_key] = {
            "scenario": scen,
            "kumulesone": sel_kumule,
            "beskrivelse": scenariobeskrivelse,
            "updated": now_iso(),
            "updated_by": st.session_state.get("bruker", ""),
        }
        # Lagre per-risiko valg
        for k, patch in changed.items():
            if k in db and isinstance(db[k], dict):
                existing = db[k].get("brann", {})
                if not isinstance(existing, dict):
                    existing = {}
                existing.update(patch["brann"])
                db[k]["brann"] = existing
                db[k]["updated"] = now_iso()

        save_db_to_file(DB_FILENAME, db)
        st.success("Scenario 'Brann' lagret for valgt kumulesone.")
        st.rerun()


    # ---------- Skjema: Legg til risiko manuelt ----------
   # ---------- Skjema: Legg til risiko manuelt (lagrer på toppnivå i db) ----------
import uuid
from datetime import date

st.subheader("Legg til risiko manuelt")

with st.form("manual_add_form"):
    # Felter som matcher visningskoden
    forsnr = st.text_input("Forsikringsnummer (forsnr)")
    risikonr = st.text_input("Risikonummer (risikonr)")
    kundenavn = st.text_input("Kundenavn (kundenavn)", value="")
    adresse = st.text_input("Adresse (adresse)")
    postnummer = st.text_input("Postnummer (postnummer)", value="")
    kommune = st.text_input("Kommune (kommune)", value="")
    sum_forsikring = st.number_input("Sum forsikring (sum_forsikring) – NOK", min_value=0, step=10000)

    # Bruker samme kumulesone og scenario som valgt over
    # (forvalg gir rask registrering i riktig sone/scenario)
    default_index = kumule_liste.index(sel_kumule) if sel_kumule in kumule_liste else 0
    kumulesone = st.selectbox("Kumulesone (kumulesone)", kumule_liste, index=default_index)
    scenario_valg = st.selectbox("Scenario (scenario)", SCENARIOS, index=SCENARIOS.index(scen) if scen in SCENARIOS else 0)

    # Valgfritt – geokoordinater og fritekst
    #latitude = st.number_input("Latitude (valgfritt)", value=0.0, step=0.0001)
    #longitude = st.number_input("Longitude (valgfritt)", value=0.0, step=0.0001)
    beskrivelse = st.text_area("Beskrivelse (valgfritt)", value="")



    # Flagg for om objektet skal tas med i beregning (visningen sjekker 'include')
    include = st.checkbox("Ta med i beregning (include)", value=True)

    submitted = st.form_submit_button("Legg til risiko")

    if submitted:
        # Lag unik nøkkel for toppnivå-dict (slik visningen fanger den opp)
        key = f"MAN_{uuid.uuid4().hex[:8]}"

        # Bygg record med FELTNAVN som visningen forventer
        rec = {
            "forsnr": forsnr,
            "risikonr": risikonr,
            "kundenavn": kundenavn,
            "adresse": adresse,
            "postnummer": postnummer,
            "kommune": kommune,
            "sum_forsikring": float(sum_forsikring),
            "kumulesone": kumulesone,           # NB: matcher visningen (ikke 'kumule_id')
            "scenario": scenario_valg,          # matcher visningen
            "include": bool(include),           # matcher visningen

            # Valgfritt / ekstra
            #"latitude": latitude,
            #"longitude": longitude,
            "beskrivelse": beskrivelse,

            # EML-metadata (nye felt i databasen)
            "eml_beregnet_dato": eml_beregnet_dato,
            "eml_beregnet_av": eml_beregnet_av,

            # Overstyringsfelter - default
            "eml_rate_manual_on": False,
            "eml_rate_manual": 0.0,

            # Sporing
            "kilde": "manuell",
            "updated": now_iso(),
        }

        # Sørg for at db er et dict og ikke inneholder colliding keys
        if not isinstance(db, dict):
            st.error("DB er korrupt (forventet dict).")
        else:
            db[key] = rec  # <- Lagrer på toppnivå slik visningen leser
            # (valgfritt) hold på en speilliste for eksport/import:
            if "risikoer" not in db or not isinstance(db["risikoer"], list):
                db["risikoer"] = []
            db["risikoer"].append({**rec, "_key": key})

            save_db_to_file(DB_FILENAME, db)
            st.success(f"La til risiko {forsnr}/{risikonr} i '{kumulesone}' (key={key}).")
            st.rerun()
