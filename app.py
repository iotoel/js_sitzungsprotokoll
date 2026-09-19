from __future__ import annotations

import base64
from io import BytesIO
from datetime import date

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)

st.set_page_config(page_title="Sitzungsprotokoll", page_icon="📝", layout="wide")

BLUE = colors.HexColor("#1F4E78")
LIGHT_BLUE = colors.HexColor("#D9EAF7")
VERY_LIGHT = colors.HexColor("#F5F8FA")
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


def esc(value: object) -> str:
    text = "" if value is None else str(value)
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>"))


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
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title="Sitzungsprotokoll Jungschi Neuhof",
        author="Streamlit Sitzungsprotokoll",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=BLUE, alignment=TA_CENTER,
        spaceAfter=5 * mm,
    )
    body = ParagraphStyle(
        "BodyCustom", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=10, leading=14, textColor=colors.black, alignment=TA_LEFT,
    )
    small = ParagraphStyle(
        "SmallCustom", parent=body, fontSize=9, leading=12,
    )

    story = [Paragraph("Sitzungsprotokoll", title_style)]

    meta = Table([
        [Paragraph("<b>Sitzung vom</b>", small), Paragraph(esc(data["sitzung_vom"]), body),
         Paragraph("<b>Thema</b>", small), Paragraph(esc(data["thema"]), body)],
        [Paragraph("<b>Nächster Jungschi-NaMi</b><br/><font size='8'>(Input &amp; Programm)</font>", small),
         Paragraph(esc(data["naechster_termin"]), body),
         Paragraph("<b>Verantwortlich</b>", small), Paragraph(esc(data["verantwortlich"]), body)],
    ], colWidths=[34 * mm, 51 * mm, 31 * mm, 58 * mm])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    story.extend([meta, Spacer(1, 5 * mm)])

    present = [name for name, checked in data["anwesend"].items() if checked]
    participant_rows = []
    for i in range(0, len(TEILNEHMENDE), 2):
        row = []
        for name in TEILNEHMENDE[i:i + 2]:
            mark = "[X]" if name in present else "[ ]"
            row.append(Paragraph(f"{mark}&nbsp;&nbsp;{esc(name)}", small))
        if len(row) == 1:
            row.append(Paragraph("", small))
        participant_rows.append(row)

    attendee_heading = Table([[Paragraph(f"<b>Anwesend ({len(present)} / {len(TEILNEHMENDE)})</b>", body)]], colWidths=[174 * mm])
    attendee_heading.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, -1), BLUE),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    attendees = Table(participant_rows, colWidths=[87 * mm, 87 * mm])
    attendees.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D6D8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
    ]))
    story.extend([KeepTogether([attendee_heading, attendees]), Spacer(1, 5 * mm)])

    story.extend([
        section_box("Gedanken", data["gedanken"], body, 25),
        Spacer(1, 4 * mm),
        section_box("Programmideen", data["programmideen"], body, 39),
        PageBreak(),
        section_box("Programm heute", data["programm_heute"], body, 72),
        Spacer(1, 5 * mm),
        section_box("Diverses", data["diverses"], body, 72),
    ])

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return buffer.getvalue()


st.markdown("""
<style>
.block-container {max-width: 1250px; padding-top: 1.4rem; padding-bottom: 3rem;}
[data-testid="stForm"] {border: 1px solid #d7e0e7; border-radius: 12px; padding: 1.2rem; background: #fbfcfd;}
h1, h2, h3 {color: #1F4E78;}
.small-note {color:#5f6b73; font-size:0.9rem;}
</style>
""", unsafe_allow_html=True)

st.title("📝 Sitzungsprotokoll Jungschi Neuhof")
st.caption("Formular ausfüllen, PDF erzeugen, in der Vorschau kontrollieren und anschliessend herunterladen oder drucken.")

with st.form("protokoll_form"):
    st.subheader("Sitzung")
    c1, c2 = st.columns(2)
    with c1:
        sitzung_vom = st.date_input("Sitzung vom", value=date.today(), format="DD.MM.YYYY")
        naechster_termin = st.date_input("Nächster Jungschi-NaMi (Input & Programm)", value=None, format="DD.MM.YYYY")
    with c2:
        thema = st.text_input("Thema")
        verantwortlich = st.text_input("Verantwortlich")

    st.subheader("Anwesend")
    attendance_cols = st.columns(2)
    anwesend = {}
    for idx, name in enumerate(TEILNEHMENDE):
        with attendance_cols[idx % 2]:
            anwesend[name] = st.checkbox(name, key=f"anw_{idx}")

    st.subheader("Inhalte")
    gedanken = st.text_area("Gedanken", height=130)
    programmideen = st.text_area("Programmideen", height=180)
    programm_heute = st.text_area("Programm heute", height=220)
    diverses = st.text_area("Diverses", height=180)

    submitted = st.form_submit_button("PDF erstellen", type="primary", use_container_width=True)

if submitted:
    data = {
        "sitzung_vom": sitzung_vom.strftime("%d.%m.%Y") if sitzung_vom else "",
        "naechster_termin": naechster_termin.strftime("%d.%m.%Y") if naechster_termin else "",
        "thema": thema,
        "verantwortlich": verantwortlich,
        "anwesend": anwesend,
        "gedanken": gedanken,
        "programmideen": programmideen,
        "programm_heute": programm_heute,
        "diverses": diverses,
    }
    st.session_state["pdf_bytes"] = create_pdf(data)
    st.session_state["pdf_name"] = f"Sitzungsprotokoll_{data['sitzung_vom'].replace('.', '-')}.pdf"

if "pdf_bytes" in st.session_state:
    st.divider()
    st.subheader("PDF-Vorschau")
    encoded = base64.b64encode(st.session_state["pdf_bytes"]).decode("ascii")
    st.download_button(
        "PDF herunterladen",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state["pdf_name"],
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{encoded}" width="100%" height="850" '
        'style="border:1px solid #d7e0e7;border-radius:8px"></iframe>',
        unsafe_allow_html=True,
    )
    st.info("Zum Drucken das PDF herunterladen oder in der PDF-Vorschau das Drucksymbol des Browsers verwenden.")
