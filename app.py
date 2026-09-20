"""Sitzungsprotokoll Jungschi Neuhof.

Streamlit-App zum Erfassen von Sitzungsprotokollen. Erlaubt das Ausfüllen
eines Formulars, das Speichern als JSON-Entwurf auf der Festplatte sowie
den Export als formatiertes PDF.

Der Code ist in folgende Abschnitte gegliedert:
    1. Konfiguration & Konstanten
    2. Allgemeine Hilfsfunktionen
    3. Session-State: Standardwerte & Verwaltung
    4. Synchronisation der dynamischen Formular-Widgets
    5. Umwandlung Session-State <-> Speicher-Payload (JSON)
    6. Entwürfe auf der Festplatte (lesen/schreiben/auflisten)
    7. PDF-Erstellung
    8. Seitenaufbau (Streamlit-UI)
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
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

# =============================================================================
# 1. Konfiguration & Konstanten
# =============================================================================

st.set_page_config(page_title="Sitzungsprotokoll", page_icon="📝", layout="wide")

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "daten"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Feste Liste der Teilnehmenden, wird für die Anwesenheitsliste verwendet.
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

# Feste Programmpunkte, die bei jeder neuen Sitzung automatisch angelegt
# werden (Uhrzeit, Titel). Zusätzliche, frei editierbare Punkte werden
# vom Formular dazwischen eingefügt (siehe add_program_block()).
FIXED_PROGRAM = [
    ("11:00", "Sitzung"),
    ("12:00", "Essen"),
    ("14:00", "Begrüssung"),
    ("16:58", "Tschi-ai-ai"),
    ("17:00", "Schluss"),
]

# Farbpalette, sowohl für das UI-CSS als auch für das PDF verwendet.
BLUE = colors.HexColor("#1F4E78")
TODAY = colors.HexColor("#D9EAF7")
TODAY_DARK = colors.HexColor("#1F4E78")
NEXT = colors.HexColor("#E4F2DF")
NEXT_DARK = colors.HexColor("#376B2B")
OVERNEXT = colors.HexColor("#FFF0D5")
OVERNEXT_DARK = colors.HexColor("#8A5600")
MISC = colors.HexColor("#EEE1F6")
MISC_DARK = colors.HexColor("#67417E")
LIGHT_BLUE = TODAY
PALE_BLUE = colors.HexColor("#F5F7F9")
BORDER = colors.HexColor("#7F8C8D")
GRAY = colors.HexColor("#666666")


# =============================================================================
# 2. Allgemeine Hilfsfunktionen
# =============================================================================


def new_id() -> str:
    """Erzeugt eine kurze, zufällige ID für Programmpunkte/Diverses-Karten."""
    return uuid4().hex[:10]


def parse_date(value, fallback=None):
    """Wandelt einen gespeicherten oder eingegebenen Wert in ein date-Objekt um.

    Akzeptiert bereits vorhandene date-Objekte oder ISO-Strings (wie sie
    beim Speichern in die JSON-Datei geschrieben werden). Bei leeren oder
    ungültigen Werten wird `fallback` zurückgegeben.
    """
    if not value:
        return fallback
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return fallback


def esc(value: object) -> str:
    """Escaped Text für die Verwendung in ReportLab-Paragraphen (HTML-ähnlich)."""
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def safe_filename(value: str) -> str:
    """Macht aus einem beliebigen Text einen sicheren Dateinamen-Bestandteil."""
    cleaned = re.sub(r"[^A-Za-z0-9ÄÖÜäöü._-]+", "_", value.strip())
    return cleaned.strip("_.") or "Sitzungsprotokoll"


# =============================================================================
# 3. Session-State: Standardwerte & Verwaltung
# =============================================================================


def default_program() -> list[dict]:
    """Erzeugt die Liste der festen Programmpunkte für eine neue Sitzung."""
    return [
        {"id": new_id(), "time": time, "title": title, "details": "", "fixed": True}
        for time, title in FIXED_PROGRAM
    ]


def default_state() -> dict:
    """Erzeugt die Standardwerte für eine leere/neue Sitzung."""
    today = date.today()
    return {
        "sitzung_vom": today,
        "naechstes_datum": today + timedelta(weeks=2),
        "uebernaechstes_datum": today + timedelta(weeks=4),
        "thema_heute": "",
        "naechstes_thema": "",
        "naechster_input_verantwortlich": "",
        "gedanken_naechster_input": "",
        "programmideen_naechster_nachmittag": "",
        "programm_heute": "",
        "uebernaechster_input_thema": "",
        "uebernaechster_input_verantwortlich": "",
        "program_blocks": default_program(),
        "diverses_cards": [],
    }


def initialize_state() -> None:
    """Befüllt den Session-State beim ersten Aufruf mit Standardwerten.

    Bestehende Werte (z. B. nach einem Rerun) werden nicht überschrieben.
    """
    defaults = default_state()
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    for index, _ in enumerate(TEILNEHMENDE):
        st.session_state.setdefault(f"anw_{index}", False)
    st.session_state.setdefault("active_draft", None)
    st.session_state.setdefault("flash", None)


def reset_form() -> None:
    """Setzt das Formular auf eine leere, neue Sitzung zurück."""
    defaults = default_state()
    for key, value in defaults.items():
        st.session_state[key] = value
    for index, _ in enumerate(TEILNEHMENDE):
        st.session_state[f"anw_{index}"] = False
    st.session_state["active_draft"] = None


# =============================================================================
# 4. Synchronisation der dynamischen Formular-Widgets
# =============================================================================
#
# Programmpunkte und Diverses-Karten werden dynamisch gerendert (eine Zeile
# pro Eintrag, mit einem eigenen Widget-Key je Feld). Bevor Einträge
# hinzugefügt, entfernt oder gespeichert werden, müssen die aktuellen
# Widget-Werte zurück in die "echten" Datenstrukturen im Session-State
# geschrieben werden - das übernimmt sync_dynamic_widgets_to_state().


def sync_dynamic_widgets_to_state() -> None:
    """Überträgt die aktuellen Werte der dynamischen Widgets in den State."""
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
    """Fügt einen neuen, frei editierbaren Programmpunkt vor den letzten zwei ein."""
    sync_dynamic_widgets_to_state()
    blocks = st.session_state["program_blocks"]
    insert_at = max(len(blocks) - 2, 0)
    blocks.insert(insert_at, {"id": new_id(), "time": "", "title": "", "details": "", "fixed": False})


def remove_program_block(block_id: str) -> None:
    """Entfernt einen Programmpunkt anhand seiner ID."""
    sync_dynamic_widgets_to_state()
    st.session_state["program_blocks"] = [
        block for block in st.session_state["program_blocks"] if block["id"] != block_id
    ]


def add_diverses_card() -> None:
    """Fügt eine neue, leere Diverses-Karte hinzu."""
    sync_dynamic_widgets_to_state()
    st.session_state["diverses_cards"].append({"id": new_id(), "title": "", "text": ""})


def remove_diverses_card(card_id: str) -> None:
    """Entfernt eine Diverses-Karte anhand ihrer ID."""
    sync_dynamic_widgets_to_state()
    st.session_state["diverses_cards"] = [
        card for card in st.session_state["diverses_cards"] if card["id"] != card_id
    ]


# =============================================================================
# 5. Umwandlung Session-State <-> Speicher-Payload (JSON)
# =============================================================================


def payload_from_state() -> dict:
    """Baut das JSON-fähige Payload-Dict aus dem aktuellen Session-State."""
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
        "programm_heute": st.session_state["programm_heute"],
        "program_blocks": st.session_state["program_blocks"],
        "uebernaechstes_datum": st.session_state["uebernaechstes_datum"].isoformat() if st.session_state["uebernaechstes_datum"] else "",
        "uebernaechster_input_verantwortlich": st.session_state["uebernaechster_input_verantwortlich"],
        "diverses_cards": st.session_state["diverses_cards"],
    }


def load_payload(payload: dict) -> None:
    """Übernimmt ein gespeichertes Payload-Dict in den Session-State.

    Unterstützt sowohl das aktuelle Format als auch ältere Feldnamen
    (z. B. "thema" statt "thema_heute"), damit alte Entwürfe weiterhin
    geöffnet werden können.
    """
    st.session_state["sitzung_vom"] = parse_date(payload.get("sitzung_vom"), date.today())
    st.session_state["thema_heute"] = str(payload.get("thema_heute", payload.get("thema", "")))

    attendance = payload.get("anwesend", {})
    for index, name in enumerate(TEILNEHMENDE):
        st.session_state[f"anw_{index}"] = bool(attendance.get(name, False))

    st.session_state["naechstes_datum"] = parse_date(
        payload.get("naechstes_datum", payload.get("naechster_termin")), None
    )
    st.session_state["naechstes_thema"] = str(payload.get("naechstes_thema", ""))
    st.session_state["naechster_input_verantwortlich"] = str(
        payload.get("naechster_input_verantwortlich", payload.get("verantwortlich", ""))
    )
    st.session_state["gedanken_naechster_input"] = str(
        payload.get("gedanken_naechster_input", payload.get("gedanken", ""))
    )
    st.session_state["programmideen_naechster_nachmittag"] = str(
        payload.get("programmideen_naechster_nachmittag", payload.get("programmideen", ""))
    )
    st.session_state["programm_heute"] = str(payload.get("programm_heute", ""))
    st.session_state["uebernaechstes_datum"] = parse_date(payload.get("uebernaechstes_datum"), None)
    st.session_state["uebernaechster_input_verantwortlich"] = str(
        payload.get("uebernaechster_input_verantwortlich", "")
    )

    blocks = payload.get("program_blocks") or default_program()
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

    # Alte Widget-Werte des zuvor angezeigten Entwurfs entfernen, damit die
    # neu geladenen program_blocks/diverses_cards nicht durch verwaiste
    # Widget-Keys überschrieben werden.
    for key in list(st.session_state.keys()):
        if key.startswith(("program_time_", "program_title_", "program_details_", "div_title_", "div_text_")):
            del st.session_state[key]


# =============================================================================
# 6. Entwürfe auf der Festplatte
# =============================================================================


def draft_files() -> list[Path]:
    """Alle gespeicherten Entwürfe, neuste zuerst."""
    return sorted(DATA_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def read_draft(path: Path) -> dict:
    """Liest einen einzelnen Entwurf von der Festplatte."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def draft_label(path: Path) -> str:
    """Erzeugt eine lesbare Bezeichnung ("Datum - Thema") für einen Entwurf."""
    try:
        payload = read_draft(path)
        session_date = parse_date(payload.get("sitzung_vom"))
        date_text = session_date.strftime("%d.%m.%Y") if session_date else "Ohne Datum"
        topic = str(payload.get("thema_heute", payload.get("thema", ""))).strip()
        return f"{date_text} - {topic}" if topic else date_text
    except (OSError, json.JSONDecodeError):
        return path.stem


