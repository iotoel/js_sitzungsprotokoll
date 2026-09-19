from __future__ import annotations

import json
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
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

FIXED_PROGRAM = [
    ("11:00", "Sitzung"),
    ("12:00", "Essen"),
    ("14:00", "Begrüssung"),
    ("16:58", "Tschi-ai-ai"),
    ("17:00", "Schluss"),
]

BLUE = colors.HexColor("#1F4E78")
LIGHT_BLUE = colors.HexColor("#D9EAF7")
PALE_BLUE = colors.HexColor("#EEF5FA")
BORDER = colors.HexColor("#7F8C8D")
GRAY = colors.HexColor("#666666")


def new_id() -> str:
    return uuid4().hex[:10]


def default_program() -> list[dict]:
    return [
        {"id": new_id(), "time": time, "title": title, "details": "", "fixed": True}
        for time, title in FIXED_PROGRAM
    ]


def default_state() -> dict:
    return {
        "sitzung_vom": date.today(),
        "thema_heute": "",
        "naechstes_datum": None,
        "naechstes_thema": "",
        "naechster_input_verantwortlich": "",
        "gedanken_naechster_input": "",
        "programmideen_naechster_nachmittag": "",
        "uebernaechstes_datum": None,
        "uebernaechster_input_verantwortlich": "",
        "program_blocks": default_program(),
        "diverses_cards": [],
    }


def initialize_state() -> None:
    defaults = default_state()
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    for index, _ in enumerate(TEILNEHMENDE):
        st.session_state.setdefault(f"anw_{index}", False)
    st.session_state.setdefault("active_draft", None)
    st.session_state.setdefault("flash", None)


def reset_form() -> None:
    defaults = default_state()
    for key, value in defaults.items():
        st.session_state[key] = value
    for index, _ in enumerate(TEILNEHMENDE):
        st.session_state[f"anw_{index}"] = False
    st.session_state["active_draft"] = None


def parse_date(value, fallback=None):
    if not value:
        return fallback
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return fallback


def esc(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9ÄÖÜäöü._-]+", "_", value.strip())
    return cleaned.strip("_.") or "Sitzungsprotokoll"


def sync_dynamic_widgets_to_state() -> None:
    for block in st.session_state.get("program_blocks", []):
        block_id = block["id"]
        if not block.get("fixed", False):
            block["time"] = st.session_state.get(f"program_time_{block_id}", block.get("time", ""))
            block["title"] = st.session_state.get(f"program_title_{block_id}", block.get("title", ""))
        block["details"] = st.session_state.get(f"program_details_{block_id}", block.get("details", ""))

    for card in st.session_state.get("diverses_cards", []):
        card_id = card["id"]
        card["title"] = st.session_state.get(f"div_title_{card_id}", card.get("title", ""))
        card["text"] = st.session_state.get(f"div_text_{card_id}", card.get("text", ""))


def add_program_block() -> None:
    sync_dynamic_widgets_to_state()
    blocks = st.session_state["program_blocks"]
    insert_at = max(len(blocks) - 2, 0)
    blocks.insert(insert_at, {"id": new_id(), "time": "", "title": "", "details": "", "fixed": False})


def remove_program_block(block_id: str) -> None:
    sync_dynamic_widgets_to_state()
    st.session_state["program_blocks"] = [
        block for block in st.session_state["program_blocks"] if block["id"] != block_id
    ]


def add_diverses_card() -> None:
    sync_dynamic_widgets_to_state()
    st.session_state["diverses_cards"].append(
        {"id": new_id(), "title": "", "text": ""}
    )


def remove_diverses_card(card_id: str) -> None:
    sync_dynamic_widgets_to_state()
    st.session_state["diverses_cards"] = [
        card for card in st.session_state["diverses_cards"] if card["id"] != card_id
    ]


