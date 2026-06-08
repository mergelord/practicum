#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a preliminary commercial proposal / price list PDF for
Черникова Л.А. from the public FNKC thoracic surgery price page.

Source:
https://fnkc-fmba.ru/services/statsionar/tsentr-khirurgii/klinika-torakalnoy-khirurgii/

This is not an official clinic invoice, medical conclusion, prescription,
or public offer. Final price must be confirmed by the clinic.
"""
from __future__ import annotations

import datetime as _dt
import html
import os
import re
import sys
import textwrap
import urllib.request
from pathlib import Path

SOURCE_URL = "https://fnkc-fmba.ru/services/statsionar/tsentr-khirurgii/klinika-torakalnoy-khirurgii/"
RECIPIENT = "Черникова Л.А."
OUT_PDF = Path(__file__).with_name("kommercheskoe_predlozhenie_Chernikova_LA_torakalnaya_hirurgiya.pdf")
OUT_HTML = Path(__file__).with_name("kommercheskoe_predlozhenie_Chernikova_LA_torakalnaya_hirurgiya.html")
TODAY = _dt.date.today().strftime("%d.%m.%Y")


def fetch_source(url: str = SOURCE_URL) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FNKC-proposal-generator/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, errors="replace")


def html_to_text(src: str) -> str:
    src = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", src)
    src = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", src)
    src = re.sub(r"(?i)<br\s*/?>", "\n", src)
    src = re.sub(r"(?i)</(?:p|div|li|tr|td|th|h[1-6])>", "\n", src)
    src = re.sub(r"(?s)<[^>]+>", " ", src)
    src = html.unescape(src)
    src = src.replace("\xa0", " ").replace("₽", " руб.")
    src = re.sub(r"[ \t]+", " ", src)
    src = re.sub(r"\n\s+", "\n", src)
    return src


def clean_name(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" —–-:;,.\t\r\n")
    junk_prefixes = (
        "цена", "стоимость", "руб", "от", "до", "услуги", "наименование",
        "код", "подробнее", "записаться", "заказать", "оставить заявку",
    )
    while True:
        low = s.lower()
        changed = False
        for p in junk_prefixes:
            if low.startswith(p + " "):
                s = s[len(p):].strip(" —–-:;,. ")
                changed = True
                break
        if not changed:
            return s


def parse_services(text: str) -> list[tuple[str, int]]:
    """Extract service names and prices from the rendered text.

    The source page is a public price-list page. The parser is intentionally
    conservative: it scans text near ruble-looking numbers and keeps medical
    service-like names.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    joined = "\n".join(lines)

    # Most prices are rendered as names followed by a number like "160 000".
    price_re = re.compile(r"(?<!\d)(\d{1,3}(?:[ \u00a0]\d{3})+|\d{4,6})(?:\s*(?:руб\.?|₽))?(?!\d)", re.I)
    candidates: list[tuple[str, int]] = []
    for m in price_re.finditer(joined):
        price = int(re.sub(r"\D", "", m.group(1)))
        if price < 1000 or price > 5_000_000:
            continue

        before = joined[max(0, m.start() - 280):m.start()]
        before = before.split("\n")[-3:]
        name = " ".join(before)
        name = re.sub(r"(?<!\d)(\d{1,3}(?:[ \u00a0]\d{3})+|\d{4,6})(?:\s*(?:руб\.?|₽))?", " ", name)
        name = clean_name(name)

        # Drop obvious navigation/footer fragments.
        low = name.lower()
        if len(name) < 12:
            continue
        if any(x in low for x in ("cookie", "javascript", "версия для слабовидящих", "личный кабинет")):
            continue
        if not any(ch.isalpha() for ch in name):
            continue

        candidates.append((name, price))

    # De-duplicate while preserving order. Also trim overlong names by keeping
    # the medically meaningful tail when the parser captured previous labels.
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    medical_starts = (
        "анатомическая", "бронхо", "бронхопластическая", "верхняя", "диагностическая",
        "дренирование", "закрытие", "комбинированная", "лоб", "медиастин", "нижняя",
        "операция", "плевр", "пневмон", "торако", "удаление", "ушивание", "экстирпация",
        "резекция", "сегмент", "консультация", "стационар", "видеоторакоскоп",
    )
    for name, price in candidates:
        words = name.split()
        for i, w in enumerate(words):
            if w.lower().strip(".,;:()") .startswith(medical_starts):
                if i > 0:
                    name = " ".join(words[i:])
                break
        name = clean_name(name)
        key = (name.lower(), price)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, price))

    return out


