#!/usr/bin/env python3
"""Build EndNote temporary citation groups and insertion mapping."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ANCHOR_FIELDS = [
    "paragraph_index",
    "nonempty_index",
    "target_occurrence",
    "anchor_before",
    "anchor_after",
]


def split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in re.split(r"\s*;\s*|\s*\|\s*", str(value).strip()) if part.strip()]


def load_table(path: Path, top_key: str | None = None) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and top_key:
            data = data.get(top_key, [])
        if not isinstance(data, list):
            raise ValueError(f"{path} must contain a list")
        return [dict(row) for row in data]
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def last_name(author: str) -> str:
    author = author.strip()
    if not author:
        return "Unknown"
    if "," in author:
        return author.split(",", 1)[0].strip()
    parts = re.split(r"\s+", author)
    return parts[-1].strip()


def normalize_reference(row: dict[str, Any], index: int) -> dict[str, Any]:
    authors = split_values(row.get("authors") or row.get("author"))
    return {
        **row,
        "id": str(row.get("id") or f"ref_{index:03d}").strip(),
        "authors": authors,
        "year": str(row.get("year", "")).strip(),
        "record_number": str(row.get("record_number") or index).strip(),
    }


def temporary_piece(reference: dict[str, Any]) -> str:
    author = last_name(reference.get("authors", [""])[0] if reference.get("authors") else "")
    year = reference.get("year") or "n.d."
    record_number = reference.get("record_number")
    return f"{author}, {year} #{record_number}"


def compress_numbers(numbers: list[int]) -> str:
    if not numbers:
        return "[]"
    numbers = sorted(dict.fromkeys(numbers))
    ranges: list[str] = []
    start = prev = numbers[0]
    for number in numbers[1:]:
        if number == prev + 1:
            prev = number
            continue
        ranges.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = number
    ranges.append(str(start) if start == prev else f"{start}-{prev}")
    return "[" + ",".join(ranges) + "]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--needs", type=Path, required=True, help="Citation-needs CSV or JSON")
    parser.add_argument("--references", type=Path, required=True, help="Confirmed references CSV or JSON")
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--max-per-location", type=int, default=5)
    parser.add_argument("--allow-unresolved", action="store_true", help="Allow citation needs with blank reference_ids.")
    parser.add_argument("--unresolved-report", type=Path, help="Optional CSV report for citation needs with blank reference_ids.")
    args = parser.parse_args(argv)

    references = [normalize_reference(row, i) for i, row in enumerate(load_table(args.references, "references"), start=1)]
    ref_by_id = {str(ref["id"]): ref for ref in references}
    needs = load_table(args.needs, "citation_needs")

    final_numbers: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    unresolved: list[dict[str, Any]] = []
    for index, need in enumerate(needs, start=1):
        citation_id = str(need.get("citation_id") or f"cite_{index:03d}").strip()
        ref_ids = split_values(need.get("reference_ids"))
        if not ref_ids:
            unresolved.append(
                {
                    "citation_id": citation_id,
                    "chapter": need.get("chapter", ""),
                    **{field: need.get(field, "") for field in ANCHOR_FIELDS},
                    "target_sentence": need.get("target_sentence", ""),
                    "support_claim": need.get("support_claim", ""),
                    "reason": "missing reference_ids",
                }
            )
            if not args.allow_unresolved:
                issues.append(f"{citation_id}: missing reference_ids")
            continue
        if len(ref_ids) > args.max_per_location:
            issues.append(f"{citation_id}: has {len(ref_ids)} references; max is {args.max_per_location}")
        missing = [rid for rid in ref_ids if rid not in ref_by_id]
        if missing:
            issues.append(f"{citation_id}: unknown reference ids: {', '.join(missing)}")
            continue
        for rid in ref_ids:
            if rid not in final_numbers:
                final_numbers[rid] = len(final_numbers) + 1
        refs = [ref_by_id[rid] for rid in ref_ids]
        final_group = compress_numbers([final_numbers[rid] for rid in ref_ids])
        rows.append(
            {
                "citation_id": citation_id,
                "chapter": need.get("chapter", ""),
                **{field: need.get(field, "") for field in ANCHOR_FIELDS},
                "target_sentence": need.get("target_sentence", ""),
                "support_claim": need.get("support_claim", ""),
                "suggested_keywords": need.get("suggested_keywords", ""),
                "recommended_literature_type": need.get("recommended_literature_type", ""),
                "reference_ids": ";".join(ref_ids),
                "reference_count": str(len(ref_ids)),
                "temporary_citation": "{" + ";".join(temporary_piece(ref) for ref in refs) + "}",
                "expected_numbered_citation": final_group,
            }
        )

    if args.unresolved_report:
        args.unresolved_report.parent.mkdir(parents=True, exist_ok=True)
        with args.unresolved_report.open("w", newline="", encoding="utf-8-sig") as handle:
            fieldnames = [
                "citation_id",
                "chapter",
                *ANCHOR_FIELDS,
                "target_sentence",
                "support_claim",
                "reason",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unresolved)

    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = [
            "citation_id",
            "chapter",
            *ANCHOR_FIELDS,
            "target_sentence",
            "support_claim",
            "suggested_keywords",
            "recommended_literature_type",
            "reference_ids",
            "reference_count",
            "temporary_citation",
            "expected_numbered_citation",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} citation mappings to {args.output}")
    print(f"Unique references in first-appearance order: {len(final_numbers)}")
    if unresolved:
        print(f"Unresolved citation needs skipped: {len(unresolved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
