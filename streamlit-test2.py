import json
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

import streamlit as st

# ==========================================================
# EML-prototype – v0.5 (kumule-summer + EML-sats)
# ----------------------------------------------------------
# Nytt i denne versjonen:
# - EML beregnes via en EML-sats (% av forsikringssum)
#   * Maskinell sats (veiledende) avledet av faktorene
#   * Manuell overstyring av sats (prosent) – tydelig kildeangivelse
#   * (Bakoverkompatibel) Manuell overstyring av EML-beløp hvis eksisterende felt er satt
# - Kumulevis oppsummering: summerer EML (effektiv) pr. kumulesone
# - Kumule-listing viser alle risikoer i soner over terskel (ikke bare store risikoer)
# - Robust Excel-lesing (openpyxl) og tydelig feedback
# ==========================================================

st.set_page_config(page_title="EML-prototype", layout="wide")

from pathlib import Path
VERSION = "0.5"
st.title(f"EML-prototype (v{VERSION})")
st.caption(f"Kjører fil: {Path(__file__).resolve()}")

# ------------------------------
# Konfig / taksonomi
# ------------------------------
DB_FILENAME = "risiko_db.json"
SCHEMA_VERSION = 5
DEFAULT_TERSKEL = 800_000_000  # 800 MNOK

# Excel-kolonner – forventet navn i regnearket
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

# Kategorier i UI (0–3-skala) + sum_forsikring
CATEGORY_DEFS: List[Tuple[str, str, int, str, str]] = [
    ("sum_forsikring", "Forsikringssum (NOK)", 0, "Total forsikringssum for objektet", "money"),
    ("brannrisiko", "Brannrisiko", 0, "0=ikke satt, 1=lav, 2=middels, 3=høy", "normal"),
    ("begrensende_faktorer", "Begrensende faktorer", 0, "0=ingen, 1=lav, 2=middels, 3=høy (mer som begrenser skaden)", "inverse"),
    ("deteksjon_beskyttelse", "Deteksjon/Beskyttelse", 0, "0=ingen, 1=lav, 2=middels, 3=høy (sprinkler, alarm, brannseksj.)", "inverse"),
    ("eksponering_nabo", "Eksponering/avstand til nabo", 0, "0=tett/tilgrensende, 3=isolert", "normal"),
]

# ------------------------------
# Hjelpere
# ------------------------------

def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def default_record() -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "_schema": SCHEMA_VERSION,
        "updated": now_iso(),
        "audit": [],
        # Overstyringer (ny: sats). Behold gamle felt for bakoverkomp.
        "eml_rate_manual_on": False,
        "eml_rate_manual": 0.0,   # 0.25 => 25 %
        "eml_manual_on": False,   # legacy (absolutt beløp)
        "eml_manual_value": 0.0,  # legacy
        # metadata
        "risikonr": None,
        "kumulesone": None,
        "objektnavn": None,
        "adresse": None,
        "kundenavn": None,
    }
    for key, _, default, _, _ in CATEGORY_DEFS:
        rec[key] = default
        if key not in ("sum_forsikring",):
            rec[f"{key}_note"] = ""
    return rec


def migrate_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(rec, dict):
        return default_record()
    rec.setdefault("_schema", SCHEMA_VERSION)
    rec.setdefault("audit", [])
    rec.setdefault("eml_rate_manual_on", False)
    rec.setdefault("eml_rate_manual", 0.0)
    rec.setdefault("eml_manual_on", False)
    rec.setdefault("eml_manual_value", 0.0)
    rec.setdefault("risikonr", None)
    rec.setdefault("kumulesone", None)
    rec.setdefault("objektnavn", None)
    rec.setdefault("adresse", None)
    rec.setdefault("kundenavn", None)
    for key, _, default, _, _ in CATEGORY_DEFS:
        rec.setdefault(key, default)
        if key not in ("sum_forsikring",):
            rec.setdefault(f"{key}_note", "")
    rec.setdefault("updated", now_iso())
    return rec


def load_db_from_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                for k, v in list(data.items()):
                    data[k] = migrate_record(v)
                return data
    except Exception:
        pass
    return {}


def save_db_to_file(path: str, db: Dict[str, Any]):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True, None
    except Exception as e:
        return False, str(e)


