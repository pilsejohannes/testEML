import json
from datetime import datetime
import streamlit as st

st.title("Risikovalg for flere objekter (radio + begrunnelse + lagring)")

# ---- Konfig ----
DB_FILENAME = "risiko_db.json"
# key, tittel, default
CATEGORIES = [
    ("brannrisiko", "Brannrisiko (0=ikke satt, 1=lav, 2=middels, 3=høy)", 0),
    ("begrensende_faktorer", "Begrensende faktorer (0=ingen … 3=høy)", 0),
]
STATUS_STEP = len(CATEGORIES)

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
    # 0=ikke satt
    return {0: "⚪ Ikke satt", 1: "🟩 Lav", 2: "🟨 Middels", 3: "🟥 Høy"}.get(int(v), "⚪ Ikke satt")

def color_chip_for_begr(v: int) -> str:
    # snudd skala: høy = grønn, lav/ingen = rød
    return {0: "🟥 Ingen", 1: "🟥 Lav", 2: "🟨 Middels", 3: "🟩 Høy"}.get(int(v), "⚪ Ikke satt")

# ---- Session init ----
if "db" not in st.session_state:
    st.session_state["db"] = load_db_from_file(DB_FILENAME) or {}
if "current_obj" not in st.session_state:
    st.session_state["current_obj"] = None
if "step" not in st.session_state:
    st.session_state["step"] = 0

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
                st.rerun()
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
st.subheader("Velg objekt")
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
    colA, colB, colC = st.columns([1, 1, 1])
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
            st.rerun()
    if colC.button("➕ Klon som nytt objekt"):
        base = curr
        i = 1
        new_name = f"{base} kopi {i}"
        while new_name in db:
            i += 1
            new_name = f"{base} kopi {i}"
        rec = dict(db[curr])
        rec["updated"] = now_iso()
        db[new_name] = rec
        st.session_state["current_obj"] = new_name
        save_db_to_file(DB_FILENAME, db)
        st.success(f"Klonet til: {new_name}")
        st.rerun()

    st.divider()

# ---- Navigasjon (uten callbacks) ----
col1, col2, col3 = st.columns(3)
if col1.button("← Tilbake", disabled=st.session_state["step"] == 0):
    st.session_state["step"] = max(0, st.session_state["step"] - 1)
    st.rerun()
if col2.button("Til første steg"):
    st.session_state["step"] = 0
    st.rerun()
if col3.button("Status"):
    st.session_state["step"] = STATUS_STEP
    st.rerun()

st.caption("Brannrisiko (0–3) og Begrensende faktorer (0–3) lagres separat per objekt.")
st.write(f"Steg: {st.session_state['step'] + 1}/{STATUS_STEP + 1}")

# ---- Stegvis UI ----
if not curr:
    st.info("Velg eller opprett et objekt for å sette verdier.")
else:
    if curr not in db or not isinstance(db[curr], dict):
        db[curr] = default_record()
    rec = db[curr]

    if st.session_state["step"] < len(CATEGORIES):
        key, title, default_val = CATEGORIES[st.session_state["step"]]
        st.subheader(title)

        current_val = int(rec.get(key, default_val))
        current_note = rec.get(f"{key}_note", "")

        # Etiketter til radio på linje
        if key == "brannrisiko":
            labels_map = {0: "Ikke satt", 1: "Lav", 2: "Middels", 3: "Høy"}
        else:
            labels_map = {0: "Ingen", 1: "Lav", 2: "Middels", 3: "Høy"}

        # Forvalg
        current_label = labels_map.get(current_val, list(labels_map.values())[0])

        # Radio på én linje
        new_label = st.radio(
            "Velg nivå:",
            options=list(labels_map.values()),
            index=list(labels_map.values()).index(current_label),
            horizontal=True,
            key=f"radio_{curr}_{key}",
        )
        # Oversett valgt label tilbake til tall
        new_val = [k for k, v in labels_map.items() if v == new_label][0]

        # Live fargeindikasjon
        if key == "brannrisiko":
            st.write(color_chip_for_brann(new_val))
        else:
            st.write(color_chip_for_begr(new_val))

        # Begrunnelse
        new_note = st.text_area(
            "Begrunnelse (hvorfor denne verdien?)",
            value=current_note,
            key=f"note_{curr}_{key}",
            placeholder="Skriv kort hvorfor du valgte verdien …",
        )

        # Lagre og neste
        if st.button("Lagre og neste"):
            rec[key] = int(new_val)
            rec[f"{key}_note"] = new_note
            rec["updated"] = now_iso()
            save_db_to_file(DB_FILENAME, db)  # best effort
            st.session_state["step"] = min(STATUS_STEP, st.session_state["step"] + 1)
            st.rerun()

        # Neste uten endring
        if st.button("Neste uten endring"):
            st.session_state["step"] = min(STATUS_STEP, st.session_state["step"] + 1)
            st.rerun()

    elif st.session_state["step"] == STATUS_STEP:
        # ---- Status for aktivt objekt ----
        st.subheader("📊 Status for aktivt objekt")
        brann = int(rec.get("brannrisiko", 0))
        begr = int(rec.get("begrensende_faktorer", 0))

        st.markdown(f"- **Brannrisiko:** {brann} ({color_chip_for_brann(brann)})")
        st.markdown(f"  - Begrunnelse: {rec.get('brannrisiko_note','').strip() or '—'}")

        st.markdown(f"- **Begrensende faktorer:** {begr} ({color_chip_for_begr(begr)})")
        st.markdown(f"  - Begrunnelse: {rec.get('begrensende_faktorer_note','').strip() or '—'}")

        st.caption(f"Sist oppdatert: {rec.get('updated','')}")

        st.divider()
        # ---- Alle objekter tabell ----
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
                    "Oppdatert": r.get("updated", "")
                })
            if rows:
                df = pd.DataFrame(rows).sort_values("Objekt")
                st.dataframe(df, use_container_width=True)
                st.download_button(
                    "⬇️ Last ned status (CSV)",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="risiko_status.csv",
                    mime="text/csv",
                )
            else:
                st.info("Ingen objekter i databasen ennå.")
        except Exception:
            st.info("Pandas ikke tilgjengelig – tabellvisning hoppet over.")

        st.divider()
        # Hurtig bytte objekt
        if objekter:
            ny_curr = st.selectbox("Bytt aktivt objekt", objekter, key="switch_obj")
            if st.button("Bytt"):
                st.session_state["current_obj"] = ny_curr
                st.rerun()

        if st.button("Til første steg for dette objektet"):
            st.session_state["step"] = 0
            st.rerun()
