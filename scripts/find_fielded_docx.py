#!/usr/bin/env python3
"""Scan folders for DOCX files that already contain editable EndNote fields."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from inspect_docx_fields import inspect


def scan_docx(path: Path) -> dict[str, object]:
    try:
        report = inspect(path)
        issues = list(report.get("issues", []))
        has_field_markers = bool(report["field_counts"]["begin"] and report["field_counts"]["end"])  # type: ignore[index]
        fielded = bool(report["endnote_cite_fields"] and report["endnote_reflist_fields"] and has_field_markers)
        clean = (
            fielded
            and report["temporary_citation_residue"] == 0
            and report["placeholder_residue"] == 0
            and not issues
        )
        return {
            "path": str(path),
            "status": "fielded_clean" if clean else ("fielded_needs_review" if fielded else "not_fielded"),
            "endnote_cite_fields": report["endnote_cite_fields"],
            "endnote_reflist_fields": report["endnote_reflist_fields"],
            "field_begin": report["field_counts"]["begin"],  # type: ignore[index]
            "field_separate": report["field_counts"]["separate"],  # type: ignore[index]
            "field_end": report["field_counts"]["end"],  # type: ignore[index]
            "temporary_citation_residue": report["temporary_citation_residue"],
            "placeholder_residue": report["placeholder_residue"],
            "reference_heading_count": report["reference_heading_count"],
            "issues": "; ".join(issues),
        }
    except Exception as exc:  # noqa: BLE001 - scanner should keep going across mixed folders.
        return {
            "path": str(path),
            "status": "unreadable",
            "endnote_cite_fields": 0,
            "endnote_reflist_fields": 0,
            "field_begin": 0,
            "field_separate": 0,
            "field_end": 0,
            "temporary_citation_residue": 0,
            "placeholder_residue": 0,
            "reference_heading_count": 0,
            "issues": str(exc),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Folder to scan recursively.")
    parser.add_argument("--output", type=Path, help="Optional CSV report path.")
    parser.add_argument("--all", action="store_true", help="Include non-fielded DOCX files.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    if not args.root.exists():
        parser.error(f"root not found: {args.root}")

    rows = []
    for docx in sorted(args.root.rglob("*.docx")):
        if docx.name.startswith("~$"):
            continue
        row = scan_docx(docx)
        if args.all or row["status"] != "not_fielded":
            rows.append(row)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["path", "status"])
            writer.writeheader()
            writer.writerows(rows)

    if args.as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            print(
                f"{row['status']}: {row['path']} "
                f"(cite={row['endnote_cite_fields']}, reflist={row['endnote_reflist_fields']}, "
                f"begin/separate/end={row['field_begin']}/{row['field_separate']}/{row['field_end']})"
            )
        print(f"Scanned {args.root}; reported {len(rows)} DOCX file(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
