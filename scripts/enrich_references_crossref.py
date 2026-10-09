#!/usr/bin/env python3
"""Enrich ENW and candidate-table metadata from Crossref title queries."""

from __future__ import annotations
from crossref_http import fetch_json

import argparse
import csv
import difflib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

NO_ISSUE_VALUE = "not assigned"


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", html.unescape(text).lower()).strip()


def first_year(item: dict) -> str:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = item.get(key, {}).get("date-parts") if isinstance(item.get(key), dict) else None
        if parts and parts[0]:
            value = parts[0][0]
            return str(value) if value is not None else ""
    return ""


def authors_from_item(item: dict) -> list[str]:
    authors = []
    for author in item.get("author", []) or []:
        given = author.get("given", "")
        family = author.get("family", "")
        name = " ".join(part for part in [given, family] if part).strip()
        if name:
            authors.append(name)
    return authors


def parse_enw(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    current: dict[str, object] = {}
    order: list[str] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            if current:
                current["_order"] = order
                records.append(current)
                current = {}
                order = []
            continue
        if not line.startswith("%") or len(line) < 3:
            continue
        tag = line[1]
        value = html.unescape(line[3:].strip())
        if tag == "0" and current:
            current["_order"] = order
            records.append(current)
            current = {}
            order = []
        order.append(tag)
        if tag == "A":
            current.setdefault("A", []).append(value)
        else:
            current[tag] = value
    if current:
        current["_order"] = order
        records.append(current)
    return records


def record_title(record: dict[str, object]) -> str:
    return str(record.get("T", "")).strip()


def record_authors(record: dict[str, object]) -> list[str]:
    return [str(item) for item in record.get("A", [])] if isinstance(record.get("A"), list) else []


def record_year(record: dict[str, object]) -> str:
    return str(record.get("D", "")).strip()[:4]


def record_source(record: dict[str, object]) -> str:
    return str(record.get("J") or record.get("B") or record.get("I") or "").strip()


def is_journal_record(record: dict[str, object]) -> bool:
    record_type = str(record.get("0", "")).lower()
    return "journal" in record_type or bool(str(record.get("J", "")).strip())


def has_value(record: dict[str, object], tag: str) -> bool:
    return bool(str(record.get(tag, "")).strip())


def metadata_gaps(record: dict[str, object]) -> list[str]:
    gaps: list[str] = []
    if not has_value(record, "R") and not has_value(record, "U"):
        gaps.append("DOI/URL")
    if is_journal_record(record):
        if not has_value(record, "J"):
            gaps.append("journal")
        if not has_value(record, "V"):
            gaps.append("volume")
        if not has_value(record, "N"):
            gaps.append("issue")
        if not has_value(record, "P"):
            gaps.append("pages/article number")
    return gaps


def needs_crossref(record: dict[str, object]) -> bool:
    return bool(metadata_gaps(record))


def crossref_query(record: dict[str, object], rows: int, timeout: int) -> list[dict]:
    authors = record_authors(record)
    first_author = authors[0].split(",")[0] if authors else ""
    query = " ".join(
        part
        for part in [
            first_author,
            record_year(record),
            record_title(record),
            record_source(record),
        ]
        if part
    )
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode({"query.bibliographic": query, "rows": str(rows)})
    data = fetch_json(url, timeout=timeout)
    return data.get("message", {}).get("items", [])


def score_item(record: dict[str, object], item: dict) -> tuple[float, dict[str, object]]:
    title = record_title(record)
    source = record_source(record)
    year = record_year(record)
    authors = record_authors(record)
    first_surname = normalize(authors[0].split(",")[0]) if authors else ""

    item_title = html.unescape((item.get("title") or [""])[0])
    item_source = html.unescape((item.get("container-title") or [""])[0])
    item_year = first_year(item)
    item_authors = authors_from_item(item)
    item_surnames = " ".join(normalize(author.split()[-1]) for author in item_authors)

    title_ratio = difflib.SequenceMatcher(None, normalize(title), normalize(item_title)).ratio()
    source_ratio = difflib.SequenceMatcher(None, normalize(source), normalize(item_source)).ratio() if source else 0.0
    try:
        close_year = bool(year and item_year and abs(int(item_year) - int(year)) <= 1)
    except ValueError:
        close_year = False
    year_score = 1.0 if year and item_year == year else 0.25 if close_year else 0.0
    author_score = 1.0 if first_surname and first_surname in item_surnames else 0.0
    score = (title_ratio * 4.0) + year_score + author_score + (source_ratio * 0.5)
    return score, {
        "title_ratio": round(title_ratio, 3),
        "source_ratio": round(source_ratio, 3),
        "year_score": year_score,
        "author_score": author_score,
        "crossref_title": item_title,
        "crossref_source": item_source,
        "crossref_year": item_year,
    }


def best_crossref_match(record: dict[str, object], rows: int, timeout: int) -> tuple[dict | None, dict[str, object]]:
    try:
        items = crossref_query(record, rows=rows, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - report query failures without stopping the batch.
        return None, {"status": "query_error", "error": str(exc)}
    ranked = []
    for item in items:
        score, details = score_item(record, item)
        ranked.append((score, item, details))
    ranked.sort(key=lambda part: part[0], reverse=True)
    if not ranked:
        return None, {"status": "not_found"}
    score, item, details = ranked[0]
    title_ratio = float(details["title_ratio"])
    accepted = title_ratio >= 0.88 or (title_ratio >= 0.82 and bool(details["year_score"]) and bool(details["author_score"]))
    details["score"] = round(score, 3)
    details["status"] = "accepted" if accepted else "low_confidence"
    return (item if accepted else None), details


def update_record(record: dict[str, object], item: dict | None) -> dict[str, str]:
    report = {
        "title": record_title(record),
        "year": record_year(record),
        "source": record_source(record),
        "old_doi": str(record.get("R", "")).strip(),
        "new_doi": "",
        "new_url": "",
        "filled_fields": "",
    }
    if not item:
        return report

    filled: list[str] = []
    doi = str(item.get("DOI", "")).strip()
    if doi and not str(record.get("R", "")).strip():
        record["R"] = doi
        filled.append("doi")
    if doi and not str(record.get("U", "")).strip():
        record["U"] = "https://doi.org/" + doi
        filled.append("url")
    if item.get("volume") and not str(record.get("V", "")).strip():
        record["V"] = str(item["volume"])
        filled.append("volume")
    if not str(record.get("N", "")).strip():
        if item.get("issue"):
            record["N"] = str(item["issue"])
            filled.append("issue")
        elif is_journal_record(record):
            record["N"] = NO_ISSUE_VALUE
            filled.append("issue:not_assigned")
    page_or_article = item.get("page") or item.get("article-number")
    if page_or_article and not str(record.get("P", "")).strip():
        record["P"] = str(page_or_article)
        filled.append("pages")
    if (item.get("container-title") or [""])[0] and not str(record.get("J", "")).strip():
        record["J"] = html.unescape((item.get("container-title") or [""])[0])
        filled.append("journal")

    report["new_doi"] = str(record.get("R", "")).strip()
    report["new_url"] = str(record.get("U", "")).strip()
    report["metadata_gaps"] = ";".join(metadata_gaps(record))
    report["filled_fields"] = ";".join(filled)
    return report


def write_enw(records: list[dict[str, object]], path: Path) -> None:
    tag_order = ["0", "T", "A", "J", "B", "V", "N", "P", "D", "R", "U", "I"]
    lines: list[str] = []
    for record in records:
        written: set[str] = set()
        for tag in tag_order:
            if tag == "N" and str(record.get(tag, "")).strip().lower() == "not assigned":
                written.add(tag)
                continue
            if tag == "A":
                for author in record.get("A", []) if isinstance(record.get("A"), list) else []:
                    lines.append(f"%A {author}")
                written.add("A")
            elif str(record.get(tag, "")).strip():
                lines.append(f"%{tag} {record[tag]}")
                written.add(tag)
        for tag in record.get("_order", []) if isinstance(record.get("_order"), list) else []:
            if tag in written or tag in {"A"}:
                continue
            if str(record.get(tag, "")).strip():
                lines.append(f"%{tag} {record[tag]}")
                written.add(tag)
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def enrich_candidate_table(input_csv: Path, output_csv: Path, records: list[dict[str, object]], details_by_title: dict[str, dict[str, object]]) -> None:
    by_title = {normalize(record_title(record)): record for record in records}
    with input_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    for extra in ["final_url", "volume", "issue", "pages", "metadata_status", "verification_source"]:
        if extra not in fieldnames:
            fieldnames.append(extra)
    if "enw_type" in fieldnames:
        pass
    for row in rows:
        title_key = normalize(row.get("final_title", ""))
        record = by_title.get(title_key)
        details = details_by_title.get(title_key, {})
        if record:
            row["final_doi"] = row.get("final_doi") or str(record.get("R", "")).strip()
            row["final_url"] = str(record.get("U", "")).strip()
            row["volume"] = str(record.get("V", "")).strip()
            row["issue"] = str(record.get("N", "")).strip()
            row["pages"] = str(record.get("P", "")).strip()
            row["metadata_status"] = str(details.get("status", ""))
            row["verification_source"] = "Crossref" if str(record.get("R", "")).strip() else ""
            if row.get("enw_type") == "Book Section" and str(record.get("0", "")).lower() == "journal article":
                row["enw_type"] = "Journal Article"
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enw", type=Path, required=True)
    parser.add_argument("--output-enw", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate-table", type=Path)
    parser.add_argument("--output-candidate-table", type=Path)
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args(argv)

    records = parse_enw(args.enw)
    report_rows: list[dict[str, object]] = []
    details_by_title: dict[str, dict[str, object]] = {}
    for index, record in enumerate(records, start=1):
        item = None
        details: dict[str, object] = {"status": "already_complete"}
        if needs_crossref(record):
            item, details = best_crossref_match(record, rows=args.rows, timeout=args.timeout)
            time.sleep(args.sleep)
        update = update_record(record, item)
        details_by_title[normalize(record_title(record))] = details
        report_rows.append({"index": index, **update, **details})

    write_enw(records, args.output_enw)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in report_rows for key in row.keys()})
    with args.report.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)

    if args.candidate_table and args.output_candidate_table:
        enrich_candidate_table(args.candidate_table, args.output_candidate_table, records, details_by_title)

    incomplete = [(record_title(record), metadata_gaps(record)) for record in records if metadata_gaps(record)]
    missing_links = [title for title, gaps in incomplete if "DOI/URL" in gaps]
    print(f"Processed {len(records)} ENW records; incomplete metadata after enrichment: {len(incomplete)}")
    print(f"Missing DOI/URL after enrichment: {len(missing_links)}")
    if incomplete:
        for title, gaps in incomplete[:20]:
            print(f"- {title}: {', '.join(gaps)}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