def unique_draft_path(payload: dict) -> Path:
    """Bestimmt einen noch nicht belegten Dateinamen für einen neuen Entwurf."""
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
    """Speichert den aktuellen Formularstand als JSON-Entwurf.

    Ist bereits ein Entwurf geöffnet ("active_draft"), wird dieser
    überschrieben, sonst wird ein neuer Dateiname vergeben. Das Schreiben
    erfolgt über eine temporäre Datei, um bei Fehlern keine kaputte Datei
    zurückzulassen.
    """
    payload = payload_from_state()
    active = st.session_state.get("active_draft")
    path = Path(active) if active else unique_draft_path(payload)

    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    temporary.replace(path)

    st.session_state["active_draft"] = str(path)
    return path


# =============================================================================
# 7. PDF-Erstellung
# =============================================================================


def add_footer(canvas, doc) -> None:
    """Zeichnet die Fusszeile (Titel links, Seitenzahl rechts) auf jede Seite."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(12 * mm, 8 * mm, "Sitzungsprotokoll Jungschi Neuhof")
    canvas.drawRightString(198 * mm, 8 * mm, f"Seite {doc.page}")
    canvas.restoreState()


def p(text, style) -> Paragraph:
    """Erstellt einen Paragraph; leerer Text wird durch ein geschütztes Leerzeichen ersetzt."""
    return Paragraph(esc(text) if str(text).strip() else "&nbsp;", style)


def section_header(text: str, style, width=186 * mm, fill=LIGHT_BLUE, text_color=BLUE) -> Table:
    """Ein farbig hinterlegtes, breites Balken-Label (z. B. "Nächstes Mal")."""
    table = Table([[Paragraph(f"<b>{esc(text)}</b>", style)]], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("TEXTCOLOR", (0, 0), (-1, -1), text_color),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.7 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7 * mm),
    ]))
    return table


def content_box(title: str, content: str, body_style, small_style, fill=PALE_BLUE, text_color=BLUE) -> Table:
    """Eine Box mit farbigem Titel-Kopf und Freitext darunter (z. B. "Diverses")."""
    data = [[Paragraph(f"<b>{esc(title)}</b>", small_style)], [p(content, body_style)]]
    table = Table(data, colWidths=[186 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), fill),
        ("TEXTCOLOR", (0, 0), (-1, 0), text_color),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
    ]))
    return table


def build_pdf_styles() -> dict[str, ParagraphStyle]:
    """Definiert die im PDF verwendeten Textstile."""
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=15,
        leading=18, textColor=BLUE, alignment=TA_CENTER, spaceAfter=3 * mm,
    )
    body = ParagraphStyle(
        "body", parent=base["BodyText"], fontName="Helvetica", fontSize=9,
        leading=11.5, alignment=TA_LEFT, allowWidows=0, allowOrphans=0,
    )
    small = ParagraphStyle("small", parent=body, fontSize=8.2, leading=10)
    tiny = ParagraphStyle("tiny", parent=body, fontSize=7.6, leading=9)
    return {"title": title, "body": body, "small": small, "tiny": tiny}


def build_attendance_table(payload: dict, styles: dict) -> Table:
    """Baut die Anwesenheitsliste (Checkbox-Symbole) für die Kopfzeile."""
    attendance = payload.get("anwesend", {})
    present_count = sum(1 for name in TEILNEHMENDE if attendance.get(name, False))

    rows = [[Paragraph(f"<b>Anwesend ({present_count}/{len(TEILNEHMENDE)})</b>", styles["small"])]]
    rows.extend(
        [Paragraph(f"{'[X]' if attendance.get(name, False) else '[ ]'}&nbsp;&nbsp;{esc(name)}", styles["tiny"])]
        for name in TEILNEHMENDE
    )

    table = Table(rows, colWidths=[61 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.1 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1 * mm),
    ]))
    return table


def build_top_section(payload: dict, styles: dict) -> Table:
    """Kopfbereich des PDFs: Datum/Thema links, Anwesenheitsliste rechts."""
    session_date = parse_date(payload.get("sitzung_vom"))
    date_today = session_date.strftime("%d.%m.%Y") if session_date else ""

    today_info = Table([
        [Paragraph("<b>Sitzung vom</b>", styles["small"]), p(date_today, styles["body"])],
        [Paragraph("<b>Thema heute</b>", styles["small"]), p(payload.get("thema_heute", ""), styles["body"])],
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

    attendees = build_attendance_table(payload, styles)

    top = Table([[today_info, attendees]], colWidths=[121 * mm, 61 * mm], hAlign="LEFT")
    top.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return top


def build_next_meeting_flowables(payload: dict, styles: dict) -> list:
    """Abschnitt "Nächstes Mal": Metadaten, Gedanken und Programmideen."""
    next_date = parse_date(payload.get("naechstes_datum"))
    date_next = next_date.strftime("%d.%m.%Y") if next_date else ""

    next_meta = Table([[
        Paragraph("<b>Datum</b>", styles["small"]), p(date_next, styles["body"]),
        Paragraph("<b>Thema</b>", styles["small"]), p(payload.get("naechstes_thema", ""), styles["body"]),
        Paragraph("<b>Input verantwortlich</b>", styles["small"]),
        p(payload.get("naechster_input_verantwortlich", ""), styles["body"]),
    ]], colWidths=[17 * mm, 27 * mm, 17 * mm, 52 * mm, 35 * mm, 38 * mm])
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

    return [
        section_header("Nächstes Mal", styles["small"], fill=NEXT, text_color=NEXT_DARK),
        next_meta,
        Spacer(1, 2.2 * mm),
        content_box(
            "Gedanken zum nächsten Input", payload.get("gedanken_naechster_input", ""),
            styles["body"], styles["small"], fill=NEXT, text_color=NEXT_DARK,
        ),
        Spacer(1, 2.2 * mm),
        content_box(
            "Programmideen zum nächsten Nachmittag", payload.get("programmideen_naechster_nachmittag", ""),
            styles["body"], styles["small"],
        ),
        Spacer(1, 3 * mm),
    ]


def build_program_table(payload: dict, styles: dict) -> Table:
    """Tabelle der Programmpunkte (Zeit / Block / Notizen)."""
    rows = [[
        Paragraph("<b>Zeit</b>", styles["small"]),
        Paragraph("<b>Block</b>", styles["small"]),
        Paragraph("<b>Notizen / Ablauf</b>", styles["small"]),
    ]]
    for block in payload.get("program_blocks", []):
        rows.append([
            p(block.get("time", ""), styles["body"]),
            p(block.get("title", ""), styles["body"]),
            p(block.get("details", ""), styles["body"]),
        ])

    table = Table(rows, colWidths=[20 * mm, 48 * mm, 118 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NEXT),
        ("TEXTCOLOR", (0, 0), (-1, 0), NEXT_DARK),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
    ]))
    return table


def build_today_program_flowables(payload: dict, styles: dict) -> list:
    """Abschnitt "Programm heute": Programmtabelle plus Freitext-Notizen."""
    return [
        section_header("Programm heute", styles["small"]),
        build_program_table(payload, styles),
        Spacer(1, 3 * mm),
        content_box(
            "Programm heute", payload.get("programm_heute", ""),
            styles["body"], styles["small"], fill=TODAY, text_color=TODAY_DARK,
        ),
        Spacer(1, 3 * mm),
    ]


def build_overnext_table(payload: dict, styles: dict) -> Table:
    """Balken "Input übernächstes Mal" mit Datum und Verantwortlichkeit."""
    overnext_date = parse_date(payload.get("uebernaechstes_datum"))
    date_overnext = overnext_date.strftime("%d.%m.%Y") if overnext_date else ""

    table = Table([[
        Paragraph("<b>Input übernächstes Mal</b>", styles["small"]),
        Paragraph("<b>Datum</b>", styles["small"]), p(date_overnext, styles["body"]),
        Paragraph("<b>Verantwortlich</b>", styles["small"]),
        p(payload.get("uebernaechster_input_verantwortlich", ""), styles["body"]),
    ]], colWidths=[43 * mm, 17 * mm, 31 * mm, 29 * mm, 66 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), OVERNEXT),
        ("BACKGROUND", (1, 0), (1, 0), OVERNEXT),
        ("BACKGROUND", (3, 0), (3, 0), OVERNEXT),
        ("TEXTCOLOR", (0, 0), (0, 0), OVERNEXT_DARK),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
    ]))
    return table


def build_diverses_flowables(payload: dict, styles: dict) -> list:
    """Abschnitt "Diverses": eine Box pro Karte, oder ein Platzhalter."""
    flowables = [section_header("Diverses", styles["small"], fill=MISC, text_color=MISC_DARK)]

    cards = payload.get("diverses_cards", [])
    if cards:
        for card in cards:
            card_title = card.get("title", "").strip() or "Diverses"
            flowables.append(KeepTogether([
                content_box(card_title, card.get("text", ""), styles["body"], styles["small"], fill=MISC, text_color=MISC_DARK)
            ]))
            flowables.append(Spacer(1, 2 * mm))
    else:
        flowables.append(content_box("Diverses", "", styles["body"], styles["small"], fill=MISC, text_color=MISC_DARK))

    return flowables


def create_pdf(payload: dict) -> bytes:
    """Erstellt das vollständige Sitzungsprotokoll-PDF aus dem Payload-Dict."""
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
    styles = build_pdf_styles()

    story: list = [Paragraph("Sitzungsprotokoll", styles["title"])]
    story.append(build_top_section(payload, styles))
    story.append(Spacer(1, 3 * mm))
    story.extend(build_next_meeting_flowables(payload, styles))
    story.extend(build_today_program_flowables(payload, styles))
    story.append(build_overnext_table(payload, styles))
    story.append(Spacer(1, 3 * mm))
    story.extend(build_diverses_flowables(payload, styles))

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    return output.getvalue()


# =============================================================================
# 8. Seitenaufbau (Streamlit-UI)
# =============================================================================


def apply_custom_css() -> None:
    """Bindet das seitenweite CSS für Layout, Farben und Formularabstände ein."""
    st.markdown("""
    <style>
    .block-container {max-width: 1180px; padding-top: 1.2rem; padding-bottom: 3rem;}
    h1, h2, h3 {color: #1F4E78;}
    [data-testid="stSidebar"] {background: #f5f8fa;}
    .section-line {border-top: 3px solid #1F4E78; margin: 1.6rem 0 1rem 0;}
    .card-label {font-weight:700;color:#1F4E78;margin-top:.4rem;}
    .pdf-band,.next-subband{border:1px solid #7F8C8D;border-radius:5px;padding:.5rem .75rem;margin:1rem 0 .55rem;font-weight:750}
    .today-band{background:#D9EAF7;color:#1F4E78}
    .next-band,.next-subband{background:#E4F2DF;color:#376B2B}
    .overnext-band{background:#FFF0D5;color:#8A5600}
    .misc-band{background:#EEE1F6;color:#67417E}
    div[data-testid="stDateInput"] {max-width:185px;}
    div[data-testid="stCheckbox"] {margin-bottom:-0.35rem;}
    div[data-testid="stCheckbox"] label {gap:.35rem;}

    </style>
    """, unsafe_allow_html=True)


def render_flash_message() -> None:
    """Zeigt eine einmalige Erfolgsmeldung an (z. B. nach dem Öffnen eines Entwurfs)."""
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))


def render_sidebar() -> None:
    """Seitenleiste: neue Sitzung starten oder einen gespeicherten Entwurf öffnen."""
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


def render_today_section() -> None:
    """Abschnitt "Heutige Sitzung": Datum, Thema und Anwesenheit."""
    st.markdown('<div class="pdf-band today-band">Heutige Sitzung</div>', unsafe_allow_html=True)

    col_date, col_topic = st.columns([1, 9], gap="small")
    with col_date:
        st.date_input("Sitzung vom", key="sitzung_vom", format="DD.MM.YYYY")
    with col_topic:
        st.text_input("Thema", key="thema_heute")

    st.markdown("**Anwesend**")
    attendance_cols = st.columns(4)
    for index, name in enumerate(TEILNEHMENDE):
        with attendance_cols[index % 4]:
            st.checkbox(name, key=f"anw_{index}")

    st.markdown("")


def render_next_meeting_section() -> None:
    """Abschnitt "Nächstes Mal": Termin, Thema, Input-Verantwortliche und Gedanken."""
    st.markdown('<div class="pdf-band next-band">Nächstes Mal</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 6, 2])
    with c1:
        st.date_input("Datum", key="naechstes_datum", format="DD.MM.YYYY")
    with c2:
        st.text_input("Thema", key="naechstes_thema")
    with c3:
        st.text_input("Input verantwortlich", key="naechster_input_verantwortlich")

    st.text_area("Gedanken zum nächsten Input", key="gedanken_naechster_input", height=120)


def render_program_planning_table() -> None:
    """Editierbare Tabelle der Programmpunkte für den nächsten Nachmittag."""
    st.markdown('<div class="next-subband">Programmideen zum nächsten Nachmittag</div>', unsafe_allow_html=True)

    head1, head2, head3, head4 = st.columns([1, 2.2, 5.4, .55])
    head1.markdown("**Zeit**")
    head2.markdown("**Block**")
    head3.markdown("**Notizen / Ablauf**")

    for block in st.session_state["program_blocks"]:
        bid = block["id"]
        ctime, ctitle, cnotes, cdelete = st.columns([1, 2.2, 5.4, .55])

        with ctime:
            if block.get("fixed"):
                st.text_input("Zeit", value=block["time"], key=f"fixed_time_{bid}", disabled=True, label_visibility="collapsed")
            else:
                st.text_input("Zeit", value=block.get("time", ""), key=f"program_time_{bid}", label_visibility="collapsed")

        with ctitle:
            if block.get("fixed"):
                st.text_input("Block", value=block["title"], key=f"fixed_title_{bid}", disabled=True, label_visibility="collapsed")
            else:
                st.text_input("Block", value=block.get("title", ""), key=f"program_title_{bid}", label_visibility="collapsed")

        with cnotes:
            st.text_area("Notizen", value=block.get("details", ""), key=f"program_details_{bid}", height=72, label_visibility="collapsed")

        with cdelete:
            if not block.get("fixed"):
                st.button("🗑️", key=f"remove_program_{bid}", on_click=remove_program_block, args=(bid,))

    st.button("➕ Programmblock hinzufügen", on_click=add_program_block, use_container_width=True)


def render_today_program_section() -> None:
    """Freitextfeld "Programm heute"."""
    st.markdown('<div class="pdf-band today-band">Programm heute</div>', unsafe_allow_html=True)
    st.text_area("Heutiges Programm", key="programm_heute", height=220, label_visibility="collapsed")


def render_overnext_section() -> None:
    """Abschnitt "Input übernächstes Mal": Termin, Thema und Verantwortlichkeit."""
    st.markdown('<div class="pdf-band overnext-band">Input übernächstes Mal</div>', unsafe_allow_html=True)

    o1, o2, o3 = st.columns([1, 6, 2])
    with o1:
        st.date_input("Datum", key="uebernaechstes_datum", format="DD.MM.YYYY")
    with o2:
        st.text_input("Thema", key="uebernaechster_input_thema")
    with o3:
        st.text_input("Verantwortlich", key="uebernaechster_input_verantwortlich")


def render_diverses_section() -> None:
    """Abschnitt "Diverses": frei hinzufügbare Karten mit Titel und Text."""
    st.markdown('<div class="pdf-band misc-band">Diverses</div>', unsafe_allow_html=True)

    if not st.session_state["diverses_cards"]:
        st.caption("Noch keine Karte vorhanden.")

    for card in st.session_state["diverses_cards"]:
        cid = card["id"]
        with st.container(border=True):
            x1, x2 = st.columns([8, .55])
            with x1:
                st.text_input("Titel", value=card.get("title", ""), key=f"div_title_{cid}", label_visibility="collapsed", placeholder="Titel")
            with x2:
                st.button("🗑️", key=f"remove_div_{cid}", on_click=remove_diverses_card, args=(cid,))
            st.text_area("Inhalt", value=card.get("text", ""), key=f"div_text_{cid}", height=105, label_visibility="collapsed")

    st.button("➕ Diverses-Karte hinzufügen", on_click=add_diverses_card, use_container_width=True)


def render_actions_section() -> None:
    """Fusszeile: Entwurf speichern und PDF herunterladen."""
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


def main() -> None:
    """Baut die komplette Seite in der Reihenfolge der Formularabschnitte auf."""
    initialize_state()
    apply_custom_css()
    render_flash_message()
    render_sidebar()

    st.title("📝 Sitzungsprotokoll Jungschi Neuhof")

    render_today_section()
    render_next_meeting_section()
    render_program_planning_table()
    render_today_program_section()
    render_overnext_section()
    render_diverses_section()
    render_actions_section()


main()
