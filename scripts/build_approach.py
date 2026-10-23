from pathlib import Path
from html import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="BodyCustom",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=9,
        textColor=colors.HexColor("#263445"),
    )
)
styles["Heading1"].textColor = colors.HexColor("#123653")
styles["Heading2"].textColor = colors.HexColor("#137C8B")
styles["Heading2"].spaceBefore = 14
story = []
for part in Path("docs/Approach_Document.md").read_text().split("\n\n"):
    for text in [part] if not part.startswith("#") else part.splitlines():
        if text.startswith("# "):
            style = styles["Title"]
            text = text[2:]
        elif text.startswith("## "):
            style = styles["Heading2"]
            text = text[3:]
        else:
            style = styles["BodyCustom"]
        story.append(Paragraph(escape(text).replace("\n", "<br/>"), style))


def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#137C8B"))
    canvas.line(45, 38, 550, 38)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(45, 25, "CT-200 | Tri9T Internship | Approach Document")
    canvas.drawRightString(550, 25, str(doc.page))


SimpleDocTemplate(
    "docs/Approach_Document.pdf",
    pagesize=(595.28, 841.89),
    rightMargin=45,
    leftMargin=45,
    topMargin=42,
    bottomMargin=52,
    title="CT-200 Approach Document",
    author="Ganjayi Shravan Kumar",
).build(story, onFirstPage=footer, onLaterPages=footer)