# Chips/etiketter
BRANN_CHIP = {0: "⚪ Ikke satt", 1: "🟩 Lav", 2: "🟨 Middels", 3: "🟥 Høy"}
INVERSE_CHIP = {0: "🟥 Ingen", 1: "🟥 Lav", 2: "🟨 Middels", 3: "🟩 Høy"}
EXPO_CHIP = {0: "🟥 Tett", 1: "🟧 Nabo nært", 2: "🟨 Noe avstand", 3: "🟩 Isolert"}


def chip_for(key: str, v: int) -> str:
    if key == "brannrisiko":
        return BRANN_CHIP.get(int(v), "⚪ Ikke satt")
    if key in ("begrensende_faktorer", "deteksjon_beskyttelse"):
        return INVERSE_CHIP.get(int(v), "⚪ Ikke satt")
    if key == "eksponering_nabo":
        return EXPO_CHIP.get(int(v), "⚪ Ikke satt")
    return BRANN_CHIP.get(int(v), "⚪ Ikke satt")


# ------------------------------
# EML – maskinell sats og beløp (veiledende)
# ------------------------------
# Vi uttrykker modellen som en RATE (andel av SI). Beløp = rate * SI.
BASE = 0.6
ALPHA = [1.00, 1.15, 1.35, 1.60]      # brann
BETA  = [0.40, 0.30, 0.20, 0.10]      # beskyttelse (reduserer)
GAMMA = [0.05, 0.10, 0.15, 0.20]      # begrensning (reduserer)
EXPO  = [1.30, 1.15, 1.00, 0.85]      # eksponering


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


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
    # Prioritet: manuell sats -> legacy manuell beløp -> maskinell sats
    if rec.get("eml_rate_manual_on"):
        return clamp01(float(rec.get("eml_rate_manual", 0.0)))
    if rec.get("eml_manual_on"):
        try:
            si = float(rec.get("sum_forsikring", 0)) or 0.0
            val = float(rec.get("eml_manual_value", 0.0))
            return clamp01(0.0 if si <= 0 else val/si)
        except Exception:
            return 0.0
    return calc_eml_rate_machine(rec)


def calc_eml_amount_from_rate(rec: Dict[str, Any], rate: float) -> int:
    try:
        si = float(rec.get("sum_forsikring", 0))
        return int(max(0, round(si * rate)))
    except Exception:
        return 0


def calc_eml_machine(rec: Dict[str, Any]) -> int:
    return calc_eml_amount_from_rate(rec, calc_eml_rate_machine(rec))


def calc_eml_effective(rec: Dict[str, Any]) -> int:
    return calc_eml_amount_from_rate(rec, calc_eml_rate_effective(rec))


def eml_source_label(rec: Dict[str, Any]) -> str:
    if rec.get("eml_rate_manual_on"):
        return "Manuelt satt sats"
    if rec.get("eml_manual_on"):
        return "Manuelt satt beløp (legacy)"
    return "Maskinelt (veiledende)"


# ------------------------------
# Session-init
# ------------------------------
if "db" not in st.session_state:
    st.session_state.db = load_db_from_file(DB_FILENAME) or {}
if "current_obj" not in st.session_state:
    st.session_state.current_obj = None
if "terskel" not in st.session_state:
    st.session_state.terskel = DEFAULT_TERSKEL


db: Dict[str, Any] = st.session_state.db

# ------------------------------
# Sidebar: Import/eksport + parametre
# ------------------------------
with st.sidebar:
    st.header("📁 Import / eksport")
    up_json = st.file_uploader("Last opp database (JSON)", type=["json"], help="Merger innholdet i minnet.")
    if up_json is not None:
        try:
            loaded = json.load(up_json)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    db[k] = migrate_record(v)
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

    st.divider()
    st.header("⚙️ Parametre (prototyp)")
    base = st.slider("BASE (andel av SI i spill)", 0.1, 0.9, BASE, 0.05)
    if base != BASE:
        globals()["BASE"] = base
    st.session_state.terskel = st.number_input(
        "Terskel for kumulerende risiko (NOK)",
        min_value=0,
        step=50_000_000,
        value=int(st.session_state.terskel),
        help="Vis kumulesoner der sum forsikring ≥ terskel. Default 800 MNOK.")

