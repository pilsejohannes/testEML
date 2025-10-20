import json
from datetime import datetime
import streamlit as st

st.title("Risikovalg – ett skjermbilde per objekt")

# ---- Konfig ----
DB_FILENAME = "risiko_db.json"
CATEGORIES = [
    ("brannrisiko", "Brannrisiko (0=ikke satt, 1=lav, 2=middels, 3=høy)", 0),
    ("begrensende_faktorer", "Begrensende faktorer (0=ingen … 3=høy)", 0),
    ("avstand_brannstasjon", "Avstand til brannstasjon (0=ikke satt, 1=kort, 2=middels, 3=lang)", 0),
]

# ---- Hjelpere ----
def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def default_record():
    rec = {"updated": now_iso()}
    for key, _, default in CATEGORIES:
        rec[key] = default
        rec[f"{key}_note"] = ""
    return rec

def load_db_from_file(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def save_db_to_file(path: str, db: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True, None
    except Exception as e:
        return False, str(e)

def color_chip_for_brann(v: int) -> str:
    return {0: "⚪ Ikke satt", 1: "🟩 Lav", 2: "🟨 Middels", 3: "🟥 Høy"}.get(int(v), "⚪ Ikke satt")

def color_chip_for_begr(v: int) -> str:
    # snudd skala: høy = grønn, lav/ingen = rød
    return {0: "🟥 Ingen", 1: "🟥 Lav", 2: "🟨 Middels", 3: "🟩 Høy"}.get(int(v), "⚪ Ikke satt")
  
def color_chip_for_brst(v: int) -> str:
    return {0: "🟥 Ingen", 1: "🟩 kort", 2: "🟨 Middels", 3: "🟥 Lang"}.get(int(v), "⚪ Ikke satt")

# ---- Session init ----
if "db" not in st.session_state:
    st.session_state["db"] = load_db_from_file(DB_FILENAME) or {}
if "current_obj" not in st.session_state:
    st.session_state["current_obj"] = None

db = st.session_state["db"]

# ---- Import/eksport ----
with st.expander("📁 Import/eksport database", expanded=False):
    st.caption("Last opp en tidligere JSON for å hente forrige kjøring. Last ned for å lagre.")
    up = st.file_uploader("Last opp database (JSON)", type=["json"])
    if up is not None:
        try:
            loaded = json.load(up)
            if isinstance(loaded, dict):
                db.update(loaded)
                # migrer evt. manglende felt
                for name, rec in list(db.items()):
                    if not isinstance(rec, dict):
                        db[name] = default_record()
                        continue
                    for key, _, default in CATEGORIES:
                        rec.setdefault(key, default)
                        rec.setdefault(f"{key}_note", "")
                    rec.setdefault("updated", now_iso())
                save_db_to_file(DB_FILENAME, db)
                st.success("Database importert.")
                st.experimental_rerun()
            else:
                st.error("Filen må være et JSON-objekt.")
        except Exception as e:
            st.error(f"Ugyldig JSON: {e}")

    st.download_button(
        "⬇️ Last ned database (JSON)",
        data=json.dumps(db, ensure_ascii=False, indent=2),
        file_name="risiko_db.json",
        mime="application/json",
    )

# ---- Velg/lag objekt ----
st.subheader("Objekt")
objekter = sorted(db.keys())
valg = st.selectbox("Velg eksisterende objekt", ["— Nytt objekt —"] + objekter)
if valg != "— Nytt objekt —":
    st.session_state["current_obj"] = valg
else:
    ny = st.text_input("Navn/ID for nytt objekt (f.eks. 'Bygning 1')")
    if st.button("Opprett objekt"):
        if not ny:
            st.warning("Skriv inn et navn først.")
        elif ny in db:
            st.warning("Dette objektet finnes allerede.")
        else:
            db[ny] = default_record()
            st.session_state["current_obj"] = ny
            save_db_to_file(DB_FILENAME, db)
            st.success(f"Opprettet objekt: {ny}")
            st.rerun()

curr = st.session_state["current_obj"]

# ---- Objektverktøy ----
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
            st.session_state["current_obj"] = None
            save_db_to_file(DB_FILENAME, db)
            st.success("Objekt slettet.")
            st.experimental_rerun()
    if colC.button("➕ Klon som nytt objekt"):
        base = curr
        i = 1
        new_name = f"{base} kopi {i}"
        while new_name in db:
            i += 1
            new_name = f"{base} kopi {i}"
        rec_clone = dict(db[curr])
        rec_clone["updated"] = now_iso()
        db[new_name] = rec_clone
        st.session_state["current_obj"] = new_name
        save_db_to_file(DB_FILENAME, db)
        st.success(f"Klonet til: {new_name}")
        st.experimental_rerun()

    st.divider()

# ---- En-skjerm editor for aktivt objekt ----
if not curr:
    st.info("Velg eller opprett et objekt for å sette verdier.")
else:
    rec = db.get(curr) or default_record()
    db[curr] = rec  # sikkerhet

    with st.form(key=f"edit_{curr}", clear_on_submit=False):
        st.subheader("Alle valg for aktivt objekt")

        # Rad 1: Brannrisiko
        st.markdown("#### Brannrisiko")
        brann_val = int(rec.get("brannrisiko", 0))
        brann_labels = {0: "Ikke satt", 1: "Lav", 2: "Middels", 3: "Høy"}
        brann_label_current = brann_labels.get(brann_val, "Ikke satt")
        brann_label_new = st.radio(
            "Velg nivå:",
            options=list(brann_labels.values()),
            index=list(brann_labels.values()).index(brann_label_current),
            horizontal=True,
            key=f"radio_{curr}_brannrisiko",
        )
        new_brann = [k for k, v in brann_labels.items() if v == brann_label_new][0]
        st.write(color_chip_for_brann(new_brann))
        brann_note = st.text_area(
            "Begrunnelse (brannrisiko)",
            value=rec.get("brannrisiko_note",""),
            key=f"note_{curr}_brannrisiko",
            placeholder="Hvorfor valgte du denne brannrisikoen?"
        )

        st.markdown("---")

        # Rad 2: Begrensende faktorer
        st.markdown("#### Begrensende faktorer")
        begr_val = int(rec.get("begrensende_faktorer", 0))
        begr_labels = {0: "Ingen", 1: "Lav", 2: "Middels", 3: "Høy"}
        begr_label_current = begr_labels.get(begr_val, "Ingen")
        begr_label_new = st.radio(
            "Velg nivå:",
            options=list(begr_labels.values()),
            index=list(begr_labels.values()).index(begr_label_current),
            horizontal=True,
            key=f"radio_{curr}_begrensende",
        )
        new_begr = [k for k, v in begr_labels.items() if v == begr_label_new][0]
        st.write(color_chip_for_begr(new_begr))
        begr_note = st.text_area(
            "Begrunnelse (begrensende faktorer)",
            value=rec.get("begrensende_faktorer_note",""),
            key=f"note_{curr}_begrensende",
            placeholder="Hvorfor valgte du dette nivået for begrensende faktorer?"
        )

        st.markdown("---")
                # Rad 3: Avstand til brannstasjon
        st.markdown("#### Avstand til brannstasjon")
        brst_val = int(rec.get("avstand_brannstasjon", 0))
        brst_labels = {0: "Ingen", 1: "Kort", 2: "Middels", 3: "Lang"}
        brst_label_current = brst_labels.get(begr_val, "Ingen")
        brst_label_new = st.radio(
            "Velg nivå:",
            options=list(brst_labels.values()),
            index=list(brst_labels.values()).index(brst_label_current),
            horizontal=True,
            key=f"radio_{curr}_avstand",
        )
        new_brst = [k for k, v in brst_labels.items() if v == brst_label_new][0]
        st.write(color_chip_for_begr(new_brst))
        brst_note = st.text_area(
            "Begrunnelse (avstand brannstasjon)",
            value=rec.get("avstand_brannstasjon_note",""),
            key=f"note_{curr}_avstand",
            placeholder="Er brannstasjonen døgnbemannet?"
        )

        st.markdown("---")
        submitted = st.form_submit_button("💾 Lagre endringer")
        if submitted:
            rec["brannrisiko"] = int(new_brann)
            rec["brannrisiko_note"] = brann_note
            rec["begrensende_faktorer"] = int(new_begr)
            rec["begrensende_faktorer_note"] = begr_note
            rec["avstand_brannstasjon"] = int(new_brst)
            rec["avstand_brannstasjon_note"] = brst_note
            rec["updated"] = now_iso()
            ok, err = save_db_to_file(DB_FILENAME, db)
            if ok:
                st.success("Endringer lagret.")
            else:
                st.info("Kunne ikke lagre til fil i dette miljøet. Last ned JSON fra 'Import/eksport' for å lagre lokalt.")

# ---- Status for alle objekter ----
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
                "Brannrisiko": int(r.get("brannrisiko", 0)),
                "Brann (farge)": color_chip_for_brann(int(r.get("brannrisiko", 0))),
                "Brann – begrunnelse": r.get("brannrisiko_note", ""),
                "Begrensende faktorer": int(r.get("begrensende_faktorer", 0)),
                "Begr. (farge)": color_chip_for_begr(int(r.get("begrensende_faktorer", 0))),
                "Begr. – begrunnelse": r.get("begrensende_faktorer_note", ""),
                "Oppdatert": r.get("updated", ""),
                "Avstand til brannstasjon": int(r.get("avstand_brannstasjon", 0)),
                "Brst. (farge)": color_chip_for_brst(int(r.get("avstand_brannstasjon", 0))),
                "Brst. – begrunnelse": r.get("avstand_brannstasjon_note", ""),
                "Oppdatert": r.get("updated", "")
            })
        df = pd.DataFrame(rows).sort_values("Objekt")
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "⬇️ Last ned status (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="risiko_status.csv",
            mime="text/csv",
        )
    except Exception:
        st.info("Pandas ikke tilgjengelig – tabellvisning hoppet over.")
else:
    st.info("Ingen objekter i databasen ennå.")
