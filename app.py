"""Sitzungsprotokoll Jungschi Neuhof.

Streamlit-App zum Erfassen von Sitzungsprotokollen. Erlaubt das Ausfüllen
eines Formulars und das Speichern als JSON-Entwurf auf der Festplatte.

Der Code ist in drei grosse Bereiche gegliedert:
    1. VORARBEITEN       - Konfiguration, Hilfsfunktionen, State-Verwaltung,
                            Laden/Speichern von Entwürfen (alles, was vor dem
                            eigentlichen Seitenaufbau bereitstehen muss).
    2. STREAMLIT-SEITE    - Aufbau und Anzeige der Seite, unterteilt in eine
                            Funktion pro Block auf der Seite.
    3. PDF-GENERIERUNG    - Aktuell noch nicht implementiert (Platzhalter).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import streamlit as st


# #############################################################################
# 1. VORARBEITEN
# #############################################################################
#
# Dieser Bereich enthält alles, was vor dem Zeichnen der Seite feststehen
# muss: Konfiguration, allgemeine Hilfsfunktionen, den Session-State (inkl.
# Standardwerten), die Umwandlung des States in ein speicherbares Format
# sowie das Lesen/Schreiben von Entwürfen auf der Festplatte.

# -----------------------------------------------------------------------
# 1.1 Konfiguration & Konstanten
# -----------------------------------------------------------------------

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


# -----------------------------------------------------------------------
# 1.2 Allgemeine Hilfsfunktionen
# -----------------------------------------------------------------------


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


def safe_filename(value: str) -> str:
    """Macht aus einem beliebigen Text einen sicheren Dateinamen-Bestandteil."""
    cleaned = re.sub(r"[^A-Za-z0-9ÄÖÜäöü._-]+", "_", value.strip())
    return cleaned.strip("_.") or "Sitzungsprotokoll"


# -----------------------------------------------------------------------
# 1.3 Session-State: Standardwerte & Verwaltung
# -----------------------------------------------------------------------


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


# -----------------------------------------------------------------------
# 1.4 Synchronisation der dynamischen Formular-Widgets
# -----------------------------------------------------------------------
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


# -----------------------------------------------------------------------
# 1.5 Umwandlung Session-State <-> Speicher-Payload (JSON)
# -----------------------------------------------------------------------


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


# -----------------------------------------------------------------------
# 1.6 Entwürfe auf der Festplatte (lesen/schreiben/auflisten)
# -----------------------------------------------------------------------


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


# #############################################################################
# 2. STREAMLIT-SEITE
# #############################################################################
#
# Dieser Bereich baut die eigentliche Seite auf. Für jeden sichtbaren Block
# auf der Seite (Sidebar, Kopfbereich, "Nächstes Mal", Programmtabelle,
# "Diverses", Aktionsleiste) gibt es eine eigene render_*-Funktion.
# main() ruft diese Funktionen am Ende in der Anzeigereihenfolge auf.


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

    c1, c2, c3 = st.columns([1, 6.5, 1.5])
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
                st.text_input("Zeit", value=block["time"], key=f"fixed_time_{bid}", label_visibility="collapsed")
            else:
                st.text_input("Zeit", value=block.get("time", ""), key=f"program_time_{bid}", label_visibility="collapsed")

        with ctitle:
            if block.get("fixed"):
                st.text_input("Block", value=block["title"], key=f"fixed_title_{bid}", label_visibility="collapsed")
            else:
                st.text_input("Block", value=block.get("title", ""), key=f"program_title_{bid}", label_visibility="collapsed")

        with cnotes:
            st.text_area("Notizen", value=block.get("details", ""), key=f"program_details_{bid}", height=1, label_visibility="collapsed")

        with cdelete:
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
            x1, x2 = st.columns([9.45, .55])
            with x1:
                st.text_input("Titel", value=card.get("title", ""), key=f"div_title_{cid}", label_visibility="collapsed", placeholder="Titel")
            with x2:
                st.button("🗑️", key=f"remove_div_{cid}", on_click=remove_diverses_card, args=(cid,))
            st.text_area("Inhalt", value=card.get("text", ""), key=f"div_text_{cid}", height=105, label_visibility="collapsed")

    st.button("➕ Diverses-Karte hinzufügen", on_click=add_diverses_card, use_container_width=True)


def render_actions_section() -> None:
    """Fusszeile mit den zwei Haupt-Aktionen: Entwurf speichern und PDF-Export.

    Der Speichern-Knopf ist voll funktionsfähig. Der PDF-Knopf ist bereits
    vorhanden, ruft aber noch keine echte PDF-Erstellung auf (siehe Bereich
    3, PDF-GENERIERUNG, weiter unten).
    """
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
        if st.button("⬇️ PDF herunterladen", use_container_width=True):
            st.info("Die PDF-Erstellung ist noch nicht implementiert.")


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


# #############################################################################
# 3. PDF-GENERIERUNG
# #############################################################################
#
# Noch nicht implementiert. Hier soll später eine Funktion wie
# create_pdf(payload: dict) -> bytes entstehen, die aus dem Payload-Dict
# (siehe payload_from_state() in Bereich 1) ein fertiges PDF erzeugt.
# render_actions_section() ruft diese Funktion dann anstelle des
# aktuellen Platzhalter-Hinweises auf.
