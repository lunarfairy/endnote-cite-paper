#!/usr/bin/env python3
"""Inspect DOCX EndNote fields, field balance, and placeholder residue."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEMP_CITATION_RE = re.compile(r"\{[^{}]{1,120}#[0-9]+[^{}]{0,120}\}")
PLACEHOLDER_RE = re.compile(r"\b(TODO|CITATION_NEEDED|NEEDS_CITATION|PLACEHOLDER)\b|\[citation[^\]]*\]", re.I)
REFERENCE_HEADING_RE = re.compile(r"(?:references?|参考文献)", re.I)
ENDNOTE_COMMAND_RE = re.compile(r"^\s*ADDIN\s+(EN\.(?:CITE(?:\.DATA)?|REFLIST))(?=\s|<|$)", re.I)


def field_command(instruction: str) -> str:
    match = ENDNOTE_COMMAND_RE.match(instruction)
    return match.group(1).upper() if match else ""


def load_document_xml(docx: Path) -> str:
    with zipfile.ZipFile(docx) as archive:
        return archive.read("word/document.xml").decode("utf-8", errors="replace")


def paragraph_texts(document_xml: str) -> list[str]:
    root = ET.fromstring(document_xml.encode("utf-8"))
    texts: list[str] = []
    for para in root.findall(".//w:p", NS):
        text = "".join(node.text or "" for node in para.findall(".//w:t", NS)).strip()
        if text:
            texts.append(text)
    return texts


def bibliography_entries(texts: list[str]) -> list[str]:
    reference_heading_indexes = [
        index
        for index, text in enumerate(texts)
        if REFERENCE_HEADING_RE.fullmatch(text.strip())
    ]
    if not reference_heading_indexes:
        return []
    start = reference_heading_indexes[-1] + 1
    return [text for text in texts[start:] if text.strip()]


def field_instruction_nodes(document_xml: str) -> list[str]:
    root = ET.fromstring(document_xml.encode("utf-8"))
    return [node.text or "" for node in root.findall(".//w:instrText", NS)]


def field_records(document_xml: str) -> list[dict]:
    """Read real fields in opening order; DATA belongs to its parent citation."""
    root = ET.fromstring(document_xml.encode("utf-8"))
    records: list[dict] = []
    stack: list[dict] = []
    for node in root.iter():
        if node.tag == W + "fldChar":
            kind = node.attrib.get(W + "fldCharType", "")
            if kind == "begin":
                record = {"instruction": "", "payloads": [], "closed": False}
                data = node.find(W + "fldData")
                if data is not None:
                    record["payloads"].append(data.text or "")
                records.append(record)
                stack.append(record)
            elif kind == "end" and stack:
                record = stack.pop()
                record["closed"] = True
                if field_command(record["instruction"]) == "EN.CITE.DATA" and stack:
                    stack[-1]["payloads"].extend(record["payloads"])
        elif node.tag == W + "instrText":
            if stack:
                stack[-1]["instruction"] += node.text or ""
    for node in root.findall(".//w:fldSimple", NS):
        instruction = node.attrib.get(W + "instr", "")
        if instruction:
            records.append({"instruction": instruction, "payloads": [], "closed": True})
    return [record for record in records if record["closed"]]


def field_instruction_groups(document_xml: str) -> list[str]:
    return [record["instruction"] for record in field_records(document_xml)]


def field_instruction_text(document_xml: str) -> str:
    groups = field_instruction_groups(document_xml)
    return "\n".join(groups)


def endnote_cite_group_sizes(document_xml: str) -> list[int]:
    return citation_payload_stats(document_xml)[0]


def citation_payload_stats(document_xml: str) -> tuple[list[int], list[str]]:
    sizes: list[int] = []
    issues: list[str] = []
    for record in field_records(document_xml):
        instruction = record["instruction"]
        if field_command(instruction) != "EN.CITE":
            continue
        payloads: list[str] = []
        index = len(sizes) + 1
        start = instruction.find("<EndNote")
        if start >= 0:
            payloads.append(instruction[start:].strip())
        for raw in record["payloads"]:
            try:
                payloads.append(base64.b64decode(re.sub(r"\s+", "", raw), validate=True).rstrip(b"\0").decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                issues.append(f"cite field {index}: invalid encoded payload ({exc})")
        counts = []
        for payload in payloads:
            try:
                root = ET.fromstring(payload)
                if root.tag != "EndNote":
                    raise ValueError("expected EndNote XML root")
                counts.append(len(root.findall("./Cite")))
            except (ET.ParseError, ValueError) as exc:
                issues.append(f"cite field {index}: invalid XML payload ({exc})")
        if not counts or not all(counts):
            issues.append(f"cite field {index}: missing embedded Cite records")
        if len(set(counts)) > 1:
            issues.append(f"cite field {index}: conflicting inline/encoded record counts")
        sizes.append(max(counts, default=0))
    return sizes, issues


def field_balance(document_xml: str) -> tuple[dict[str, int], list[str]]:
    root = ET.fromstring(document_xml.encode("utf-8"))
    counts = {"begin": 0, "separate": 0, "end": 0}
    issues: list[str] = []
    depth = 0
    for node in root.findall(".//w:fldChar", NS):
        kind = node.attrib.get(W + "fldCharType", "")
        if kind in counts:
            counts[kind] += 1
        if kind == "begin":
            depth += 1
        elif kind == "end":
            depth -= 1
            if depth < 0:
                issues.append("field end appears before matching begin")
                depth = 0
    if depth:
        issues.append(f"{depth} field begin marker(s) not closed")
    if counts["begin"] != counts["end"]:
        issues.append("field begin/end counts differ")
    if counts["begin"] and counts["separate"] == 0:
        issues.append("fields exist but no separate markers found")
    return counts, issues


def mapping_stats(path: Path, max_refs_per_group: int = 5) -> dict[str, object]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])

    if "reference_ids" not in fieldnames and "insert_group" in fieldnames:
        group_counts: dict[str, int] = {}
        for row in rows:
            group = row.get("insert_group", "").strip()
            if group:
                group_counts[group] = group_counts.get(group, 0) + 1
        refs = {
            (
                row.get("final_doi", "").strip().lower()
                or "|".join(
                    [
                        row.get("final_title", "").strip().lower(),
                        row.get("final_authors", "").strip().lower(),
                        row.get("final_year", "").strip(),
                    ]
                )
            )
            for row in rows
        }
        refs.discard("")
        over_limit = {group: count for group, count in group_counts.items() if count > max_refs_per_group}
        return {
            "citation_rows": len(group_counts) if group_counts else len(rows),
            "unique_references": len(refs),
            "over_limit_groups": over_limit,
        }

    refs: set[str] = set()
    over_limit: dict[str, int] = {}
    for row in rows:
        ids = [rid.strip() for rid in re.split(r"\s*;\s*|\s*\|\s*", row.get("reference_ids", "")) if rid.strip()]
        group = row.get("citation_id", "").strip() or row.get("insert_group", "").strip() or str(len(over_limit) + 1)
        if len(ids) > max_refs_per_group:
            over_limit[group] = len(ids)
        for rid in ids:
            if rid.strip():
                refs.add(rid.strip())
    return {
        "citation_rows": len(rows),
        "unique_references": len(refs),
        "over_limit_groups": over_limit,
    }


def inspect(docx: Path, mapping: Path | None = None, max_refs_per_group: int = 5) -> dict[str, object]:
    document_xml = load_document_xml(docx)
    texts = paragraph_texts(document_xml)
    plain_text = "\n".join(texts)
    bib_entries = bibliography_entries(texts)
    commands = [field_command(code) for code in field_instruction_groups(document_xml)]
    cite_group_sizes, payload_issues = citation_payload_stats(document_xml)
    counts, balance_issues = field_balance(document_xml)
    over_limit_cite_fields = {
        str(index): size
        for index, size in enumerate(cite_group_sizes, start=1)
        if size > max_refs_per_group
    }
    report: dict[str, object] = {
        "docx": str(docx),
        "paragraphs": len(texts),
        "endnote_cite_fields": commands.count("EN.CITE"),
        "endnote_reflist_fields": commands.count("EN.REFLIST"),
        "field_counts": counts,
        "endnote_cite_group_sizes": cite_group_sizes,
        "endnote_over_limit_cite_fields": over_limit_cite_fields,
        "temporary_citation_residue": len(TEMP_CITATION_RE.findall(plain_text)),
        "placeholder_residue": len(PLACEHOLDER_RE.findall(plain_text)),
        "reference_heading_count": sum(1 for text in texts if REFERENCE_HEADING_RE.fullmatch(text.strip())),
        "bibliography_entry_count": len(bib_entries),
        "bibliography_entries_preview": bib_entries[:5],
        "issues": balance_issues + payload_issues,
    }
    if mapping:
        stats = mapping_stats(mapping, max_refs_per_group=max_refs_per_group)
        report["mapping_citation_rows"] = stats["citation_rows"]
        report["mapping_unique_references"] = stats["unique_references"]
        report["mapping_over_limit_groups"] = stats["over_limit_groups"]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--expected-citations", type=int)
    parser.add_argument("--expected-references", type=int)
    parser.add_argument("--max-refs-per-group", type=int, default=5)
    parser.add_argument("--allow-temporary", action="store_true")
    parser.add_argument("--no-require-endnote", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    if not args.docx.exists():
        parser.error(f"DOCX not found: {args.docx}")
    if args.mapping and not args.mapping.exists():
        parser.error(f"mapping not found: {args.mapping}")

    report = inspect(args.docx, args.mapping, max_refs_per_group=args.max_refs_per_group)
    issues = list(report["issues"])  # type: ignore[arg-type]

    if not args.no_require_endnote:
        if report["endnote_cite_fields"] == 0:
            issues.append("missing ADDIN EN.CITE fields")
        if report["endnote_reflist_fields"] == 0:
            issues.append("missing ADDIN EN.REFLIST field")
    if not args.allow_temporary and report["temporary_citation_residue"]:
        issues.append("temporary citation placeholders remain")
    if report["placeholder_residue"]:
        issues.append("placeholder markers remain")
    if args.expected_citations is not None and report["endnote_cite_fields"] != args.expected_citations:
        issues.append(f"expected {args.expected_citations} cite fields, found {report['endnote_cite_fields']}")
    if args.mapping and args.expected_references is not None and report.get("mapping_unique_references") != args.expected_references:
        issues.append(f"expected {args.expected_references} unique references in mapping")
    expected_bibliography_entries = args.expected_references if args.expected_references is not None else report.get("mapping_unique_references")
    if (
        expected_bibliography_entries is not None
        and report["bibliography_entry_count"] != expected_bibliography_entries
    ):
        issues.append(
            "visible bibliography entry count differs from expected references: "
            f"{report['bibliography_entry_count']} vs {expected_bibliography_entries}"
        )
    if args.mapping and report["endnote_cite_fields"] and report["endnote_cite_fields"] != report.get("mapping_citation_rows"):
        issues.append("EndNote cite field count differs from mapping row count")
    if args.mapping and report.get("mapping_over_limit_groups"):
        issues.append(f"citation group(s) exceed {args.max_refs_per_group} references: {report['mapping_over_limit_groups']}")
    if report.get("endnote_over_limit_cite_fields"):
        issues.append(f"DOCX EndNote cite field(s) exceed {args.max_refs_per_group} references: {report['endnote_over_limit_cite_fields']}")

    report["issues"] = issues

    if args.as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"DOCX: {report['docx']}")
        print(f"Paragraphs: {report['paragraphs']}")
        print(f"EndNote cite fields: {report['endnote_cite_fields']}")
        print(f"EndNote reference-list fields: {report['endnote_reflist_fields']}")
        print(f"Field counts: {report['field_counts']}")
        print(f"EndNote cite group sizes: {report['endnote_cite_group_sizes']}")
        print(f"EndNote over-limit cite fields: {report['endnote_over_limit_cite_fields']}")
        print(f"Temporary citation residue: {report['temporary_citation_residue']}")
        print(f"Placeholder residue: {report['placeholder_residue']}")
        print(f"Reference heading count: {report['reference_heading_count']}")
        print(f"Visible bibliography entries: {report['bibliography_entry_count']}")
        if args.mapping:
            print(f"Mapping citation rows: {report['mapping_citation_rows']}")
            print(f"Mapping unique references: {report['mapping_unique_references']}")
            print(f"Mapping over-limit groups: {report['mapping_over_limit_groups']}")
        if issues:
            print("Issues:")
            for issue in issues:
                print(f"- {issue}")
        else:
            print("No issues found.")

    return 1 if args.strict and issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
