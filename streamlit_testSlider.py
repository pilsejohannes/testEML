import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import date
import streamlit as st, sys
import traceback
import streamlit as st, traceback
import uuid

MEDIA_DIR = Path("eml_media")
MEDIA_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="EML-prototype", layout="wide")
st.caption(f"DEBUG: fil={Path(__file__).name}  |  Streamlit={st.__version__}")
st.set_option("client.showErrorDetails", True)


VERSION = "0.4"
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
    "risikonrbeskrivelse": "Risikonr beskrivelse",
    "forsnr": "Forsnr",
    "adresse": "Adresse",
    "kundenavn": "Kundenavn",
    "tariffsum": "Tariffsum",
}

# ==========================================================
# --- HJELPEFUNKSJONER
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

def _fmt_nok(n: int | float) -> str:
    try:
        return f"{int(round(float(n))):,} NOK".replace(",", " ")
    except Exception:
        return str(n)

def _fmt_pct(x: float) -> str:
    try:
        return f"{float(x):.2f}%"
    except Exception:
        return str(x)

def _has_reportlab() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except Exception:
        return False
PDF_BYTES_KEY = "eml_pdf_bytes"
PDF_READY_TS_KEY = "eml_pdf_ready_ts"

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


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


# --- Brann-scenariofaktorer (brukes i scenariofanen) ---
BRANN_RISIKO_FAKTOR = {"Lav": 0.20, "Middels": 0.60, "Høy": 1.0}
BRANN_SPREDNING_FAKTOR = {"Liten": 0.40, "Middels": 0.80, "Stor": 1.00}
BRANN_SLUKKE_FAKTOR = {"Kort": 0.40, "Middels": 0.80, "Lang": 1.00}

def calc_skadegrad_from_brann_choices(rec: Dict[str, Any]) -> Optional[float]:
    """
    Hvis vi har lagret scenario-valgene for 'brann', beregn en EML-rate derfra.
    Returnerer None hvis ingen gyldige brann-verdier finnes.
    """
    b = rec.get("brann") or {}
    r = b.get("risiko_for_brann")
    s = b.get("spredning_av_brann")
    t = b.get("tid_for_slukkeinnsats")
    if r in BRANN_RISIKO_FAKTOR and s in BRANN_SPREDNING_FAKTOR and t in BRANN_SLUKKE_FAKTOR:
        sats = BRANN_RISIKO_FAKTOR[r] * BRANN_SPREDNING_FAKTOR[s] * BRANN_SLUKKE_FAKTOR[t]
        return clamp01(sats)
    return None


def calc_skadegrad_machine(rec: Dict[str, Any]) -> float:
    """
    Prioritet:
    1) Hvis brann-scenariovalg finnes -> bruk dem
    2) Ellers: 100 % skadegrad (default)
    """
    # 1) Brann-scenariovalg
    rate_from_brann = calc_skadegrad_from_brann_choices(rec)
    if rate_from_brann is not None:
        return clamp01(rate_from_brann)
    # default 100 % hvis ikke sats settes
    return 1.0

# manuell overstyring trumfer maskinell
def calc_skadegrad_effective(rec: Dict[str, Any]) -> float:
    if rec.get("skadegrad_manual_on"):
        return clamp01(float(rec.get("skadegrad_manual", 0.0)))
    return calc_skadegrad_machine(rec)


def calc_eml_effective(rec: Dict[str, Any]) -> int:
    try:
        si = float(rec.get("sum_forsikring", 0) or 0)
        return int(round(si * calc_skadegrad_effective(rec)))
    except Exception:
        return 0
 # --- SPLITT PD/BI
def classify_from_risikonrbeskrivelse(txt: str) -> str:
    """
    Returnerer 'BI' hvis teksten tyder på driftstap, ellers 'PD'.
    """
    t = (txt or "").strip().lower()
    if "driftstap" in t:
        return "BI"
    if "bygning" in t:
        return "PD"
    return "PD"

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


# --------------------------------------------------
# ----------- HTML-eksport -------------------------
# --------------------------------------------------
import base64
from pathlib import Path

def _img_to_data_uri(p: str) -> str:
    try:
        ext = Path(p).suffix.lower().lstrip(".") or "png"
        mime = f"image/{'jpeg' if ext in ('jpg','jpeg') else ('png' if ext=='png' else ext)}"
        b = Path(p).read_bytes()
        b64 = base64.b64encode(b).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""

