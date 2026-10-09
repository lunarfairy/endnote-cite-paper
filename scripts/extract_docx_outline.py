#!/usr/bin/env python3
"""Extract DOCX paragraphs, styles, and inferred chapters to CSV."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()


def paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find("./w:pPr/w:pStyle", NS)
    if style is None:
        return ""
    return style.attrib.get(W + "val", "")


def is_heading(style: str, text: str) -> bool:
    if style.lower().startswith("heading"):
        return True
    if style in {"1", "2", "3", "Title", "Subtitle"}:
        return True
    return bool(re.match(r"^(abstract|introduction|methods?|results?|discussion|conclusion|references?)\b", text, re.I))


def extract(docx: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(docx) as archive:
        document_xml = archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    rows: list[dict[str, str]] = []
    current_chapter = ""
    nonempty_index = 0
    for para_index, paragraph in enumerate(root.findall(".//w:p", NS), start=1):
        text = paragraph_text(paragraph)
        if not text:
            continue
        nonempty_index += 1
        style = paragraph_style(paragraph)
        heading = is_heading(style, text)
        if heading:
            current_chapter = text
        rows.append(
            {
                "paragraph_index": str(para_index),
                "nonempty_index": str(nonempty_index),
                "style": style,
                "is_heading": "true" if heading else "false",
                "chapter": current_chapter,
                "text": text,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--output", "-o", type=Path, default=Path("docx_outline.csv"))
    args = parser.parse_args(argv)

    if not args.docx.exists():
        parser.error(f"DOCX not found: {args.docx}")

    rows = extract(args.docx)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["paragraph_index", "nonempty_index", "style", "is_heading", "chapter", "text"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} non-empty paragraphs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
