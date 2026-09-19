from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

st.set_page_config(page_title="Sitzungsprotokoll", page_icon="📝", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "daten"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BLUE = colors.HexColor("#1F4E78")
LIGHT_BLUE = colors.HexColor("#D9EAF7")
BORDER = colors.HexColor("#7F8C8D")

TEILNEHMENDE = [
    "Joel Aeschlimann",
    "Dario Jaggi",
    "Simon Lendenmann",
    "Colin Saluz",
    "Dylan Egli",
    "Sarai Wolfensberger",
    "Saphira Sommerhalder",
    "Chiara Ruosch",
]

FIELD_DEFAULTS = {
    "sitzung_vom": date.today(),
    "naechster_termin": None,
    "thema": "",
    "verantwortlich": "",
    "gedanken": "",
    "programmideen": "",
    "programm_heute": "",
    "diverses": "",
}


def esc(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def parse_date(value: object, fallback=None):
    if not value:
        return fallback
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return fallback


def safe_filename_part(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9ÄÖÜäöü._-]+", "_", value.strip())
    return value.strip("_.") or "Sitzungsprotokoll"


def draft_files() -> list[Path]:
    return sorted(DATA_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def read_draft(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_draft_atomic(path: Path, payload: dict) -> None:
    temp_path = path.with_suffix(".json.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
    temp_path.replace(path)


def initialize_state() -> None:
    for key, value in FIELD_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    for index, _ in enumerate(TEILNEHMENDE):
        st.session_state.setdefault(f"anw_{index}", False)
    st.session_state.setdefault("active_draft", None)
    st.session_state.setdefault("pdf_bytes", None)
    st.session_state.setdefault("pdf_name", None)


def current_payload() -> dict:
    sitzung = st.session_state.get("sitzung_vom")
    naechster = st.session_state.get("naechster_termin")
    return {
        "version": 1,
        "gespeichert_am": datetime.now().isoformat(timespec="seconds"),
        "sitzung_vom": sitzung.isoformat() if sitzung else "",
        "naechster_termin": naechster.isoformat() if naechster else "",
        "thema": st.session_state.get("thema", ""),
        "verantwortlich": st.session_state.get("verantwortlich", ""),
        "anwesend": {
            name: bool(st.session_state.get(f"anw_{index}", False))
            for index, name in enumerate(TEILNEHMENDE)
        },
        "gedanken": st.session_state.get("gedanken", ""),
        "programmideen": st.session_state.get("programmideen", ""),
        "programm_heute": st.session_state.get("programm_heute", ""),
        "diverses": st.session_state.get("diverses", ""),
    }


def load_payload_into_state(payload: dict) -> None:
    st.session_state["sitzung_vom"] = parse_date(payload.get("sitzung_vom"), date.today())
    st.session_state["naechster_termin"] = parse_date(payload.get("naechster_termin"), None)
    for key in ("thema", "verantwortlich", "gedanken", "programmideen", "programm_heute", "diverses"):
        st.session_state[key] = str(payload.get(key, ""))
    attendance = payload.get("anwesend", {})
    for index, name in enumerate(TEILNEHMENDE):
        st.session_state[f"anw_{index}"] = bool(attendance.get(name, False))
    st.session_state["pdf_bytes"] = None
    st.session_state["pdf_name"] = None


def reset_form() -> None:
    for key, value in FIELD_DEFAULTS.items():
        st.session_state[key] = value
    for index, _ in enumerate(TEILNEHMENDE):
        st.session_state[f"anw_{index}"] = False
    st.session_state["active_draft"] = None
    st.session_state["pdf_bytes"] = None
    st.session_state["pdf_name"] = None


def draft_display_name(path: Path) -> str:
    try:
        payload = read_draft(path)
        meeting_date = parse_date(payload.get("sitzung_vom"))
        date_text = meeting_date.strftime("%d.%m.%Y") if meeting_date else "Ohne Datum"
        topic = str(payload.get("thema", "")).strip()
        return f"{date_text} - {topic}" if topic else date_text
    except (OSError, json.JSONDecodeError):
        return path.stem


def default_draft_path(payload: dict) -> Path:
    meeting_date = parse_date(payload.get("sitzung_vom"))
    date_part = meeting_date.isoformat() if meeting_date else "ohne-datum"
    topic_part = safe_filename_part(str(payload.get("thema", "")))[:50]
    base = safe_filename_part(f"{date_part}_{topic_part}")
    candidate = DATA_DIR / f"{base}.json"
    counter = 2
    while candidate.exists():
        candidate = DATA_DIR / f"{base}_{counter}.json"
        counter += 1
    return candidate


def save_current_draft(save_as_new: bool = False) -> Path:
    payload = current_payload()
    active = st.session_state.get("active_draft")
    if active and not save_as_new:
        path = Path(active)
    else:
        path = default_draft_path(payload)
    write_draft_atomic(path, payload)
    st.session_state["active_draft"] = str(path)
    return path


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(18 * mm, 10 * mm, "Sitzungsprotokoll Jungschi Neuhof")
    canvas.drawRightString(192 * mm, 10 * mm, f"Seite {doc.page}")
    canvas.restoreState()


def section_box(title: str, content: str, body_style: ParagraphStyle, min_height_mm: float):
    heading = Paragraph(f"<b>{esc(title)}</b>", body_style)
    body = Paragraph(esc(content) if content.strip() else "&nbsp;", body_style)
    table = Table([[heading], [body]], colWidths=[174 * mm], rowHeights=[8 * mm, min_height_mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    return table


def create_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=16 * mm,
        title="Sitzungsprotokoll Jungschi Neuhof",
        author="Streamlit Sitzungsprotokoll",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=BLUE, alignment=TA_CENTER, spaceAfter=5 * mm,
    )
    body = ParagraphStyle(
        "BodyCustom", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=10, leading=14, textColor=colors.black, alignment=TA_LEFT,
    )
    small = ParagraphStyle("SmallCustom", parent=body, fontSize=9, leading=12)
    story = [Paragraph("Sitzungsprotokoll", title_style)]
    meeting_date = parse_date(data.get("sitzung_vom"))
    next_date = parse_date(data.get("naechster_termin"))
    meeting_text = meeting_date.strftime("%d.%m.%Y") if meeting_date else ""
    next_text = next_date.strftime("%d.%m.%Y") if next_date else ""
    meta = Table([
        [Paragraph("<b>Sitzung vom</b>", small), Paragraph(esc(meeting_text), body),
         Paragraph("<b>Thema</b>", small), Paragraph(esc(data.get("thema", "")), body)],
        [Paragraph("<b>Nächster Jungschi-NaMi</b><br/><font size='8'>(Input &amp; Programm)</font>", small),
         Paragraph(esc(next_text), body), Paragraph("<b>Verantwortlich</b>", small),
         Paragraph(esc(data.get("verantwortlich", "")), body)],
    ], colWidths=[34 * mm, 51 * mm, 31 * mm, 58 * mm])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE), ("BACKGROUND", (2, 0), (2, -1), LIGHT_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    story.extend([meta, Spacer(1, 5 * mm)])
    attendance = data.get("anwesend", {})
    present = [name for name in TEILNEHMENDE if attendance.get(name, False)]
    rows = []
    for i in range(0, len(TEILNEHMENDE), 2):
        row = []
        for name in TEILNEHMENDE[i:i + 2]:
            row.append(Paragraph(f"{'[X]' if name in present else '[ ]'}&nbsp;&nbsp;{esc(name)}", small))
        if len(row) == 1:
            row.append(Paragraph("", small))
        rows.append(row)
    attendee_heading = Table([[Paragraph(f"<b>Anwesend ({len(present)} / {len(TEILNEHMENDE)})</b>", body)]], colWidths=[174 * mm])
    attendee_heading.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE), ("TEXTCOLOR", (0, 0), (-1, -1), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    attendees = Table(rows, colWidths=[87 * mm, 87 * mm])
    attendees.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D6D8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
    ]))
    story.extend([KeepTogether([attendee_heading, attendees]), Spacer(1, 5 * mm)])
    story.extend([
        section_box("Gedanken", str(data.get("gedanken", "")), body, 25), Spacer(1, 4 * mm),
        section_box("Programmideen", str(data.get("programmideen", "")), body, 39), PageBreak(),
        section_box("Programm heute", str(data.get("programm_heute", "")), body, 72), Spacer(1, 5 * mm),
        section_box("Diverses", str(data.get("diverses", "")), body, 72),
    ])
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return buffer.getvalue()


initialize_state()

st.markdown("""
<style>
.block-container {max-width: 1250px; padding-top: 1.4rem; padding-bottom: 3rem;}
h1, h2, h3 {color: #1F4E78;}
[data-testid="stSidebar"] {background: #f5f8fa;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("📁 Protokolle")
    if st.button("➕ Neues Protokoll", use_container_width=True):
        reset_form()
        st.rerun()

    files = draft_files()
    if files:
        labels = {draft_display_name(path): path for path in files}
        selected_label = st.selectbox("Gespeichertes Protokoll", list(labels.keys()), index=None, placeholder="Protokoll auswählen")
        selected_path = labels.get(selected_label) if selected_label else None
        col_load, col_delete = st.columns(2)
        with col_load:
            if st.button("📂 Laden", disabled=selected_path is None, use_container_width=True):
                try:
                    payload = read_draft(selected_path)
                    load_payload_into_state(payload)
                    st.session_state["active_draft"] = str(selected_path)
                    st.success("Protokoll geladen.")
                    st.rerun()
                except (OSError, json.JSONDecodeError) as exc:
                    st.error(f"Protokoll konnte nicht geladen werden: {exc}")
        with col_delete:
            if st.button("🗑️ Löschen", disabled=selected_path is None, use_container_width=True):
                try:
                    selected_path.unlink(missing_ok=True)
                    if st.session_state.get("active_draft") == str(selected_path):
                        reset_form()
                    st.success("Protokoll gelöscht.")
                    st.rerun()
                except OSError as exc:
                    st.error(f"Protokoll konnte nicht gelöscht werden: {exc}")
    else:
        st.caption("Noch keine Entwürfe gespeichert.")

    st.divider()
    active = st.session_state.get("active_draft")
    if active:
        st.caption(f"Aktuell: {draft_display_name(Path(active))}")
    else:
        st.caption("Aktuell: neues, noch nicht gespeichertes Protokoll")

st.title("📝 Sitzungsprotokoll Jungschi Neuhof")
st.caption("Entwurf speichern, später wieder laden und weiterbearbeiten oder als PDF ausgeben.")

st.subheader("Sitzung")
c1, c2 = st.columns(2)
with c1:
    st.date_input("Sitzung vom", key="sitzung_vom", format="DD.MM.YYYY")
    st.date_input("Nächster Jungschi-NaMi (Input & Programm)", key="naechster_termin", value=None, format="DD.MM.YYYY")
with c2:
    st.text_input("Thema", key="thema")
    st.text_input("Verantwortlich", key="verantwortlich")

st.subheader("Anwesend")
attendance_cols = st.columns(2)
for idx, name in enumerate(TEILNEHMENDE):
    with attendance_cols[idx % 2]:
        st.checkbox(name, key=f"anw_{idx}")

st.subheader("Inhalte")
st.text_area("Gedanken", key="gedanken", height=130)
st.text_area("Programmideen", key="programmideen", height=180)
st.text_area("Programm heute", key="programm_heute", height=220)
st.text_area("Diverses", key="diverses", height=180)

st.divider()
button_save, button_save_as, button_pdf = st.columns(3)
with button_save:
    if st.button("💾 Entwurf speichern", type="primary", use_container_width=True):
        try:
            saved_path = save_current_draft(save_as_new=False)
            st.success(f"Gespeichert: {draft_display_name(saved_path)}")
        except OSError as exc:
            st.error(f"Speichern fehlgeschlagen: {exc}")
with button_save_as:
    if st.button("📑 Als neuen Entwurf speichern", use_container_width=True):
        try:
            saved_path = save_current_draft(save_as_new=True)
            st.success(f"Neuer Entwurf gespeichert: {draft_display_name(saved_path)}")
        except OSError as exc:
            st.error(f"Speichern fehlgeschlagen: {exc}")
with button_pdf:
    if st.button("📄 PDF erstellen", use_container_width=True):
        payload = current_payload()
        st.session_state["pdf_bytes"] = create_pdf(payload)
        meeting_date = parse_date(payload.get("sitzung_vom"))
        date_part = meeting_date.strftime("%Y-%m-%d") if meeting_date else "ohne-Datum"
        st.session_state["pdf_name"] = f"Sitzungsprotokoll_{date_part}.pdf"
        st.success("PDF wurde erstellt.")

if st.session_state.get("pdf_bytes"):
    st.divider()
    st.subheader("PDF-Vorschau")
    st.download_button(
        "⬇️ PDF herunterladen",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state["pdf_name"],
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
    encoded = base64.b64encode(st.session_state["pdf_bytes"]).decode("ascii")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{encoded}" width="100%" height="850" '
        'style="border:1px solid #d7e0e7;border-radius:8px"></iframe>',
        unsafe_allow_html=True,
    )
    st.info("Zum Drucken das PDF herunterladen oder das Drucksymbol des PDF-Viewers verwenden.")