# ------------------------------
# Startmodus-velger
# ------------------------------
start_mode = st.radio(
    "Velg startmodus",
    ["Kumulesoner fra Excel", "Manuell registrering"],
    horizontal=True,
)

# ==========================================================
# MODUS 1: Kumulesoner fra Excel
# ==========================================================
if start_mode == "Kumulesoner fra Excel":
    st.subheader("1) Last opp Excel med risikoer")
    st.caption("Eksempel: 'Test til streamlit.xlsx'. Vi forventer kolonner som beskrevet nedenfor.")

with st.expander("Forventede Excel-kolonner", expanded=False):
    st.write("\n".join([f"• {col}" for col in EXPECTED_COLS.values()]))


    up_xlsx = st.file_uploader("Last opp Excel (.xlsx)", type=["xlsx"], key="xlsx_uploader")

    if up_xlsx is not None:
        try:
            import pandas as pd, io
            _bytes = up_xlsx.read()
            df = pd.read_excel(io.BytesIO(_bytes), engine="openpyxl")
            up_xlsx.seek(0)

            df.columns = [str(c).strip() for c in df.columns]
            lower_to_orig = {c.lower(): c for c in df.columns}

            def col(name_key: str) -> Optional[str]:
                expected = EXPECTED_COLS[name_key]
                return lower_to_orig.get(expected.lower())

            required = ["kumulenr", "risikonr"]
            missing = [EXPECTED_COLS[k] for k in required if col(k) is None]
            if missing:
                st.error("Mangler påkrevde kolonner: " + ", ".join(missing))
            else:
                st.success(f"Lest {len(df)} rader fra Excel – kolonner: {list(df.columns)}")

                kumule_col = col("kumulenr")
                kumulesum_col = col("kumulesum")
                tariff_col = col("tariffsum")

                # Sum per kumule: bruk Kumulesum hvis tilstede, ellers sum av Tariffsum
                import pandas as pd
                if kumulesum_col and kumulesum_col in df.columns:
                    df["__sum_candidate__"] = pd.to_numeric(df[kumulesum_col], errors="coerce").fillna(0)
                elif tariff_col and tariff_col in df.columns:
                    df["__sum_candidate__"] = pd.to_numeric(df[tariff_col], errors="coerce").fillna(0)
                else:
                    df["__sum_candidate__"] = 0

                kumule_summer = df.groupby(kumule_col)["__sum_candidate__"].sum().reset_index(name="sum_kumule")
                terskel = st.session_state.terskel
                store = kumule_summer[kumule_summer["sum_kumule"] >= terskel]

                st.subheader("2) Velg kumulesone(r) over terskel")
                st.caption(f"Viser kumulesoner med samlet forsikringssum ≥ {terskel:,.0f} NOK".replace(",", " "))
                st.dataframe(store.sort_values("sum_kumule"), use_container_width=True)

                valgte_kumuler = st.multiselect(
                    "Velg kumulesone(r)",
                    options=list(store[kumule_col].astype(str).unique()),
                )

                if valgte_kumuler:
                    st.subheader("3) Velg risikoer (alle i valgt kumule)")
                    tablist = st.tabs([f"Kumule {k}" for k in valgte_kumuler])

                    selected_ids: List[str] = []
                    for idx, k in enumerate(valgte_kumuler):
                        with tablist[idx]:
                            subset = df[df[kumule_col].astype(str) == str(k)].copy()
                            risiko_col = col("risikonr")
                            adresse_col = col("adresse")
                            kundenavn_col = col("kundenavn")
                            si_col = tariff_col or col("eml_sum") or col("kumulesum")

                            if si_col:
                                subset["__si__"] = pd.to_numeric(subset[si_col], errors="coerce").fillna(0)
                            else:
                                subset["__si__"] = 0

                            for i, row in subset.iterrows():
                                rid = str(row[risiko_col])
                                label = f"{rid} – {row.get(adresse_col, '')} (SI≈{int(row['__si__']):,} NOK)".replace(",", " ")
                                chk = st.checkbox(label, key=f"sel_{k}_{rid}")
                                if chk:
                                    selected_ids.append(rid)

                    if selected_ids:
                        st.success(f"Valgt {len(selected_ids)} risiko(er)")
                        if st.button("📥 Importer valgte risikoer til databasen"):
                            imported = 0
                            for rid in selected_ids:
                                rows = df[df[col("risikonr")].astype(str) == str(rid)]
                                if rows.empty:
                                    continue
                                row = rows.iloc[0]
                                navn = f"{row[col('kumulenr')]}-{row[col('risikonr')]}-{row.get(col('adresse'), '')}".strip("-")
                                rec = migrate_record(db.get(navn) or default_record())
                                rec["objektnavn"] = str(row.get(col("kundenavn"), navn))
                                rec["adresse"] = str(row.get(col("adresse"), ""))
                                rec["kundenavn"] = str(row.get(col("kundenavn"), ""))
                                rec["risikonr"] = str(row.get(col("risikonr"), ""))
                                rec["kumulesone"] = str(row.get(col("kumulenr"), ""))
                                # SI fra Tariffsum (fallback: EML sum -> Kumulesum)
                                si_val = 0.0
                                for key_try in [col("tariffsum"), col("eml_sum"), col("kumulesum")]:
                                    if key_try and key_try in row and not pd.isna(row[key_try]):
                                        try:
                                            si_val = float(row[key_try])
                                            break
                                        except Exception:
                                            pass
                                rec["sum_forsikring"] = si_val
                                rec["updated"] = now_iso()
                                db[navn] = rec
                                imported += 1
                            save_db_to_file(DB_FILENAME, db)
                            st.success(f"Importert {imported} objekt(er) til databasen. Gå til 'Status – alle objekter' eller 'Manuell registrering' for videre arbeid.")
        except Exception as e:
            st.error(f"Kunne ikke lese Excel: {e}")