def money(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


def fallback_html(services: list[tuple[str, int]]) -> None:
    rows = "\n".join(
        f"<tr><td>{i}</td><td>{html.escape(name)}</td><td class='price'>{money(price)}</td></tr>"
        for i, (name, price) in enumerate(services, 1)
    )
    min_price = min((p for _, p in services), default=0)
    max_price = max((p for _, p in services), default=0)
    doc = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Коммерческое предложение — {html.escape(RECIPIENT)}</title>
<style>
body  font-family: Arial, sans-serif; margin: 28px; color: #1f1f1f; 
h1  color: #1F4E79; 
.note  background: #eef5ff; border-left: 5px solid #1F4E79; padding: 12px; 
table  border-collapse: collapse; width: 100%; font-size: 12px; 
th  background: #1F4E79; color: white; 
th, td  border: 1px solid #bbb; padding: 5px 7px; vertical-align: top; 
tr:nth-child(even)  background: #f7f9fb; 
.price  text-align: right; white-space: nowrap; 
</style>
</head>
<body>
<h1>Коммерческое предложение — {html.escape(RECIPIENT)}</h1>
<p><b>Направление:</b> торакальная хирургия<br>
<b>Источник цен:</b> <a href="{SOURCE_URL}">{SOURCE_URL}</a><br>
<b>Дата подготовки:</b> {TODAY}</p>
<div class="note">Документ подготовлен как предварительное коммерческое предложение и прайс-лист по опубликованным ценам. Не является медицинским заключением, назначением, официальным счетом или публичной офертой.</div>
<h2>Краткое резюме</h2>
<ul><li>Позиций: {len(services)}</li><li>Минимальная цена: {money(min_price)}</li><li>Максимальная цена: {money(max_price)}</li></ul>
<h2>Прайс-лист</h2>
<table><thead><tr><th>№</th><th>Наименование услуги</th><th>Цена</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    OUT_HTML.write_text(doc, encoding="utf-8")


def build_pdf(services: list[tuple[str, int]]) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception as e:
        fallback_html(services)
        print(f"ReportLab не установлен: {e}")
        print(f"Создан HTML вместо PDF: {OUT_HTML}")
        return

    font = "Helvetica"
    font_bold = "Helvetica-Bold"
    for candidate in (
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ):
        if candidate.exists():
            pdfmetrics.registerFont(TTFont("DocFont", str(candidate)))
            font = "DocFont"
            break
    for candidate in (
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ):
        if candidate.exists():
            pdfmetrics.registerFont(TTFont("DocFontBold", str(candidate)))
            font_bold = "DocFontBold"
            break

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCyr", parent=styles["Title"], fontName=font_bold, fontSize=18, leading=22, textColor=colors.HexColor("#1F4E79")))
    styles.add(ParagraphStyle(name="BodyCyr", parent=styles["BodyText"], fontName=font, fontSize=9, leading=12))
    styles.add(ParagraphStyle(name="SmallCyr", parent=styles["BodyText"], fontName=font, fontSize=7, leading=9, textColor=colors.HexColor("#555555")))
    styles.add(ParagraphStyle(name="TableText", parent=styles["BodyText"], fontName=font, fontSize=6.4, leading=8))
    styles.add(ParagraphStyle(name="TableTextBold", parent=styles["BodyText"], fontName=font_bold, fontSize=6.6, leading=8, textColor=colors.white))

    min_price = min((p for _, p in services), default=0)
    max_price = max((p for _, p in services), default=0)
    story = []
    story.append(Paragraph(f"Коммерческое предложение — {RECIPIENT}", styles["TitleCyr"]))
    story.append(Paragraph("Направление: торакальная хирургия", styles["BodyCyr"]))
    story.append(Paragraph(f"Источник цен: {SOURCE_URL}", styles["SmallCyr"]))
    story.append(Paragraph(f"Дата подготовки: {TODAY}", styles["SmallCyr"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Документ подготовлен как предварительное коммерческое предложение и прайс-лист по опубликованным ценам Клиники торакальной хирургии ФНКЦ ФМБА России. Не является медицинским заключением, назначением, официальным счетом или публичной офертой. Окончательная стоимость определяется клиникой после очной консультации, обследования и выбора тактики лечения.", styles["BodyCyr"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"Позиций: {len(services)} · минимальная цена: {money(min_price)} · максимальная цена: {money(max_price)}", styles["BodyCyr"]))
    story.append(Spacer(1, 4 * mm))

    data = [[Paragraph("№", styles["TableTextBold"]), Paragraph("Наименование услуги", styles["TableTextBold"]), Paragraph("Цена", styles["TableTextBold"])]
    for i, (name, price) in enumerate(services, 1):
        data.append([Paragraph(str(i), styles["TableText"]), Paragraph(name, styles["TableText"]), Paragraph(money(price), styles["TableText"])])

    table = Table(data, colWidths=[12 * mm, 220 * mm, 31 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BFBFBF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(table)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(doc.leftMargin, 8 * mm, f"Предварительное КП для {RECIPIENT} · источник: ФНКЦ ФМБА России · {TODAY}")
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 8 * mm, f"стр. {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(OUT_PDF), pagesize=landscape(A4), rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Создан PDF: {OUT_PDF}")


def main() -> int:
    try:
        page = fetch_source()
    except Exception as e:
        print(f"Не удалось скачать страницу-источник: {e}", file=sys.stderr)
        return 2
    services = parse_services(html_to_text(page))
    if not services:
        print("Не удалось извлечь позиции прайс-листа.", file=sys.stderr)
        return 3
    build_pdf(services)
    print(f"Позиций извлечено: {len(services)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