def payload_from_state() -> dict:
    sync_dynamic_widgets_to_state()
    return {
        "version": 2,
        "gespeichert_am": datetime.now().isoformat(timespec="seconds"),
        "sitzung_vom": st.session_state["sitzung_vom"].isoformat() if st.session_state["sitzung_vom"] else "",
        "thema_heute": st.session_state["thema_heute"],
        "anwesend": {
            name: bool(st.session_state.get(f"anw_{index}", False))
            for index, name in enumerate(TEILNEHMENDE)
        },
        "naechstes_datum": st.session_state["naechstes_datum"].isoformat() if st.session_state["naechstes_datum"] else "",
        "naechstes_thema": st.session_state["naechstes_thema"],
        "naechster_input_verantwortlich": st.session_state["naechster_input_verantwortlich"],
        "gedanken_naechster_input": st.session_state["gedanken_naechster_input"],
        "programmideen_naechster_nachmittag": st.session_state["programmideen_naechster_nachmittag"],
        "program_blocks": st.session_state["program_blocks"],
        "uebernaechstes_datum": st.session_state["uebernaechstes_datum"].isoformat() if st.session_state["uebernaechstes_datum"] else "",
        "uebernaechster_input_verantwortlich": st.session_state["uebernaechster_input_verantwortlich"],
        "diverses_cards": st.session_state["diverses_cards"],
    }


def load_payload(payload: dict) -> None:
    st.session_state["sitzung_vom"] = parse_date(payload.get("sitzung_vom"), date.today())
    st.session_state["thema_heute"] = str(payload.get("thema_heute", payload.get("thema", "")))
    attendance = payload.get("anwesend", {})
    for index, name in enumerate(TEILNEHMENDE):
        st.session_state[f"anw_{index}"] = bool(attendance.get(name, False))
    st.session_state["naechstes_datum"] = parse_date(payload.get("naechstes_datum", payload.get("naechster_termin")), None)
    st.session_state["naechstes_thema"] = str(payload.get("naechstes_thema", ""))
    st.session_state["naechster_input_verantwortlich"] = str(payload.get("naechster_input_verantwortlich", payload.get("verantwortlich", "")))
    st.session_state["gedanken_naechster_input"] = str(payload.get("gedanken_naechster_input", payload.get("gedanken", "")))
    st.session_state["programmideen_naechster_nachmittag"] = str(payload.get("programmideen_naechster_nachmittag", payload.get("programmideen", "")))
    st.session_state["uebernaechstes_datum"] = parse_date(payload.get("uebernaechstes_datum"), None)
    st.session_state["uebernaechster_input_verantwortlich"] = str(payload.get("uebernaechster_input_verantwortlich", ""))

    blocks = payload.get("program_blocks")
    if not blocks:
        blocks = default_program()
        old_program = str(payload.get("programm_heute", ""))
        if old_program:
            blocks[0]["details"] = old_program
    for block in blocks:
        block.setdefault("id", new_id())
        block.setdefault("details", "")
        block.setdefault("fixed", False)
    st.session_state["program_blocks"] = blocks

    cards = payload.get("diverses_cards")
    if cards is None:
        old_diverses = str(payload.get("diverses", ""))
        cards = [{"id": new_id(), "title": "Diverses", "text": old_diverses}] if old_diverses else []
    for card in cards:
        card.setdefault("id", new_id())
        card.setdefault("title", "")
        card.setdefault("text", "")
    st.session_state["diverses_cards"] = cards

    # Remove widget values from the previously shown draft.
    for key in list(st.session_state.keys()):
        if key.startswith(("program_time_", "program_title_", "program_details_", "div_title_", "div_text_")):
            del st.session_state[key]


def draft_files() -> list[Path]:
    return sorted(DATA_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def read_draft(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def draft_label(path: Path) -> str:
    try:
        payload = read_draft(path)
        session_date = parse_date(payload.get("sitzung_vom"))
        date_text = session_date.strftime("%d.%m.%Y") if session_date else "Ohne Datum"
        topic = str(payload.get("thema_heute", payload.get("thema", ""))).strip()
        return f"{date_text} - {topic}" if topic else date_text
    except (OSError, json.JSONDecodeError):
        return path.stem


def unique_draft_path(payload: dict) -> Path:
    session_date = parse_date(payload.get("sitzung_vom"))
    date_part = session_date.isoformat() if session_date else "ohne-datum"
    topic = safe_filename(str(payload.get("thema_heute", "")))[:55]
    base = safe_filename(f"{date_part}_{topic}")
    candidate = DATA_DIR / f"{base}.json"
    counter = 2
    while candidate.exists():
        candidate = DATA_DIR / f"{base}_{counter}.json"
        counter += 1
    return candidate


def save_draft() -> Path:
    payload = payload_from_state()
    active = st.session_state.get("active_draft")
    path = Path(active) if active else unique_draft_path(payload)
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    temporary.replace(path)
    st.session_state["active_draft"] = str(path)
    return path


def add_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(12 * mm, 8 * mm, "Sitzungsprotokoll Jungschi Neuhof")
    canvas.drawRightString(198 * mm, 8 * mm, f"Seite {doc.page}")
    canvas.restoreState()


def p(text, style):
    return Paragraph(esc(text) if str(text).strip() else "&nbsp;", style)


def section_header(text: str, style, width=186 * mm):
    table = Table([[Paragraph(f"<b>{esc(text)}</b>", style)]], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, -1), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.7 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7 * mm),
    ]))
    return table