# ==========================================================
# MODUS 2: Manuell registrering (ett objekt om gangen)
# ==========================================================
if start_mode == "Manuell registrering":
    st.subheader("Objekt")
    objekter = sorted(db.keys())
    valg = st.selectbox("Velg eksisterende objekt", ["— Nytt objekt —"] + objekter)
    if valg != "— Nytt objekt —":
        st.session_state.current_obj = valg
    else:
        ny = st.text_input("Navn/ID for nytt objekt (f.eks. 'Bygning 1')")
        if st.button("Opprett objekt"):
            if not ny:
                st.warning("Skriv inn et navn først.")
            elif ny in db:
                st.warning("Dette objektet finnes allerede.")
            else:
                db[ny] = default_record()
                st.session_state.current_obj = ny
                save_db_to_file(DB_FILENAME, db)
                st.success(f"Opprettet objekt: {ny}")
                st.experimental_rerun()

    curr = st.session_state.current_obj

    if curr:
        st.markdown(f"**Aktivt objekt:** `{curr}`")
        colA, colB, colC = st.columns([1,1,1])
        if colA.button("💾 Lagre nå"):
            ok, err = save_db_to_file(DB_FILENAME, db)
            if ok:
                st.success(f"Lagret til `{DB_FILENAME}` (dersom miljøet tillater filskriving).")
            else:
                st.info("Kunne ikke lagre til fil i dette miljøet. Bruk nedlasting av JSON i stedet.")
        if colB.button("🗑️ Slett objekt"):
            if curr in db:
                del db[curr]
                st.session_state.current_obj = None
                save_db_to_file(DB_FILENAME, db)
                st.success("Objekt slettet.")
                st.experimental_rerun()
        if colC.button("➕ Klon som nytt objekt"):
            base_name = curr
            i = 1
            new_name = f"{base_name} kopi {i}"
            while new_name in db:
                i += 1
                new_name = f"{base_name} kopi {i}"
            rec_clone = dict(db[curr])
            rec_clone["updated"] = now_iso()
            rec_clone.setdefault("audit", []).append({"ts": now_iso(), "msg": "Klonet fra annet objekt"})
            db[new_name] = rec_clone
            st.session_state.current_obj = new_name
            save_db_to_file(DB_FILENAME, db)
            st.success(f"Klonet til: {new_name}")
            st.experimental_rerun()

        st.divider()

    # Editor
    if not curr:
        st.info("Velg eller opprett et objekt for å sette verdier.")
    else:
        rec = migrate_record(db.get(curr) or default_record())
        db[curr] = rec

        # Toppkort med nøkkeltall
        eml_rate_eff = calc_eml_rate_effective(rec)
        eml_rate_mach = calc_eml_rate_machine(rec)
        eml_eff = calc_eml_effective(rec)
        eml_mach = calc_eml_machine(rec)
        with st.container():
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("EML (effektiv)", f"{eml_eff:,.0f}".replace(",", " "), help=eml_source_label(rec))
            c2.metric("Sats (effektiv)", f"{eml_rate_eff*100:.1f}%")
            c3.metric("Maskinelt beløp", f"{eml_mach:,.0f}".replace(",", " "))
            c4.metric("Maskinell sats", f"{eml_rate_mach*100:.1f}%")
            c5.metric("Eksponering", chip_for("eksponering_nabo", rec.get("eksponering_nabo", 0)))

        with st.form(key=f"edit_{curr}", clear_on_submit=False):
            st.subheader("Vurderinger for aktivt objekt")

            # Metadata
            col_meta1, col_meta2, col_meta3 = st.columns(3)
            with col_meta1:
                rec["objektnavn"] = st.text_input("Objektnavn", value=rec.get("objektnavn") or "")
            with col_meta2:
                rec["risikonr"] = st.text_input("Risikonr", value=(rec.get("risikonr") or ""))
            with col_meta3:
                rec["kumulesone"] = st.text_input("Kumulesone", value=(rec.get("kumulesone") or ""))
            col_meta4, col_meta5 = st.columns(2)
            with col_meta4:
                rec["adresse"] = st.text_input("Adresse", value=rec.get("adresse") or "")
            with col_meta5:
                rec["kundenavn"] = st.text_input("Kundenavn", value=rec.get("kundenavn") or "")

            # Forsikringssum
            sum_si = st.number_input(
                "Forsikringssum (NOK)",
                min_value=0.0,
                value=float(rec.get("sum_forsikring", 0)),
                step=100000.0,
                help="Direkte input fra kildesystem – i produksjon bør dette hentes via API."
            )

            st.markdown("---")

            # Skala-kontroller
            def level_radio(label: str, key: str, help_txt: str, initial: int):
                labels = {0: "0 – Ikke satt/negativ", 1: "1 – Lav", 2: "2 – Middels", 3: "3 – Høy"}
                idx = list(labels.keys()).index(int(initial)) if int(initial) in labels else 0
                choice = st.radio(
                    label,
                    options=list(labels.values()),
                    index=idx,
                    horizontal=True,
                    key=f"radio_{curr}_{key}",
                    help=help_txt,
                )
                picked = [k for k, v in labels.items() if v == choice][0]
                st.write(chip_for(key, picked))
                note = st.text_area(
                    f"Begrunnelse – {label}",
                    value=rec.get(f"{key}_note", ""),
                    key=f"note_{curr}_{key}",
                    placeholder=f"Hvorfor valgte du {picked}?"
                )
                return int(picked), note

            brann, brann_note = level_radio("Brannrisiko", "brannrisiko", "0=ikke satt … 3=høy", rec.get("brannrisiko", 0))
            st.markdown("---")
            begr, begr_note = level_radio("Begrensende faktorer", "begrensende_faktorer", "0=ingen … 3=høy", rec.get("begrensende_faktorer", 0))
            st.markdown("---")
            prot, prot_note = level_radio("Deteksjon/Beskyttelse", "deteksjon_beskyttelse", "0=ingen … 3=høy", rec.get("deteksjon_beskyttelse", 0))
            st.markdown("---")
            expo, expo_note = level_radio("Eksponering/avstand til nabo", "eksponering_nabo", "0=tett … 3=isolert", rec.get("eksponering_nabo", 0))

            st.markdown("---")
            # Overstyr EML – sats (anbefalt) eller legacy beløp
            st.subheader("EML – kilde og overstyring")
            use_manual_rate = st.checkbox("Overstyr EML-sats manuelt", value=bool(rec.get("eml_rate_manual_on", False)))
            manual_rate_pct = st.number_input(
                "Manuell EML-sats (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(rec.get("eml_rate_manual", 0.0) * 100.0),
                step=0.5,
                help="Når aktivert brukes denne satsen. Maskinell sats vises som veiledende."
            )
            # Legacy beløp om ønskelig
            use_manual_abs = st.checkbox("(Valgfritt) Overstyr EML-beløp (legacy)", value=bool(rec.get("eml_manual_on", False)))
            manual_abs = st.number_input(
                "Manuelt EML-beløp (NOK)",
                min_value=0.0,
                value=float(rec.get("eml_manual_value", 0.0)),
                step=100000.0,
                help="Hvis satt, brukes dette beløpet. Satsen avledes av SI. Overstyres av manuell sats dersom begge er aktivert."
            )

            st.info(
                f"Maskinell sats (veiledende): {calc_eml_rate_machine(rec)*100:.1f}%  –  "
                f"Maskinelt beløp: {calc_eml_machine(rec):,} NOK".replace(",", " ")
            )

            submitted = st.form_submit_button("💾 Lagre endringer")
            if submitted:
                rec["sum_forsikring"] = sum_si
                rec["brannrisiko"] = brann
                rec["brannrisiko_note"] = brann_note
                rec["begrensende_faktorer"] = begr
                rec["begrensende_faktorer_note"] = begr_note
                rec["deteksjon_beskyttelse"] = prot
                rec["deteksjon_beskyttelse_note"] = prot_note
                rec["eksponering_nabo"] = expo
                rec["eksponering_nabo_note"] = expo_note
                rec["eml_rate_manual_on"] = bool(use_manual_rate)
                rec["eml_rate_manual"] = float(manual_rate_pct) / 100.0
                rec["eml_manual_on"] = bool(use_manual_abs)
                rec["eml_manual_value"] = float(manual_abs)
                rec["updated"] = now_iso()
                rec.setdefault("audit", []).append({
                    "ts": now_iso(),
                    "msg": "Oppdatert vurderinger",
                    "eml_effective": calc_eml_effective(rec),
                    "eml_rate_effective": calc_eml_rate_effective(rec),
                    "eml_rate_machine": calc_eml_rate_machine(rec),
                    "eml_source": eml_source_label(rec),
                })

                ok, err = save_db_to_file(DB_FILENAME, db)
                if ok:
                    st.success("Endringer lagret.")
                else:
                    st.info("Kunne ikke lagre til fil i dette miljøet. Last ned JSON fra sidemenyen for å lagre lokalt.")

