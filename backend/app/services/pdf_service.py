from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


def _styles() -> dict:
    base = getSampleStyleSheet()["Normal"]
    return {
        "name": ParagraphStyle("Name", parent=base, fontSize=20, fontName="Helvetica-Bold", leading=24, spaceAfter=6),
        "contact": ParagraphStyle("Contact", parent=base, fontSize=10, leading=14, textColor=colors.HexColor("#666666"), spaceAfter=14),
        "section": ParagraphStyle("Section", parent=base, fontSize=9, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=4, textColor=colors.HexColor("#333333")),
        "body": ParagraphStyle("Body", parent=base, fontSize=10, leading=16, spaceAfter=8),
        "role": ParagraphStyle("Role", parent=base, fontSize=10, fontName="Helvetica-Bold", spaceAfter=1),
        "meta": ParagraphStyle("Meta", parent=base, fontSize=9, textColor=colors.HexColor("#777777"), spaceAfter=4),
        "bullet": ParagraphStyle("Bullet", parent=base, fontSize=10, leading=14, leftIndent=10, spaceAfter=3),
    }


def _rule():
    return HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#DDDDDD"), spaceAfter=10)


def _build(story: list) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    doc.build(story)
    return buffer.getvalue()


def generate_cover_letter_pdf(
    name: str,
    email: str,
    job_title: str,
    company: str,
    cover_letter: str,
) -> bytes:
    s = _styles()
    story = []

    story.append(Paragraph(name or "Applicant", s["name"]))
    story.append(Paragraph(email or "", s["contact"]))
    story.append(_rule())

    story.append(Paragraph(f"{job_title} — {company}", s["body"]))
    story.append(Spacer(1, 6))

    for para in cover_letter.strip().split("\n\n"):
        para = para.strip().replace("\n", " ")
        if para:
            story.append(Paragraph(para, s["body"]))

    return _build(story)


def generate_resume_pdf(
    name: str,
    email: str,
    tailored_resume: dict,
) -> bytes:
    s = _styles()
    story = []

    story.append(Paragraph(name or "Applicant", s["name"]))
    story.append(Paragraph(email or "", s["contact"]))
    story.append(_rule())

    skills = tailored_resume.get("skills") or []
    if skills:
        story.append(Paragraph("SKILLS", s["section"]))
        story.append(_rule())
        story.append(Paragraph(", ".join(skills), s["body"]))

    experience = tailored_resume.get("experience") or []
    if experience:
        story.append(Paragraph("EXPERIENCE", s["section"]))
        story.append(_rule())
        for exp in experience:
            start = exp.get("start", "")
            end = exp.get("end", "Present")
            dates = f"{start} – {end}" if start else ""
            story.append(Paragraph(f"{exp.get('role', '')} — {exp.get('company', '')}", s["role"]))
            if dates:
                story.append(Paragraph(dates, s["meta"]))
            for bullet in exp.get("bullets") or []:
                story.append(Paragraph(f"• {bullet}", s["bullet"]))
            story.append(Spacer(1, 6))

    education = tailored_resume.get("education") or []
    if education:
        story.append(Paragraph("EDUCATION", s["section"]))
        story.append(_rule())
        for edu in education:
            parts = [edu.get("degree", ""), edu.get("institution", "")]
            line = " — ".join(p for p in parts if p)
            if edu.get("year"):
                line += f" ({edu['year']})"
            story.append(Paragraph(line, s["body"]))

    return _build(story)