def content_box(title: str, content: str, body_style, small_style):
    data = [[Paragraph(f"<b>{esc(title)}</b>", small_style)], [p(content, body_style)]]
    table = Table(data, colWidths=[186 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
    ]))
    return table


def create_pdf(payload: dict) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=13 * mm,
        title="Sitzungsprotokoll Jungschi Neuhof",
        author="Jungschi Neuhof",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=15,
        leading=18, textColor=BLUE, alignment=TA_CENTER, spaceAfter=3 * mm,
    )
    body = ParagraphStyle(
        "body", parent=styles["BodyText"], fontName="Helvetica", fontSize=9,
        leading=11.5, alignment=TA_LEFT, allowWidows=0, allowOrphans=0,
    )
    small = ParagraphStyle("small", parent=body, fontSize=8.2, leading=10)
    tiny = ParagraphStyle("tiny", parent=body, fontSize=7.6, leading=9)

    session_date = parse_date(payload.get("sitzung_vom"))
    next_date = parse_date(payload.get("naechstes_datum"))
    overnext_date = parse_date(payload.get("uebernaechstes_datum"))
    date_today = session_date.strftime("%d.%m.%Y") if session_date else ""
    date_next = next_date.strftime("%d.%m.%Y") if next_date else ""
    date_overnext = overnext_date.strftime("%d.%m.%Y") if overnext_date else ""

    attendance = payload.get("anwesend", {})
    present_count = sum(1 for name in TEILNEHMENDE if attendance.get(name, False))
    attendee_rows = [[Paragraph(f"<b>Anwesend ({present_count}/{len(TEILNEHMENDE)})</b>", small)]]
    attendee_rows.extend([
        [Paragraph(f"{'[X]' if attendance.get(name, False) else '[ ]'}&nbsp;&nbsp;{esc(name)}", tiny)]
        for name in TEILNEHMENDE
    ])
    attendees = Table(attendee_rows, colWidths=[61 * mm])
    attendees.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.1 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1 * mm),
    ]))

    today_info = Table([
        [Paragraph("<b>Sitzung vom</b>", small), p(date_today, body)],
        [Paragraph("<b>Thema heute</b>", small), p(payload.get("thema_heute", ""), body)],
    ], colWidths=[30 * mm, 91 * mm])
    today_info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("TEXTCOLOR", (0, 0), (0, -1), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))

    top = Table([[today_info, attendees]], colWidths=[121 * mm, 61 * mm], hAlign="LEFT")
    top.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    story = [Paragraph("Sitzungsprotokoll", title_style), top, Spacer(1, 3 * mm)]

    story.append(section_header("Nächstes Mal", small))
    next_meta = Table([
        [Paragraph("<b>Datum</b>", small), p(date_next, body),
         Paragraph("<b>Thema</b>", small), p(payload.get("naechstes_thema", ""), body),
         Paragraph("<b>Input verantwortlich</b>", small), p(payload.get("naechster_input_verantwortlich", ""), body)]
    ], colWidths=[17 * mm, 27 * mm, 17 * mm, 52 * mm, 35 * mm, 38 * mm])
    next_meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), PALE_BLUE),
        ("BACKGROUND", (2, 0), (2, 0), PALE_BLUE),
        ("BACKGROUND", (4, 0), (4, 0), PALE_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.7 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7 * mm),
    ]))
    story.extend([
        next_meta,
        Spacer(1, 2.2 * mm),
        content_box("Gedanken zum nächsten Input", payload.get("gedanken_naechster_input", ""), body, small),
        Spacer(1, 2.2 * mm),
        content_box("Programmideen zum nächsten Nachmittag", payload.get("programmideen_naechster_nachmittag", ""), body, small),
        Spacer(1, 3 * mm),
        section_header("Programm heute", small),
    ])

    program_rows = [[Paragraph("<b>Zeit</b>", small), Paragraph("<b>Block</b>", small), Paragraph("<b>Notizen / Ablauf</b>", small)]]
    for block in payload.get("program_blocks", []):
        program_rows.append([
            p(block.get("time", ""), body),
            p(block.get("title", ""), body),
            p(block.get("details", ""), body),
        ])
    program_table = Table(program_rows, colWidths=[20 * mm, 48 * mm, 118 * mm], repeatRows=1)
    program_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
    ]))
    story.extend([program_table, Spacer(1, 3 * mm)])

    overnext = Table([
        [Paragraph("<b>Input übernächstes Mal</b>", small),
         Paragraph("<b>Datum</b>", small), p(date_overnext, body),
         Paragraph("<b>Verantwortlich</b>", small), p(payload.get("uebernaechster_input_verantwortlich", ""), body)]
    ], colWidths=[43 * mm, 17 * mm, 31 * mm, 29 * mm, 66 * mm])
    overnext.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_BLUE),
        ("BACKGROUND", (1, 0), (1, 0), PALE_BLUE),
        ("BACKGROUND", (3, 0), (3, 0), PALE_BLUE),
        ("TEXTCOLOR", (0, 0), (0, 0), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
    ]))
    story.extend([overnext, Spacer(1, 3 * mm), section_header("Diverses", small)])

    cards = payload.get("diverses_cards", [])
    if cards:
        for card in cards:
            card_title = card.get("title", "").strip() or "Diverses"
            story.extend([
                KeepTogether([content_box(card_title, card.get("text", ""), body, small)]),
                Spacer(1, 2 * mm),
            ])
    else:
        story.append(content_box("Diverses", "", body, small))

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    return output.getvalue()