# ------------------------------
# Status for alle objekter + kumule-eksponering
# ------------------------------
st.divider()
st.subheader("📚 Status – alle objekter")
if db:
    try:
        import pandas as pd
        rows = []
        for name, r in db.items():
            if not isinstance(r, dict):
                continue
            rows.append({
                "Objekt": name,
                "Kunde": r.get("kundenavn", ""),
                "Adresse": r.get("adresse", ""),
                "Kumulesone": r.get("kumulesone", ""),
                "Risikonr": r.get("risikonr", ""),
                "Sum forsikring": r.get("sum_forsikring", 0),
                "Sats (effektiv %)": round(calc_eml_rate_effective(r)*100, 2),
                "EML (effektiv)": calc_eml_effective(r),
                "Kilde": eml_source_label(r),
                "Oppdatert": r.get("updated", ""),
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            st.dataframe(df.sort_values(["Kumulesone", "Objekt"]), use_container_width=True)

            # Kumule-summer
            st.subheader("📊 Kumule-eksponering (sum EML effektiv per kumulesone)")
            grp = df.groupby("Kumulesone", dropna=False)["EML (effektiv)"].sum().reset_index()
            grp = grp.sort_values("EML (effektiv)", ascending=False)
            st.dataframe(grp, use_container_width=True)

            st.download_button(
                "⬇️ Last ned status (CSV)",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="eml_status.csv",
                mime="text/csv",
            )
            st.download_button(
                "⬇️ Last ned kumule-summer (CSV)",
                data=grp.to_csv(index=False).encode("utf-8"),
                file_name="eml_kumule_summer.csv",
                mime="text/csv",
            )
        else:
            st.info("Ingen objekter i databasen ennå.")
    except Exception:
        st.info("Pandas ikke tilgjengelig – tabellvisning/CSV hoppet over.")
else:
    st.info("Ingen objekter i databasen ennå.")