def make_eml_html(sel_kumule: str, scenariobeskrivelse: str, meta: dict, dsc_df, include_links: bool = False) -> bytes:
    # kolonner og headers identisk med PDF (så totalsummer osv. stemmer)
    cols = [
        "adresse", "kundenavn", "kumulesone", "forsnr",
        "risikonr", "risikonrbeskrivelse", "dekning",
        "sum_forsikring", "skadegrad_eff_pct", "eml_preview", "eml_pd", "eml_bi"
    ]
    headers = [
        "Adresse", "Kunde", "Kumule", "Forsnr",
        "Risikonr", "Risikonr-beskrivelse", "Dekning",
        "SI", "Eff. sats", "EML", "EML PD", "EML BI"
    ]

    # beregn totaler
    try:
        tot_pd = int(dsc_df["eml_pd"].sum()) if "eml_pd" in dsc_df.columns else 0
        tot_bi = int(dsc_df["eml_bi"].sum()) if "eml_bi" in dsc_df.columns else 0
    except Exception:
        tot_pd = tot_bi = 0

    # kolonnevekter (gir mer plass til tekstkolonner). Summerer til 100.
    weights = [18, 14, 7, 7, 7, 18, 5, 8, 6, 10, 10, 10]
    # NB: weights-lengde må matche antall kolonner

    # bygg <colgroup> med prosentbaserte bredder (kun for eksport)
    colgroup = "\n".join([f'<col style="width:{w}%;"/>' for w in weights])

    # bygg rader
    def _fmt_num(x):
        try:
            return f"{int(round(float(x))):,}".replace(",", " ")
        except Exception:
            return str(x)

    def _fmt_pct(x):
        try:
            return f"{float(x):.2f}%"
        except Exception:
            return str(x)

    rows_html = []
    for _, row in dsc_df.iterrows():
        cells = []
        for c in cols:
            val = row.get(c, "")
            if c in ("sum_forsikring", "eml_preview", "eml_pd", "eml_bi"):
                cells.append(f"<td class='num'>{_fmt_num(val)}</td>")
            elif c == "skadegrad_eff_pct":
                cells.append(f"<td class='num'>{_fmt_pct(val)}</td>")
            else:
                # HTML-escape
                s = str(val).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                cells.append(f"<td>{s}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    # bilder (embed som base64 for portabilitet)
    images = meta.get("images", []) or []
    img_tags = []
    for p in images[:8]:
        uri = _img_to_data_uri(p)
        if uri:
            img_tags.append(f"<img src='{uri}' alt='bilde' />")

    # (valgfritt) sharepoint-lenker – IKKE med mindre include_links=True
    links_html = ""
    if include_links:
        sp_links = meta.get("sharepoint_links", []) or []
        if sp_links:
            items = []
            for u in sp_links:
                esc = str(u).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                items.append(f"<li><a href='{esc}'>{esc}</a></li>")
            links_html = f"<h2>SharePoint-lenker</h2><ul>{''.join(items)}</ul>"

    # CSS: tabell kun for eksport (fast layout, wrapping, sticky header, A4 marginer)
    # Tips: endre @page size til 'landscape' hvis du vil ha liggende utskrift.
    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EML – {sel_kumule}</title>
<style>
  :root {{
    --text: #111;
    --muted: #666;
    --bg: #fff;
    --line: #ddd;
    --headbg: #f0f2f6;
  }}
  @page {{
    size: A4 portrait;
    margin: 1.5cm;
  }}
  @media print {{
    .no-print {{ display: none !important; }}
    table {{ page-break-inside: auto; }}
    tr {{ page-break-inside: avoid; page-break-after: auto; }}
    h1, h2, h3 {{ page-break-after: avoid; }}
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    color: var(--text);
    background: var(--bg);
    line-height: 1.35;
    font-size: 11pt;
  }}
  h1 {{ margin: 0 0 .4rem 0; }}
  .meta {{ color: var(--muted); margin-bottom: .8rem; }}
  .summary {{
    background: #fafafa; border: 1px solid var(--line); padding: .6rem .8rem; margin: .6rem 0 1rem 0;
  }}
  .images {{ margin: .5rem 0 1rem 0; display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: .6rem; }}
  .images img {{ max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 6px; }}

  table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;      /* 👈 viktig: låser breddene fra <colgroup> */
    font-size: 10pt;
  }}
  col {{}} /* bredder fra <colgroup> */
  thead th {{
    background: var(--headbg);
    text-align: left;
    padding: 6px 6px;
    border: 1px solid var(--line);
    position: sticky;
    top: 0;
  }}
  tbody td {{
    padding: 6px 6px;
    border: 1px solid var(--line);
    vertical-align: top;
    word-wrap: break-word;
    overflow-wrap: anywhere;  /* bryt lange ord/url'er */
  }}
  td.num {{ text-align: right; }}
  .muted {{ color: var(--muted); }}
  pre {{
    white-space: pre-wrap;
    border: 1px solid var(--line);
    background: #fbfbfb;
    padding: .6rem .8rem;
    border-radius: 6px;
  }}
