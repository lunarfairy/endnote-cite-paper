#!/usr/bin/env python3
"""Insert EndNote temporary citations after anchored target sentences in a DOCX."""

from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import json
import re
import zipfile
from pathlib import Path

from lxml import etree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_URI = "http://www.w3.org/XML/1998/namespace"
W = "{" + W_URI + "}"
INSERTED_CITATION_ATTR = "data-codex-inserted-citation"
TERMINAL_PUNCTUATION = set(".,;:!?。；：！？")
CLOSING_PUNCTUATION = set("\"'”’)]）】》")


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.xpath(".//w:t", namespaces=NS))


def document_paragraph_texts(
    root: ET.Element,
    skip_text_node_ids: set[int] | None = None,
    skip_inserted_citations: bool = False,
) -> list[str]:
    skipped = skip_text_node_ids or set()
    texts: list[str] = []
    for paragraph in root.xpath(".//w:p", namespaces=NS):
        texts.append(
            "".join(
                node.text or ""
                for node in paragraph.xpath(".//w:t", namespaces=NS)
                if id(node) not in skipped and not (skip_inserted_citations and node.attrib.get(INSERTED_CITATION_ATTR) == "1")
            )
        )
    return texts


def clear_inserted_citation_markers(root: ET.Element) -> None:
    for node in root.xpath(".//w:t", namespaces=NS):
        if INSERTED_CITATION_ATTR in node.attrib:
            del node.attrib[INSERTED_CITATION_ATTR]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def paragraph_style(paragraph: ET.Element) -> str:
    values = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
    return str(values[0]) if values else ""


def is_heading(style: str, text: str) -> bool:
    if style.lower().startswith("heading"):
        return True
    if style in {"1", "2", "3", "Title", "Subtitle"}:
        return True
    return bool(re.match(r"^(abstract|introduction|methods?|results?|discussion|conclusion|references?)\b", text, re.I))


def int_field(row: dict[str, str], *names: str) -> int | None:
    for name in names:
        value = str(row.get(name, "")).strip()
        if not value:
            continue
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def paragraph_records(root: ET.Element) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    current_chapter = ""
    nonempty_index = 0
    for paragraph_index, paragraph in enumerate(root.xpath(".//w:p", namespaces=NS), start=1):
        text = paragraph_text(paragraph)
        stripped = normalize_space(text)
        if not stripped:
            continue
        nonempty_index += 1
        style = paragraph_style(paragraph)
        if is_heading(style, stripped):
            current_chapter = stripped
        records.append(
            {
                "paragraph": paragraph,
                "paragraph_index": paragraph_index,
                "nonempty_index": nonempty_index,
                "chapter": current_chapter,
                "text": text,
                "normalized_chapter": normalize_space(current_chapter).lower(),
            }
        )
    return records


def find_offsets(text: str, target: str) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = text.find(target, start)
        if offset < 0:
            return offsets
        offsets.append(offset)
        start = offset + max(1, len(target))


def citation_end_offset(text: str, target_start: int, target: str) -> int:
    """Return the insertion offset, before terminal punctuation when present."""
    end = target_start + len(target)
    probe = end
    while probe > target_start and text[probe - 1].isspace():
        probe -= 1
    while probe > target_start and text[probe - 1] in CLOSING_PUNCTUATION:
        probe -= 1
    if probe > target_start and text[probe - 1] in TERMINAL_PUNCTUATION:
        while probe > target_start and text[probe - 1] in TERMINAL_PUNCTUATION:
            probe -= 1
        return probe
    return end


def insert_run_after(parent: ET.Element, after_run: ET.Element, text: str) -> ET.Element:
    new_run = ET.Element(W + "r")
    new_text = ET.SubElement(new_run, W + "t")
    new_text.attrib["{" + XML_URI + "}space"] = "preserve"
    new_text.attrib[INSERTED_CITATION_ATTR] = "1"
    new_text.text = text
    children = list(parent)
    index = children.index(after_run)
    parent.insert(index + 1, new_run)
    return new_text


