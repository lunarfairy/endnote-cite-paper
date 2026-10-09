#!/usr/bin/env python3
"""Package EndNote citation deliverables into a collaborator zip."""

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def add_file(archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    archive.write(path, arcname)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docx", type=Path, required=True)
    parser.add_argument("--enw", type=Path, required=True)
    parser.add_argument("--candidate-table", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output-zip", type=Path, required=True)
    parser.add_argument("--extra", type=Path, action="append", default=[])
    args = parser.parse_args(argv)

    files = {
        "final_docx": args.docx,
        "combined_enw": args.enw,
        "candidate_table": args.candidate_table,
        "insertion_mapping": args.mapping,
        "pdf_preview": args.pdf,
    }
    for extra_index, extra in enumerate(args.extra, start=1):
        files[f"extra_{extra_index}_{extra.name}"] = extra

    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise SystemExit("Missing required file(s): " + "; ".join(missing))

    args.output_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "files": {key: path.name for key, path in files.items()},
    }
    with zipfile.ZipFile(args.output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        add_file(archive, args.docx, f"docx/{args.docx.name}")
        add_file(archive, args.enw, f"endnote/{args.enw.name}")
        add_file(archive, args.candidate_table, f"tables/{args.candidate_table.name}")
        add_file(archive, args.mapping, f"tables/{args.mapping.name}")
        add_file(archive, args.pdf, f"preview/{args.pdf.name}")
        for extra in args.extra:
            add_file(archive, extra, f"extra/{extra.name}")
    print(f"Wrote package: {args.output_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