</style>
</head>
<body>
  <h1>EML-scenario – {sel_kumule}</h1>
  <div class="meta">
    <b>Beregnet av:</b> {meta.get('updated_by','')}&nbsp;&nbsp;
    <b>Sist oppdatert:</b> {meta.get('updated','')}
  </div>

  <h2>Scenariobeskrivelse</h2>
  <pre>{(scenariobeskrivelse or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")}</pre>

  <div class="summary">
    <b>Sum PD (EML):</b> {_fmt_nok(tot_pd)} &nbsp;&nbsp;
    <b>Sum BI (EML):</b> {_fmt_nok(tot_bi)}
  </div>

  {"<div class='images'>" + "".join(img_tags) + "</div>" if img_tags else ""}

  {links_html}

  <h2>Risikoer</h2>
  <table>
    <colgroup>
      {colgroup}
    </colgroup>
    <thead>
      <tr>{"".join(f"<th>{h}</th>" for h in headers)}</tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>

  <p class="muted" style="margin-top:.8rem;">Eksportert {now_iso()}</p>
</body>
</html>
"""
    return html.encode("utf-8")

# ----------------------------------------
# --- EKSPORT AV PDF - STRUKTURBYGGING ---
# ----------------------------------------
def make_eml_pdf(sel_kumule: str, scenariobeskrivelse: str, meta: dict, dsc_df, include_links: bool = False):
    
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.2*cm)
    styles = getSampleStyleSheet()
    H1, H2, N = styles["Heading1"], styles["Heading2"], styles["BodyText"]

    story = []

    # Header
    story.append(Paragraph(f"EML-scenario – {sel_kumule}", H1))
    updated_by = meta.get("updated_by", "") or ""
    updated = meta.get("updated", "") or ""
    story.append(Paragraph(f"Beregnet av: {updated_by}  &nbsp;&nbsp; Sist oppdatert: {updated}", N))
    story.append(Spacer(1, 6))

    # Scenariobeskrivelse
    if scenariobeskrivelse:
        story.append(Paragraph("Scenariobeskrivelse", H2))
        # Tillat enkel linebreak
        for line in str(scenariobeskrivelse).splitlines():
            story.append(Paragraph(line or "&nbsp;", N))
        story.append(Spacer(1, 8))

    # SharePoint-lenker
    if include_links:
        sp_links = meta.get("sharepoint_links", []) or []
        if sp_links:
            story.append(Paragraph("SharePoint-lenker", H2))
            for u in sp_links:
                safe = str(u).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                story.append(Paragraph(f"• <link href='{safe}' color='blue'>{safe}</link>", N))
            story.append(Spacer(1, 8))
    
    #sp_links = meta.get("sharepoint_links", []) or []
    #if sp_links:
    #    story.append(Paragraph("SharePoint-lenker", H2))
    #    for u in sp_links:
    #        # ReportLab støtter <link> i Paragraph
    #        safe = str(u).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    #        story.append(Paragraph(f"• <link href='{safe}' color='blue'>{safe}</link>", N))
    #    story.append(Spacer(1, 8))

    # Bilder (valg: vis opptil 3 først)
    imgs = meta.get("images", []) or []
    if imgs:
        story.append(Paragraph("Bilder", H2))
        for p in imgs[:3]:
            try:
                im = Image(p)
                # Skaler til bredde
                max_w = 16.5*cm
                iw, ih = im.wrap(0, 0)
                if iw > max_w:
                    scale = max_w / iw
                    im._restrictSize(max_w, ih*scale)
                story.append(im)
                story.append(Spacer(1, 6))
            except Exception:
                story.append(Paragraph(f"• {p}", N))
        story.append(Spacer(1, 6))

    # Summer PD/BI
    try:
        tot_pd = int(dsc_df["eml_pd"].sum()) if "eml_pd" in dsc_df.columns else 0
        tot_bi = int(dsc_df["eml_bi"].sum()) if "eml_bi" in dsc_df.columns else 0
    except Exception:
        tot_pd = tot_bi = 0

    story.append(Paragraph(
        f"<b>Sum PD (EML):</b> {_fmt_nok(tot_pd)} &nbsp;&nbsp; "
        f"<b>Sum BI (EML):</b> {_fmt_nok(tot_bi)}", N
    ))
    story.append(Spacer(1, 8))

    # Tabell med rader
    cols = [
        "adresse", "kundenavn", "kumulesone", "forsnr",
        "risikonr", "risikonrbeskrivelse", "dekning",
        "sum_forsikring", "skadegrad_eff_pct", "eml_preview", "eml_pd", "eml_bi"
    ]
    headers = [
        "Adresse", "Kunde", "Kumule", "Forsnr",
        "Risikonr", "Risikonr-beskrivelse", "Dekning",
        "SI", "Eff. sats", "EML", "EML PD", "EML BI"
    ]

    data = [headers]
    for _, row in dsc_df.iterrows():
        data.append([
            str(row.get("adresse","")),
            str(row.get("kundenavn","")),
            str(row.get("kumulesone","")),
            str(row.get("forsnr","")),
            str(row.get("risikonr","")),
            str(row.get("risikonrbeskrivelse","")),
            str(row.get("dekning","")),
            _fmt_nok(row.get("sum_forsikring", 0)),
            _fmt_pct(row.get("skadegrad_eff_pct", 0)),
            _fmt_nok(row.get("eml_preview", 0)),
            _fmt_nok(row.get("eml_pd", 0)),
            _fmt_nok(row.get("eml_bi", 0)),
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f0f2f6")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#111111")),
        ("ALIGN", (-5,1), (-1,-1), "RIGHT"),   # tall høyrejustert for de siste kolonnene
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#c8ccd4")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fbfbfd")]),
    ]))
    story.append(table)

    doc.build(story)
    buf.seek(0)
    return buf.read()

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
# Tekstfiltre
colf1, colf2, colf3 = st.columns(3)
with colf1:
    filt_kunde = st.text_input("Filter: Kunde inneholder", value="")
with colf2:
    filt_adresse = st.text_input("Filter: Adresse inneholder", value="")
with colf3:
    filt_kumule = st.text_input("Filter: Kumulesone inneholder", value="")
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
                # Bygg opp eksisterende tripletter for å kunne flagge nye risikoer i eksisterende kumule
                existing_triplets = set()
                for _k, _r in db.items():
                    if isinstance(_r, dict):
                        existing_triplets.add((
                            str(_r.get("kumulesone", "")),
                            str(_r.get("", "")),
                            str(_r.get("risikonr", "")),
                        ))

                imported = 0

               
                for _, row in df.iterrows():
                    kumule = str(row.get(col("kumulenr"), ""))
                    risiko = str(row.get(col("risikonr"), ""))
                    forsnr = str(row.get(col("forsnr"), ""))
                    risikonrbeskrivelse = str(row.get(col("risikonrbeskrivelse"), ""))
                    adresse = str(row.get(col("adresse"), ""))
                    kunde = str(row.get(col("kundenavn"), ""))
                    
                    # --- MIDLERTIDIG FIX GRUNNET MANGLENDE DEKNINGSINFORMASJON I IMPORT
                    risikonrbeskrivelse = str(row.get(col("risikonrbeskrivelse"), ""))
                    dekning = classify_from_risikonrbeskrivelse(risikonrbeskrivelse)

                    navn = f"{kumule}-{risiko}-{adresse}".strip("-")

                    try:
                        si = float(row.get(col("tariffsum"), 0) or 0)
                    except Exception:
                        si = 0.0

                    try:
                        eml_eff = float(row.get(col("EML sum"), 0) or 0)
                    except Exception:
                        eml_eff = 0.0

                    try:
                        rate_eff = float(row.get(col("EML sats"), 0) or 0)
                    except Exception:
                        rate_eff = 0.0

                    # --- DETEKTER "NY I KUMULE" + FIRST_SEEN (må skje FØR rec.update)
                    triplet = (kumule, forsnr, risiko)
                    is_new_here = triplet not in existing_triplets

                    old_first_seen = None
                    if navn in db and isinstance(db[navn], dict):
                        old_first_seen = db[navn].get("first_seen")
                    if rate_eff > 1.0:
                        rate_eff = rate_eff / 100.0
                    rate_eff = clamp01(rate_eff)
                    
                   

                    # --- OPPDATER / OPPRETT RECORD (rec) RETT FØR LAGRING
                    rec = db.get(navn, {})
                    rec.update({
                        "kumulesone": kumule,
                        "risikonr": risiko,
                        "forsnr": forsnr,
                        "risikonrbeskrivelse": risikonrbeskrivelse,
                        "dekning": dekning,
                        "adresse": adresse,
                        "kundenavn": kunde,
                        "sum_forsikring": si,
                        #"skadegrad": float(rate_eff),
                        "eml_effektiv": eml_eff,
                        
                        # eksisterende overstyrings-/visningsfelt bevares om de fantes
                        "skadegrad_manual_on": rec.get("skadegrad_manual_on", False),
                        "skadegrad_manual": rec.get("skadegrad_manual", 0.0),
                        "include": bool(rec.get("include", True)),
                        "scenario": rec.get("scenario", SCENARIOS[0]),
                        "updated": now_iso(),

                        # --- NYTT: flagg + first_seen
                        "first_seen": old_first_seen if old_first_seen else (now_iso() if is_new_here else None),
                        "is_new_in_kumule": bool(is_new_here),
                    })
                    db[navn] = rec
                    imported += 1

                    # Oppdater in-memory settet så vi ikke flagger samme triplet flere ganger i samme import
                    existing_triplets.add(triplet)

                ok, err = save_db_to_file(DB_FILENAME, db)
                if ok:
                    st.success(f"Importert {imported} rader til databasen.")
                    st.session_state.last_import_md5 = file_hash
                else:
                    st.error(f"Kunne ikke lagre DB: {err}")
    except Exception as e:
        st.error(f"Kunne ikke lese Excel: {e}")


    st.markdown("---")
    st.subheader("2) Filtrer og velg per kumulesone")


# Sikre at filtre finnes (default tomme)
filt_kunde = st.session_state.get("filt_kunde", "")
filt_adresse = st.session_state.get("filt_adresse", "")
filt_kumule = st.session_state.get("filt_kumule", "")

   
# Bygge visningstabell (db) i applikasjonen
try:
    import pandas as pd

    # Liten statusboks så vi ser at DB faktisk er fylt
    st.caption(f"🔎 Objekter i database: {len(db)}")

    records = []
    for key, r in db.items():
        if not isinstance(r, dict):
            continue
        if key.startswith("_"):  # f.eks. _scenario_meta
            continue
        si = float(r.get("sum_forsikring", 0) or 0)
        rate_eff = calc_skadegrad_effective(r)
        eml_eff  = int(round(si * rate_eff))
        
        records.append({
            "key": key,
            "forsnr": r.get("forsnr", ""),
            "risikonr": r.get("risikonr", ""),
            "risikonrbeskrivelse": r.get("risikonrbeskrivelse", ""),
            "dekning": r.get("dekning", ""),
            "kundenavn": r.get("kundenavn", ""),
            "adresse": r.get("adresse", ""),
            "postnummer": r.get("postnummer", ""),
            "kommune": r.get("kommune", ""),
            "kumulesone": r.get("kumulesone", ""),
            "scenario": r.get("scenario", ""),
            "include": bool(r.get("include", True)),
            "sum_forsikring": si,
            "skadegrad": float(rate_eff),
            "eml_effektiv": eml_eff,
            "kilde": r.get("kilde", ""),
            "updated": r.get("updated", "")
        })

    if records:
        df = pd.DataFrame.from_records(records)
    else:
        df = pd.DataFrame(
            columns=[
                "key","forsnr","risikonr","risikonrbeskrivelse","dekning","kundenavn","adresse","postnummer","kommune",
                "kumulesone","scenario","include","sum_forsikring","skadegrad","eml_effektiv",
                "kilde","updated"
            ]
        )#df = pd.DataFrame.from_records(records)
        
    # Toppfiltre: TSI / EML > 800 MNOK
    colfA, colfB = st.columns(2)
    f_tsi = colfA.toggle("Vis kun TSI > 800 MNOK", value=False)
    f_eml = colfB.toggle("Vis kun EML > 800 MNOK", value=False)
    
    df["sum_forsikring"] = pd.to_numeric(df["sum_forsikring"], errors="coerce")
    df["eml_effektiv"]   = pd.to_numeric(df["eml_effektiv"],   errors="coerce")

    # Kun inkluderte for kumule-summer
    grp_src = df[df["include"]]
    grp = (
        grp_src.groupby("kumulesone", dropna=False)
               .agg({"sum_forsikring": "sum", "eml_effektiv": "sum"})
               .fillna(0)
    )

    # Filter & sorteringspanel
    with st.expander("Filter & sortering", expanded=True):
        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
        f_kunde    = c1.text_input("Filtrer kundenavn", key="flt_kunde")
        f_adresse  = c2.text_input("Filtrer adresse", key="flt_adresse")
        f_kumule   = c3.selectbox("Kumulesone", options=["(alle)"] + sorted(df["kumulesone"].dropna().unique().tolist()), key="flt_kumule")
        f_scenario = c4.selectbox("Scenario", options=["(alle)"] + sorted(df["scenario"].dropna().unique().tolist()), key="flt_scenario")
        f_include  = c5.selectbox("Inkludert", options=["(alle)", True, False], key="flt_include")

    dff = df.copy()
    if f_kunde:
        dff = dff[dff["kundenavn"].str.contains(f_kunde, case=False, na=False)]
    if f_adresse:
        dff = dff[dff["adresse"].str.contains(f_adresse, case=False, na=False)]
    if f_kumule != "(alle)":
        dff = dff[dff["kumulesone"] == f_kumule]
    if f_scenario != "(alle)":
        dff = dff[dff["scenario"] == f_scenario]
    if f_include != "(alle)":
        dff = dff[dff["include"] == f_include]

    sortable_cols = ["kundenavn","adresse","kumulesone","sum_forsikring","forsnr","risikonr",
                     "scenario","include","kommune","postnummer","kilde","updated"]
    c6, c7 = st.columns([3, 2])
    sort_order = c6.multiselect("Sortér etter (rekkefølge gjelder)", options=sortable_cols,
                                default=["kumulesone","kundenavn"], key="sort_cols")
    asc_flags = []
    with c7:
        st.caption("Rekkefølge pr. kolonne")
        for col in sort_order:
            asc_flags.append(st.checkbox(f"↑ {col}", value=True, key=f"asc_{col}"))
    if sort_order:
        try:
            dff = dff.sort_values(by=sort_order, ascending=asc_flags, kind="mergesort")
        except Exception as e:
            st.warning(f"Klarte ikke sortere: {e}")

    # Vis tabell
   # --- ÉN tabell: sorterbar + redigerbar (include + scenario) ---
    from copy import deepcopy
    
    view_cols = [
        "forsnr","risikonr","risikonrbeskrivelse","dekning","kundenavn","adresse","postnummer","kommune",
        "kumulesone","scenario","include","sum_forsikring","skadegrad","eml_effektiv","kilde","updated","key"
    ]
    dff = dff[view_cols].reset_index(drop=True)
    
    edited = st.data_editor(
        dff,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "forsnr": "Forsnr",
            "risikonr": "Risikonr",
            "kundenavn": "Kundenavn",
            "adresse": "Adresse",
            "postnummer": "Postnr",
            "kommune": "Kommune",
            "kumulesone": "Kumulesone",
            "scenario": st.column_config.SelectboxColumn("Scenario", options=SCENARIOS),
            "include": st.column_config.CheckboxColumn("Inkludert"),
            "sum_forsikring": st.column_config.NumberColumn("Sum forsikring", format="%,.0f"),
            "skadegrad": st.column_config.NumberColumn("EML-rate", format="%.2f"),
            "eml_effektiv": st.column_config.NumberColumn("EML (effektiv)", format="%,.0f"),
            "kilde": "Kilde",
            "updated": "Oppdatert",
            "key": st.column_config.TextColumn("Key", help="Intern nøkkel i DB", width="small"),
        },
        disabled=[
            # alt låses bortsett fra include/scenario
            "forsnr","risikonr","kundenavn","adresse","postnummer","kommune",
            "kumulesone","sum_forsikring","skadegrad","eml_effektiv","kilde","updated","key"
        ],
        key="eml_editor",
    )
    
    left, right = st.columns(2)
    if left.button("✔️ Ta med ALLE i nåværende visning"):
        for k in edited["key"].tolist():
            if k in db: db[k]["include"] = True
        save_db_to_file(DB_FILENAME, db); 
        st.rerun()

    if right.button("🚫 Fjern ALLE i nåværende visning"):
        for k in edited["key"].tolist():
            if k in db: db[k]["include"] = False
        save_db_to_file(DB_FILENAME, db); 
        st.rerun()
    
    # Finn endringer (include/scenario) og persister
    changed_rows = []
    for i, row in edited.iterrows():
        k = row["key"]
        if k not in db: continue
        changed = False
        # include
        new_inc = bool(row["include"])
        if bool(db[k].get("include", False)) != new_inc:
            db[k]["include"] = new_inc; changed = True
        # scenario
        new_scen = row["scenario"] if row["scenario"] in SCENARIOS else db[k].get("scenario", SCENARIOS[0])
        if db[k].get("scenario", SCENARIOS[0]) != new_scen:
            db[k]["scenario"] = new_scen; changed = True
        if changed:
            db[k]["updated"] = now_iso()
            changed_rows.append(k)
        
    if changed_rows:
        save_db_to_file(DB_FILENAME, db)
   # st.success(f"Lagret endringer for {len(changed_rows)} rad(er).")

    # Nedlasting av csv-fil
    csv = dff.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Last ned filtrert/sortert CSV", data=csv, file_name="risiko_oversikt.csv", mime="text/csv")

    # --- TRINN 3: Én sorterbar/redigerbar tabell ---
    # Vi lar kun 'include' (avhuking) og 'scenario' være redigerbare.
    present_cols = [c for c in [
        "include","scenario","forsnr","risikonr","kundenavn","adresse",
        "postnummer","kommune","kumulesone","sum_forsikring",
        "skadegrad","eml_effektiv","updated","kilde","key"
    ] if c in dff.columns]
    
    col_cfg = {
        "include": st.column_config.CheckboxColumn("Inkludert"),
        "scenario": st.column_config.SelectboxColumn(
            "Scenario", options=SCENARIOS, required=True
        ),
        "sum_forsikring": st.column_config.NumberColumn("Sum forsikring", format="%,.0f"),
        "skadegrad": st.column_config.NumberColumn("EML-rate", format="%.2f"),
        "eml_effektiv": st.column_config.NumberColumn("EML (effektiv)", format="%,.0f"),
        "key": st.column_config.TextColumn("Key", help="Intern nøkkel i DB", width="small"),
    }
             
    
    if df.empty:
        st.info("Ingen data i databasen. Last opp Excel over.")
    else:
       # Filtrene (snake_case)
        m = pd.Series(True, index=df.index)
    if filt_kunde:
        m &= df["kundenavn"].astype(str).str.contains(filt_kunde, case=False, na=False)
    if filt_adresse:
        m &= df["adresse"].astype(str).str.contains(filt_adresse, case=False, na=False)
    if filt_kumule:
        m &= df["kumulesone"].astype(str).str.contains(filt_kumule, case=False, na=False)

               # st.success("Valg lagret for kumulesonen.")

    if PDF_BYTES_KEY not in st.session_state:
        st.session_state[_KEY] = None
    if PDF_READY_TS_KEY not in st.session_state:
        st.session_state[PDF_READY_TS_KEY] = None


except Exception as e:
    st.error(f"Visningsfeil: {e}")


# ----------------------------------------------------------
# 📈 EML-SCENARIO – Beregn per EN kumulesone + MANUELL overstyring
# ----------------------------------------------------------
#
#from datetime import date
#import pandas as pd
#import streamlit as st

import os
from urllib.parse import quote_plus
import pandas as pd

# Sørg for synlige feildetaljer
st.set_option("client.showErrorDetails", True)

# --- KONFIG for scenario "Brann" ---
BRANN_RISIKO_CHOICES = ["Høy", "Middels", "Lav"]
BRANN_SPREDNING_CHOICES = ["Stor", "Middels", "Liten"]
BRANN_slukke_CHOICES = ["Lang", "Middels", "Kort"]

def maps_url(adresse: str, kommune: str = "") -> str:
    q = adresse if not kommune else f"{adresse}, {kommune}"
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(q)}"

def _scenario_key(scen: str, kumule: str) -> str:
    return f"{scen}::{kumule}".strip()


# --- VISNING I APP ---
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

    # 2) Hente eksisterende meta og bilder
    meta_key = _scenario_key(scen, sel_kumule)
    if "_scenario_meta" not in db or not isinstance(db.get("_scenario_meta"), dict):
        db["_scenario_meta"] = {}
    current_meta = db["_scenario_meta"].get(meta_key, {}) if isinstance(db["_scenario_meta"].get(meta_key), dict) else {}
    existing_desc   = current_meta.get("beskrivelse", "")
    existing_images = current_meta.get("images", []) if isinstance(current_meta.get("images"), list) else []
    existing_sp_links = current_meta.get("sharepoint_links", []) or []

      
    # 3) Tabellvisning: én linje per risiko i valgt kumulesone (kun include=True)
    
    DEFAULT_RISIKO   = "Høy"
    DEFAULT_SPRED    = "Stor"
    DEFAULT_SLUKKE    = "Lang"
    
    rows = []
    for k, r in db.items():
        if not isinstance(r, dict):
            continue
        if str(r.get("kumulesone", "")) != sel_kumule:
            continue
        if not bool(r.get("include", True)):
            continue
    
        # Les eksisterende (med default til maks)
        brann_cfg = r.get("brann", {}) if isinstance(r.get("brann"), dict) else {}
        risiko_val   = brann_cfg.get("risiko_for_brann", DEFAULT_RISIKO)
        spredning_val = brann_cfg.get("spredning_av_brann", DEFAULT_SPRED)
        slukke_val    = brann_cfg.get("tid_for_slukkeinnsats", DEFAULT_SLUKKE)
    
        si = float(r.get("sum_forsikring", 0) or 0)
    
        # Auto-rate (maskin) fra valgene som står nå
        auto_rate = clamp01(BRANN_RISIKO_FAKTOR[risiko_val] * BRANN_SPREDNING_FAKTOR[spredning_val] * BRANN_SLUKKE_FAKTOR[slukke_val])
            
        manual_on  = bool(r.get("skadegrad_manual_on", False))
        manual_pct = float(r.get("skadegrad_manual", 0.0)) * 100.0
    
        eff_rate = clamp01(manual_pct/100.0) if manual_on else auto_rate

        addr = r.get("adresse", "") or ""
        komm = r.get("kommune", "") or ""
        dekning = (r.get("dekning") or classify_from_risikonrbeskrivelse(r.get("risikonrbeskrivelse",""))).upper()
        is_bi = (dekning == "BI")
        eml_total = int(round(si * eff_rate))
        eml_pd = 0 if is_bi else eml_total
        eml_bi = eml_total if is_bi else 0

        rows.append({
            "key": k,
            # Visningsfelt
            "adresse": addr,
            "kundenavn": r.get("kundenavn", ""),
            "kumulesone": r.get("kumulesone", ""),
            "forsnr": r.get("forsnr", ""),
            "risikonr": r.get("risikonr", ""),
            "risikonrbeskrivelse": r.get("risikonrbeskrivelse", ""),
            "sum_forsikring": si,
            # Splitt PD/BI
            "dekning": dekning,
            "eml_pd": eml_pd,
            "eml_bi": eml_bi,

            # Redigerbare scenariofelt
            "risiko_for_brann": risiko_val,
            "spredning_av_brann": spredning_val,
            "tid_for_slukkeinnsats": slukke_val,
            # Manuell overstyring
            "manuell_overstyring": manual_on,
            "manuell_sats_pct": round(manual_pct, 2),
            # Forklaring (lagres bare hvis oppgitt; kreves ved avvik fra default)
            "forklaring": r.get("forklaring_brann", ""),
            # Lesefelt
            "auto_sats_pct": round(auto_rate*100.0, 2),
            "skadegrad_eff_pct": round(eff_rate*100.0, 2),
            "eml_preview": int(round(si * eff_rate)),
            # Kartvisning
            "kart": maps_url(addr, komm),
            "updated": r.get("updated", "")
        })
       
    dsc = pd.DataFrame(rows)
    tot_pd = int(dsc["eml_pd"].sum()) if not dsc.empty else 0
    tot_bi = int(dsc["eml_bi"].sum()) if not dsc.empty else 0
    
    cPD, cBI = st.columns(2)
    cPD.metric("Sum PD (EML)", f"{tot_pd:,.0f} NOK".replace(",", " "))
    cBI.metric("Sum BI (EML)", f"{tot_bi:,.0f} NOK".replace(",", " "))

    st.write(f"**{len(dsc)} risiko(er) i kumulesone {sel_kumule}**")

    # --------------------------------------
    # --- PDF ----
    # --------------------------------------
    scenario_meta = db.get("_scenario_meta", {}).get(meta_key, {}) if isinstance(db.get("_scenario_meta"), dict) else {}
    
    desc_key = f"scenario_desc_{meta_key}" 
    scenariobeskrivelse = st.text_area(
        "Fritekstbeskrivelse",
        value=existing_desc,
        placeholder="Forutsetninger, tiltak, spesielle forhold, osv.",
        height=160,
        key=desc_key,   
    )
    # hent siste lagrede til eksport av PDF
    desc_for_pdf = st.session_state.get(desc_key) or scenario_meta.get("beskrivelse", existing_desc) or ""
  
    def _export_pdf():
       if not _has_reportlab():
            st.error(
                "Modulen 'reportlab' er ikke installert. "
                "Kjør `pip install reportlab` lokalt eller legg `reportlab>=4.0` i requirements.txt."
            )
            return
       if dsc is None or dsc.empty:
           st.warning("Ingen rader å eksportere i valgt kumule.")
           return
       with st.spinner("Genererer PDF..."):
           try:
               pdf_bytes = make_eml_pdf(sel_kumule, st.session_state.get(desc_key, "") or existing_desc, scenario_meta, dsc, include_links=False)
               st.session_state[PDF_BYTES_KEY] = pdf_bytes
               st.session_state[PDF_READY_TS_KEY] = now_iso()
           except Exception as e:
               st.exception(e)

    # Knapp som bare trigger generering og lagrer i session_state
    st.button("📄 Eksporter PDF for valgt kumule", type="secondary", on_click=_export_pdf)
    
    # Vis nedlastningsknapp når bytes er klare
    if st.session_state.get(PDF_BYTES_KEY):
        st.success(f"PDF klar ({st.session_state.get(PDF_READY_TS_KEY)}).")
        st.download_button(
            "⬇️ Last ned PDF",
            data=st.session_state[PDF_BYTES_KEY],
            file_name=f"EML_{sel_kumule}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    if st.button("⬇️ Eksporter HTML (print-vennlig)"):
        try:
            scenario_meta = db.get("_scenario_meta", {}).get(meta_key, {}) if isinstance(db.get("_scenario_meta"), dict) else {}
            html_bytes = make_eml_html(
                sel_kumule,
                st.session_state.get(desc_key, "") or existing_desc,
                scenario_meta,
                dsc,
                include_links=False   # behold False, slik du ønsket
            )
            st.download_button(
                "Last ned HTML",
                data=html_bytes,
                file_name=f"EML_{sel_kumule}.html",
                mime="text/html",
                use_container_width=True,
            )
            st.info("Åpne HTML-filen i nettleseren og velg *Skriv ut → Lagre som PDF* for PDF-versjon.")
        except Exception as e:
            st.error(f"Kunne ikke generere HTML: {e}")

 
    # if pdf_bytes:
    #     st.download_button(
    #         "⬇️ Last ned PDF",
    #         data=pdf_bytes,
    #         file_name=f"EML_{sel_kumule}.pdf",
    #         mime="application/pdf",
    #         use_container_width=True,
    #     )


# Skjemabygging
    with st.form("brann_scenario_form"):
        # ØVERST: meta for HELE scenarioet
        meta_col, img_col = st.columns([2, 1])
        top_c1, top_c2 = st.columns(2)
        with top_c1:
            eml_beregnet_dato = st.text_input("EML beregnet dato (ISO-8601)", value=date.today().isoformat())
        with top_c2:
            eml_beregnet_av = st.text_input("EML beregnet av", value=st.session_state.get("bruker", ""))

        with meta_col:
            st.markdown("**SharePoint-lenker (én per linje):**")
            sp_default = "\n".join(existing_sp_links) if existing_sp_links else ""
            sp_links_text = st.text_area(
                "Lenker", value=sp_default,
                placeholder="https://contoso.sharepoint.com/sites/.../Dok1.pdf\nhttps://contoso.sharepoint.com/sites/.../Mappe/",
                height=90
            )

        with img_col:
            st.markdown("### Bilder")
            uploads = st.file_uploader(
                "Last opp bilder (valgfritt)", type=["png", "jpg", "jpeg", "webp"],
                accept_multiple_files=True
            )
            # Forhåndsvis eksisterende
            if existing_images:
                st.caption("Lagrede bilder:")
                for p in existing_images[:4]:  # vis inntil 4
                    try:
                        st.image(p, use_column_width=True, caption=os.path.basename(p))
                    except Exception:
                        st.write(f"• {p}")

            if uploads:
                st.caption("Nyopplastede (forhåndsvisning):")
                for f in uploads:
                    st.image(f, use_column_width=True, caption=f.name)

        st.markdown("---")
        st.write(f"**{len(dsc)} risiko(er) i kumulesone {sel_kumule}**")

        edited_dsc = st.data_editor(
            dsc,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                # visning
                "adresse": st.column_config.TextColumn("Adresse", width="large"),
                "kundenavn": st.column_config.TextColumn("Kunde", width="medium"),
                "kumulesone": st.column_config.TextColumn("Kumule", width="small"),
                "forsnr": st.column_config.TextColumn("Forsikringsnr", width="small"),
                "risikonr": st.column_config.TextColumn("Risikonr", width="small"),
                "risikonrbeskrivelse": st.column_config.TextColumn("Risikonr-beskrivelse", width="large"),
                "sum_forsikring": st.column_config.NumberColumn("SI", format="%,.0f"),
                "dekning": st.column_config.TextColumn("Dekning (PD/BI)", width="small"),
                "eml_pd": st.column_config.NumberColumn("EML PD", format="%,.0f", disabled=True),
                "eml_bi": st.column_config.NumberColumn("EML BI", format="%,.0f", disabled=True),


                # scenario (redigerbare)
                "risiko_for_brann": st.column_config.SelectboxColumn("Risiko for brann", options=BRANN_RISIKO_CHOICES, required=True),
                "spredning_av_brann": st.column_config.SelectboxColumn("Spredning av brann", options=BRANN_SPREDNING_CHOICES, required=True),
                "tid_for_slukkeinnsats": st.column_config.SelectboxColumn("Tid før slukkeinnsats", options=BRANN_slukke_CHOICES, required=True),

                # manuell (redigerbare)
                "manuell_overstyring": st.column_config.CheckboxColumn("Manuell sats?"),
                "manuell_sats_pct": st.column_config.NumberColumn("Sats (%)", min_value=0.0, max_value=100.0, step=0.1, format="%.2f"),

                # forklaring (redigerbar)
                "forklaring": st.column_config.TextColumn("Forklaring ved avvik", width="large"),

                # lesefelt
                "auto_sats_pct": st.column_config.NumberColumn("Auto (%)", format="%.2f", disabled=True),
                "skadegrad_eff_pct": st.column_config.NumberColumn("Eff. (%)", format="%.2f", disabled=True),
                "eml_preview": st.column_config.NumberColumn("EML", format="%,.0f", disabled=True),

                # linker
                "kart": st.column_config.LinkColumn("Kart", help="Åpner Google Maps søk"),

                "updated": st.column_config.TextColumn("Oppdatert", width="small"),
                "key": st.column_config.TextColumn("Key", width="small"),
            },
            column_order=[
                "adresse","kundenavn","kumulesone","forsnr","risikonr","risikonrbeskrivelse","dekning",
                "sum_forsikring",
                "risiko_for_brann","spredning_av_brann","tid_for_slukkeinnsats",
                "manuell_overstyring","manuell_sats_pct","forklaring",
                "auto_sats_pct","skadegrad_eff_pct","eml_preview",
                "kart","updated","key"
            ],
            disabled=["adresse","kundenavn","kumulesone","forsnr","risikonr","risikonrbeskrivelse","dekning","sum_forsikring",
                      "auto_sats_pct","skadegrad_eff_pct","eml_preview","kart","updated","key"],
            key="brann_editor",
        )
    
        submitted = st.form_submit_button("💾 Lagre scenario (Brann) for kumulesonen")
    
    # 5) Persister ved submit (krav: forklaring hvis avvik fra default)
    
    # 
    # 
    if submitted:
        # lagre meta for kumule
        if "_scenario_meta" not in db or not isinstance(db.get("_scenario_meta"), dict):
            db["_scenario_meta"] = {}
        
        # lese eksisterende meta
        current_meta = db["_scenario_meta"].get(meta_key, {}) if isinstance(db["_scenario_meta"].get(meta_key), dict) else {}
        existing_images = current_meta.get("images", []) if isinstance(current_meta.get("images"), list) else []
        
        saved_paths = []
        if uploads:
            from pathlib import Path
            import uuid
            MEDIA_DIR = Path("eml_media")
            MEDIA_DIR.mkdir(exist_ok=True)
    
            for f in uploads:
                # finn filendelse
                ext = ""
                if "." in f.name:
                    ext = "." + f.name.rsplit(".", 1)[-1].lower()
                elif getattr(f, "type", None) in ("image/png", "image/jpeg", "image/webp"):
                    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[f.type]
                # lag filnavn og skriv til disk
                fname = f"{sel_kumule}_{uuid.uuid4().hex[:8]}{ext or ''}"
                out_path = MEDIA_DIR / fname
                out_path.write_bytes(f.getbuffer())
                saved_paths.append(str(out_path))

        # Slå sammen, dedupliser og begrens antall bilder (maks 8)
        new_images = existing_images + saved_paths
        seen = set(); images_dedup = []
        for p in new_images:
            if p not in seen:
                seen.add(p)
                images_dedup.append(p)
        images_dedup = images_dedup[:8]

        # Sharepoint-innliming
        sp_links_list = [
            ln.strip() for ln in (sp_links_text or "").splitlines()
            if ln.strip()
        ]
    
        # Lagre meta inkl. fritekst og bilder
        db["_scenario_meta"][meta_key] = {
            "scenario": scen,
            "kumulesone": sel_kumule,
            "beskrivelse": (st.session_state.get(desc_key, "") or "").strip(),
            "images": images_dedup,
            "sharepoint_links": sp_links_list,
            "updated": now_iso(),
            "updated_by": st.session_state.get("bruker", ""),
        }
        
    
        # Valider forklaring ved avvik
        avvik_uten_forklaring = []
        for _, row in edited_dsc.iterrows():
            avvik_fra_default = (
                (row["risiko_for_brann"] != DEFAULT_RISIKO) or
                (row["spredning_av_brann"] != DEFAULT_SPRED) or
                (row["tid_for_slukkeinnsats"] != DEFAULT_SLUKKE)
            )
            if avvik_fra_default and not str(row.get("forklaring", "")).strip():
                avvik_uten_forklaring.append(row["key"])
    
        if avvik_uten_forklaring:
            st.error(f"Forklaring mangler for {len(avvik_uten_forklaring)} rad(er) med avvik fra default.")
            st.stop()
    
        # Persister radene
        changed = 0
        for _, row in edited_dsc.iterrows():
            k = row["key"]
            if k not in db or not isinstance(db[k], dict):
                continue
    
            # 1) Brann-innstillinger (alltid lagres)
            db[k]["brann"] = {
                "risiko_for_brann": row["risiko_for_brann"],
                "spredning_av_brann": row["spredning_av_brann"],
                "tid_for_slukkeinnsats": row["tid_for_slukkeinnsats"],
                "updated": now_iso(),
            }
    
            # 2) Manuell overstyring
            on  = bool(row["manuell_overstyring"])
            pct = clamp01(float(row.get("manuell_sats_pct") or 0.0) / 100.0)
            db[k]["skadegrad_manual_on"] = on
            db[k]["skadegrad_manual"]    = pct

            # Visning av splitt PD/BI
            val = str(row.get("dekning", "")).upper()
            db[k]["dekning"] = "BI" if val == "BI" else "PD"
    
            # 3) Forklaring (lagre strippede strenger)
            db[k]["forklaring_brann"] = str(row.get("forklaring", "")).strip()
    
            # 4) Auto-rate som referanse
            auto_rate = BRANN_RISIKO_FAKTOR[row["risiko_for_brann"]] * BRANN_SPREDNING_FAKTOR[row["spredning_av_brann"]] * BRANN_SLUKKE_FAKTOR[row["tid_for_slukkeinnsats"]]
            db[k]["skadegrad_auto"] = clamp01(auto_rate)
    
            # 5) Stempel + EML metadata
            db[k]["eml_beregnet_dato"] = eml_beregnet_dato
            db[k]["eml_beregnet_av"]   = eml_beregnet_av
            db[k]["updated"]           = now_iso()
    
            changed += 1
    
        save_db_to_file(DB_FILENAME, db)
        st.success(f"Scenario 'Brann' lagret for {sel_kumule}. Endringer: {changed}.")
        st.rerun()

    # ---------- Skjema: Legg til risiko manuelt ----------
   # ---------- Skjema: Legg til risiko manuelt (lagrer på toppnivå i db) ----------


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
            "skadegrad_manual_on": False,
            "skadegrad_manual": 0.0,

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