def insert_at_offset(paragraph: ET.Element, end_offset: int, citation: str) -> ET.Element:
    text_nodes = paragraph.xpath(".//w:t", namespaces=NS)
    cursor = 0
    for node in text_nodes:
        value = node.text or ""
        next_cursor = cursor + len(value)
        if cursor <= end_offset <= next_cursor:
            split_at = end_offset - cursor
            before = value[:split_at]
            after = value[split_at:]
            node.text = before
            node.attrib["{" + XML_URI + "}space"] = "preserve"
            run = node.getparent()
            run_parent = run.getparent()
            # Preserve formatting and every child after the split (tabs, drawings,
            # OLE objects, subsequent text), in their original order.
            trailing_run = ET.Element(W + "r", attrib=dict(run.attrib))
            properties = run.find(W + "rPr")
            if properties is not None:
                trailing_run.append(deepcopy(properties))
            if after:
                trailing_text = deepcopy(node)
                trailing_text.text = after
                trailing_run.append(trailing_text)
            for child in list(run)[run.index(node) + 1:]:
                trailing_run.append(child)
            inserted_text = insert_run_after(run_parent, run, " " + citation)
            if any(child.tag != W + "rPr" for child in trailing_run):
                run_parent.insert(run_parent.index(run) + 2, trailing_run)
            return inserted_text
        cursor = next_cursor
    raise ValueError("target end offset is outside paragraph text")


def resolve_insertion(records: list[dict[str, object]], row: dict[str, str]) -> dict[str, object]:
    target = str(row.get("target_sentence", "")).strip()
    citation = str(row.get("temporary_citation", "")).strip()
    if not target or not citation:
        return {"row": row, "status": "skipped_missing_target_or_citation", "detail": ""}

    requested_paragraph = int_field(row, "paragraph_index")
    requested_nonempty = int_field(row, "nonempty_index")
    requested_occurrence = int_field(row, "target_occurrence", "occurrence", "sentence_occurrence")
    requested_chapter = normalize_space(row.get("chapter", "")).lower()
    anchor_before = str(row.get("anchor_before", "")).strip()
    anchor_after = str(row.get("anchor_after", "")).strip()

    matches: list[tuple[dict[str, object], int, int]] = []
    for record in records:
        if requested_paragraph and record["paragraph_index"] != requested_paragraph:
            continue
        if requested_nonempty and record["nonempty_index"] != requested_nonempty:
            continue
        if requested_chapter and record["normalized_chapter"] != requested_chapter:
            continue
        paragraph = record["paragraph"]
        if not isinstance(paragraph, ET._Element):
            continue
        paragraph_full_text = paragraph_text(paragraph)
        for offset in find_offsets(paragraph_full_text, target):
            end_offset = citation_end_offset(paragraph_full_text, offset, target)
            if anchor_before and anchor_before not in paragraph_full_text[:offset]:
                continue
            if anchor_after and anchor_after not in paragraph_full_text[end_offset:]:
                continue
            matches.append((record, offset, end_offset))

    if requested_occurrence:
        if requested_occurrence > len(matches):
            return {
                "row": row,
                "status": "not_found",
                "detail": f"requested occurrence {requested_occurrence}, found {len(matches)}",
            }
        record, _offset, end_offset = matches[requested_occurrence - 1]
        return {
            "row": row,
            "status": "planned",
            "detail": f"occurrence {requested_occurrence}",
            "paragraph": record["paragraph"],
            "paragraph_index": record["paragraph_index"],
            "nonempty_index": record["nonempty_index"],
            "end_offset": end_offset,
            "citation": citation,
        }

    if not matches:
        return {"row": row, "status": "not_found", "detail": ""}
    if len(matches) > 1:
        locations = [
            f"p{match[0]['paragraph_index']}/n{match[0]['nonempty_index']}"
            for match in matches[:8]
        ]
        return {"row": row, "status": "ambiguous_target", "detail": f"{len(matches)} matches: {', '.join(locations)}"}

    record, _offset, end_offset = matches[0]
    return {
        "row": row,
        "status": "planned",
        "detail": f"p{record['paragraph_index']}/n{record['nonempty_index']}",
        "paragraph": record["paragraph"],
        "paragraph_index": record["paragraph_index"],
        "nonempty_index": record["nonempty_index"],
        "end_offset": end_offset,
        "citation": citation,
    }