initialize_state()

st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 1.2rem; padding-bottom: 3rem;}
h1, h2, h3 {color: #1F4E78;}
[data-testid="stSidebar"] {background: #f5f8fa;}
.section-line {border-top: 3px solid #1F4E78; margin: 1.6rem 0 1rem 0;}
.card-label {font-weight: 700; color: #1F4E78; margin-top: .4rem;}
</style>
""", unsafe_allow_html=True)

if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))

with st.sidebar:
    st.header("📁 Alte Sitzungen")
    if st.button("➕ Neue Sitzung", use_container_width=True):
        reset_form()
        st.rerun()

    files = draft_files()
    if files:
        options = {f"{draft_label(path)}  ·  {path.name}": path for path in files}
        selected = st.selectbox(
            "Gespeicherte Sitzung",
            options=list(options.keys()),
            index=None,
            placeholder="Sitzung auswählen",
        )
        if st.button("📂 Sitzung öffnen", disabled=selected is None, use_container_width=True):
            try:
                selected_path = options[selected]
                load_payload(read_draft(selected_path))
                st.session_state["active_draft"] = str(selected_path)
                st.session_state["flash"] = "Gespeicherte Sitzung wurde geöffnet."
                st.rerun()
            except (OSError, json.JSONDecodeError) as exc:
                st.error(f"Die Sitzung konnte nicht geöffnet werden: {exc}")
    else:
        st.caption("Noch keine gespeicherten Sitzungen vorhanden.")

    st.divider()
    if st.session_state.get("active_draft"):
        st.caption(f"Geöffnet: {draft_label(Path(st.session_state['active_draft']))}")
    else:
        st.caption("Neue, noch nicht gespeicherte Sitzung")

st.title("📝 Sitzungsprotokoll Jungschi Neuhof")
st.caption("Die Reihenfolge der Eingabe entspricht dem späteren Protokoll.")

st.subheader("1. Heutige Sitzung")
# Kompakte Zeile: Datumsfeld so klein wie möglich, Thema bis an den Rand.
today_date_col, today_topic_col = st.columns([1, 4.8], gap="small")
with today_date_col:
    st.date_input("Sitzung vom", key="sitzung_vom", format="DD.MM.YYYY")
with today_topic_col:
    st.text_input("Thema", key="thema_heute")

# Anwesenheit in zwei kompakten Reihen mit je vier Personen.
present_count = sum(
    bool(st.session_state.get(f"anw_{index}", False))
    for index in range(len(TEILNEHMENDE))
)
st.markdown(f"**Anwesend ({present_count}/{len(TEILNEHMENDE)})**")
for row_start in (0, 4):
    attendance_cols = st.columns(4, gap="small")
    for offset, column in enumerate(attendance_cols):
        index = row_start + offset
        with column:
            st.checkbox(TEILNEHMENDE[index], key=f"anw_{index}")

st.markdown('<div class="section-line"></div>', unsafe_allow_html=True)
st.subheader("2. Nächstes Mal")
next_col1, next_col2 = st.columns([1, 4.8], gap="small")
with next_col1:
    st.date_input("Datum nächstes Mal", key="naechstes_datum", format="DD.MM.YYYY")
    st.text_input("Thema nächstes Mal", key="naechstes_thema")
with next_col2:
    st.text_input("Inputverantwortliche Person nächstes Mal", key="naechster_input_verantwortlich")

st.text_area("Gedanken zum nächsten Input", key="gedanken_naechster_input", height=150)
st.text_area("Programmideen zum nächsten Nachmittag", key="programmideen_naechster_nachmittag", height=170)

st.markdown('<div class="section-line"></div>', unsafe_allow_html=True)
st.subheader("3. Heutiges Programm")
st.caption("Die festen Blöcke sind automatisch vorhanden. Zusätzliche Blöcke werden vor 16:58 eingefügt.")

for position, block in enumerate(st.session_state["program_blocks"]):
    block_id = block["id"]
    with st.container(border=True):
        if block.get("fixed", False):
            st.markdown(f"**{block['time']} {block['title']}**")
            st.text_area(
                "Notizen / Ablauf",
                value=block.get("details", ""),
                key=f"program_details_{block_id}",
                height=90,
                label_visibility="collapsed",
            )
        else:
            time_col, title_col, remove_col = st.columns([1, 3, 0.7])
            with time_col:
                st.text_input("Zeit", value=block.get("time", ""), key=f"program_time_{block_id}", placeholder="z.B. 15:00")
            with title_col:
                st.text_input("Titel des Blocks", value=block.get("title", ""), key=f"program_title_{block_id}")
            with remove_col:
                st.write("")
                st.write("")
                st.button("🗑️", key=f"remove_program_{block_id}", on_click=remove_program_block, args=(block_id,), help="Block löschen")
            st.text_area("Notizen / Ablauf", value=block.get("details", ""), key=f"program_details_{block_id}", height=100)

st.button("➕ Weiteren Programmblock hinzufügen", on_click=add_program_block, use_container_width=True)

st.subheader("4. Input übernächstes Mal")
over_col1, over_col2 = st.columns([1, 4.8], gap="small")
with over_col1:
    st.date_input("Datum übernächstes Mal", key="uebernaechstes_datum", format="DD.MM.YYYY")
with over_col2:
    st.text_input("Inputverantwortliche Person übernächstes Mal", key="uebernaechster_input_verantwortlich")

st.markdown('<div class="section-line"></div>', unsafe_allow_html=True)
st.subheader("5. Diverses")
if not st.session_state["diverses_cards"]:
    st.caption("Noch keine Karte vorhanden.")

for card in st.session_state["diverses_cards"]:
    card_id = card["id"]
    with st.container(border=True):
        title_col, delete_col = st.columns([6, 0.7])
        with title_col:
            st.text_input("Titel", value=card.get("title", ""), key=f"div_title_{card_id}", placeholder="Titel der Karte")
        with delete_col:
            st.write("")
            st.button("🗑️", key=f"remove_div_{card_id}", on_click=remove_diverses_card, args=(card_id,), help="Karte löschen")
        st.text_area("Inhalt", value=card.get("text", ""), key=f"div_text_{card_id}", height=120)

st.button("➕ Diverses-Karte hinzufügen", on_click=add_diverses_card, use_container_width=True)

st.divider()
action_save, action_pdf = st.columns(2)
with action_save:
    if st.button("💾 Entwurf speichern", type="primary", use_container_width=True):
        try:
            saved = save_draft()
            st.success(f"Entwurf gespeichert: {draft_label(saved)}")
        except OSError as exc:
            st.error(f"Der Entwurf konnte nicht gespeichert werden: {exc}")

with action_pdf:
    try:
        pdf_payload = payload_from_state()
        pdf_bytes = create_pdf(pdf_payload)
        session_date = parse_date(pdf_payload.get("sitzung_vom"))
        filename_date = session_date.strftime("%Y-%m-%d") if session_date else "ohne-Datum"
        st.download_button(
            "⬇️ PDF herunterladen",
            data=pdf_bytes,
            file_name=f"Sitzungsprotokoll_{filename_date}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as exc:
        st.error(f"Das PDF konnte nicht erstellt werden: {exc}")
