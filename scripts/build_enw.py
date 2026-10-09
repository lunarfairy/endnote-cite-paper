#!/usr/bin/env python3
"""Build an EndNote Import .enw file from verified references."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

PREPRINT_MARKERS = (
    "arxiv",
    "ssrn",
    "biorxiv",
    "medrxiv",
    "preprint",
    "researchgate",
)

FIELD_ALIASES = {
    "reference_type": "type",
    "source": "journal",
    "publication": "journal",
    "container_title": "journal",
    "doi_url": "url",
}


def split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*;\s*|\s*\|\s*", text) if part.strip()]


def normalize_record(row: dict[str, Any], index: int) -> dict[str, Any]:
    normalized = {
        FIELD_ALIASES.get(str(k).strip(), str(k).strip()): html.unescape(v) if isinstance(v, str) else v
        for k, v in row.items()
    }
    normalized.setdefault("id", f"ref_{index:03d}")
    normalized.setdefault("type", "Journal Article")
    normalized["authors"] = split_values(normalized.get("authors") or normalized.get("author"))
    normalized["keywords"] = split_values(normalized.get("keywords"))
    normalized["record_number"] = str(normalized.get("record_number") or index).strip()
    return normalized


def load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("references", [])
        if not isinstance(data, list):
            raise ValueError("JSON input must be a list or an object with a references list")
        return [normalize_record(dict(row), i) for i, row in enumerate(data, start=1)]

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [normalize_record(dict(row), i) for i, row in enumerate(reader, start=1)]


def is_truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "verified"}


def venue(record: dict[str, Any]) -> str:
    return str(record.get("journal") or record.get("publisher") or record.get("book_title") or "").strip()


def validate(records: list[dict[str, Any]], allow_preprints: bool, allow_unverified: bool) -> list[str]:
    issues: list[str] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        rid = str(record.get("id", "")).strip()
        label = rid or f"row {index}"
        if not rid:
            issues.append(f"{label}: missing id")
        if rid in seen_ids:
            issues.append(f"{label}: duplicate id")
        seen_ids.add(rid)
        for field in ("title", "year"):
            if not str(record.get(field, "")).strip():
                issues.append(f"{label}: missing {field}")
        if not record.get("authors"):
            issues.append(f"{label}: missing authors")
        if not venue(record):
            issues.append(f"{label}: missing journal/publisher")
        if not (str(record.get("doi", "")).strip() or str(record.get("url", "")).strip()):
            issues.append(f"{label}: missing DOI or official URL")
        record_type = str(record.get("type", "")).lower()
        if any(word in record_type for word in ("journal", "article", "review")):
            if not str(record.get("journal", "")).strip():
                issues.append(f"{label}: journal article missing journal")
            if not str(record.get("volume", "")).strip():
                issues.append(f"{label}: journal article missing volume")
            if not str(record.get("issue", "")).strip():
                issues.append(f"{label}: journal article missing issue; use 'not assigned' only when publisher/Crossref has no issue")
            if not (str(record.get("pages", "")).strip() or str(record.get("article_number", "")).strip()):
                issues.append(f"{label}: journal article missing pages or article number")
        if not allow_unverified and not is_truthy(record.get("verified")):
            issues.append(f"{label}: verified must be true")
        haystack = " ".join(str(record.get(key, "")) for key in ("type", "title", "journal", "publisher", "url")).lower()
        if not allow_preprints and any(marker in haystack for marker in PREPRINT_MARKERS):
            issues.append(f"{label}: appears to be a preprint or disallowed source")
    return issues


def add_line(lines: list[str], tag: str, value: Any) -> None:
    text = str(value or "").strip()
    if text:
        lines.append(f"{tag} {text}")


def to_enw(record: dict[str, Any]) -> str:
    lines: list[str] = []
    add_line(lines, "%0", record.get("type") or "Journal Article")
    for author in record.get("authors", []):
        add_line(lines, "%A", author)
    add_line(lines, "%D", record.get("year"))
    add_line(lines, "%T", record.get("title"))
    add_line(lines, "%J", record.get("journal"))
    add_line(lines, "%B", record.get("book_title"))
    add_line(lines, "%I", record.get("publisher"))
    add_line(lines, "%V", record.get("volume"))
    if str(record.get("issue", "")).strip().lower() != "not assigned":
        add_line(lines, "%N", record.get("issue"))
    add_line(lines, "%P", record.get("pages") or record.get("article_number"))
    add_line(lines, "%R", record.get("doi"))
    add_line(lines, "%U", record.get("url"))
    for keyword in record.get("keywords", []):
        add_line(lines, "%K", keyword)
    add_line(lines, "%Z", record.get("notes"))
    add_line(lines, "%Z", f"source_id: {record.get('id')}")
    return "\n".join(lines)


def write_record_map(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "record_number", "author", "year", "title"])
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "id": record.get("id"),
                    "record_number": record.get("record_number"),
                    "author": record.get("authors", [""])[0] if record.get("authors") else "",
                    "year": record.get("year", ""),
                    "title": record.get("title", ""),
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", type=Path, required=True, help="Reference CSV or JSON")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output .enw path")
    parser.add_argument("--record-map", type=Path, help="Optional CSV with provisional record numbers")
    parser.add_argument("--allow-preprints", action="store_true")
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args(argv)

    records = load_records(args.input)
    issues = validate(records, args.allow_preprints, args.allow_unverified)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n\n".join(to_enw(record) for record in records) + "\n", encoding="utf-8")
    if args.record_map:
        write_record_map(records, args.record_map)
    print(f"Wrote {len(records)} references to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