def insert_after_sentence(root: ET.Element, row: dict[str, str]) -> tuple[str, str]:
    planned = resolve_insertion(paragraph_records(root), row)
    if planned["status"] != "planned":
        return str(planned["status"]), str(planned["detail"])
    insert_at_offset(planned["paragraph"], int(planned["end_offset"]), str(planned["citation"]))  # type: ignore[arg-type]
    return "inserted", str(planned["detail"])


def read_mapping(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--mapping", "-m", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.input.resolve() == args.output.resolve():
        parser.error("output must be a new file, not the source manuscript")

    rows = read_mapping(args.mapping)
    with zipfile.ZipFile(args.input) as archive:
        document_xml = archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    original_paragraph_texts = document_paragraph_texts(root)

    records = paragraph_records(root)
    planned_items = [resolve_insertion(records, row) for row in rows]
    seen_positions: dict[tuple[int, int], dict[str, object]] = {}
    for item in planned_items:
        if item["status"] != "planned":
            continue
        paragraph = item["paragraph"]
        position = (id(paragraph), int(item["end_offset"]))  # type: ignore[arg-type]
        if position in seen_positions:
            item["status"] = "duplicate_insert_position"
            item["detail"] = "same insertion position as " + str(seen_positions[position]["row"].get("citation_id", ""))
        else:
            seen_positions[position] = item

    for item in sorted(
        [item for item in planned_items if item["status"] == "planned"],
        key=lambda item: (int(item["paragraph_index"]), int(item["end_offset"])),
        reverse=True,
    ):
        insert_at_offset(item["paragraph"], int(item["end_offset"]), str(item["citation"]))  # type: ignore[arg-type]
        item["status"] = "inserted"

    preserved_paragraph_texts = document_paragraph_texts(root, skip_inserted_citations=True)
    preservation_issue = ""
    if preserved_paragraph_texts != original_paragraph_texts:
        mismatch_index = next(
            (
                index
                for index, (before, after) in enumerate(zip(original_paragraph_texts, preserved_paragraph_texts), start=1)
                if before != after
            ),
            min(len(original_paragraph_texts), len(preserved_paragraph_texts)) + 1,
        )
        preservation_issue = f"source_text_modified_at_paragraph_{mismatch_index}"
        for item in planned_items:
            if item["status"] == "inserted":
                item["status"] = "blocked_source_text_preservation"
                item["detail"] = preservation_issue

    report: list[dict[str, str]] = []
    for item in planned_items:
        row = item["row"]
        citation = row.get("temporary_citation", "")
        report.append(
            {
                "citation_id": row.get("citation_id", ""),
                "status": str(item["status"]),
                "detail": str(item["detail"]),
                "temporary_citation": citation,
                "target_sentence": row.get("target_sentence", ""),
                "paragraph_index": row.get("paragraph_index", ""),
                "nonempty_index": row.get("nonempty_index", ""),
                "target_occurrence": row.get("target_occurrence", ""),
            }
        )

    report_path = args.report or args.output.with_suffix(".insert_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    inserted = sum(1 for item in report if item["status"] == "inserted")
    failed = [f"{item['citation_id']}:{item['status']}" for item in report if item["status"] != "inserted"]
    if preservation_issue:
        print(f"Source text preservation failed: {preservation_issue}")
        print(f"Report: {report_path}")
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    clear_inserted_citation_markers(root)
    replacement = ET.tostring(root, encoding="utf-8", xml_declaration=True, standalone=True)
    with zipfile.ZipFile(args.input, "r") as src, zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename == "word/document.xml":
                dst.writestr(item, replacement)
            else:
                dst.writestr(item, src.read(item.filename))

    print(f"Inserted {inserted}/{len(report)} temporary citation groups into {args.output}")
    if failed:
        print("Uninserted citation ids: " + ", ".join(failed))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
