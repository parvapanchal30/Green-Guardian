"""CSV import of dataset samples: parsing and row validation. Pure: no database, no network, no file system.

Design rules
* Import registers sample METADATA (identifier, group, label, fingerprints, provenance). It never carries review state:
  every imported label is `unreviewed`, and a column that tries to carry review state (label_status, reviewed, validated,
  reviewer ...) is a file-level error, so a spreadsheet can never smuggle labels in as validated.
* A file is accepted or refused as a whole. Row errors name the row (1 = the first data row), the column and the problem.
* The server validates everything; a client-side preview is a convenience only.
* Cells are stored as plain text. A cell that starts with = + - @ is flagged, because a spreadsheet could execute it on export.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

MAX_BYTES = 2_000_000
MAX_ROWS = 5000
KNOWN_COLUMNS = (
    "external_id",
    "group_key",
    "label",
    "content_sha256",
    "phash",
    "file_status",
    "width",
    "height",
    "source",
)
REQUIRED_COLUMNS = ("external_id",)
FORBIDDEN_COLUMNS = {
    "label_status", "status", "review_status", "reviewed", "validated", "verified", "reviewer", "reviewer_id", "reviewed_by",
    "expert", "accepted", "is_synthetic", "id", "workspace_id", "dataset_id",
}  # fmt: skip
LIMITS = {"external_id": 300, "group_key": 200, "label": 120, "source": 300}
SHA = re.compile(r"^[0-9a-f]{64}$")
PHASH = re.compile(r"^[0-9a-f]{16}$")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
FORMULA_START = ("=", "+", "-", "@")
TEMPLATE = "external_id,group_key,label,content_sha256,phash,file_status,width,height,source\n"


@dataclass
class Row:
    number: int  # 1 = first data row
    data: dict[str, Any]
    errors: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Parsed:
    columns: list[str]
    rows: list[Row]
    file_errors: list[dict[str, str]]
    warnings: list[dict[str, Any]]


def _err(code: str, message: str, column: str | None = None) -> dict[str, str]:
    return {"code": code, "message": message, **({"column": column} if column else {})}


def _clean(value: str) -> str:
    return value.strip()


def parse(text: str, *, require_source: bool = True) -> Parsed:
    """Parse and validate. Never raises for bad content: problems are returned."""
    fatal = lambda code, msg: Parsed([], [], [_err(code, msg)], [])  # noqa: E731
    if "\x00" in text:
        return fatal("binary_content", "the file contains NUL characters and is not a text CSV")
    if len(text.encode("utf-8", errors="ignore")) > MAX_BYTES:
        return fatal("file_too_large", f"the file is larger than {MAX_BYTES // 1_000_000} MB")
    text = text.lstrip("﻿")
    try:
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        return fatal("malformed_csv", f"the file is not valid CSV: {exc}")
    records = [r for r in records if any(c.strip() for c in r)]  # blank lines are ignored
    if not records:
        return fatal("empty_file", "the file is empty")
    header = [c.strip().lower() for c in records[0]]
    file_errors: list[dict[str, str]] = []
    if len(set(header)) != len(header):
        file_errors.append(_err("duplicate_columns", "a column name appears more than once"))
    forbidden = [c for c in header if c in FORBIDDEN_COLUMNS]
    if forbidden:
        file_errors.append(_err(
            "review_state_not_importable",
            f"column(s) {', '.join(forbidden)} cannot be imported: every imported label starts as unreviewed, and review "
            "status can only be set by a recorded review",
        ))  # fmt: skip
    unknown = [c for c in header if c not in KNOWN_COLUMNS and c not in FORBIDDEN_COLUMNS]
    if unknown:
        file_errors.append(
            _err("unknown_columns", f"unknown column(s): {', '.join(unknown)}. Allowed: {', '.join(KNOWN_COLUMNS)}")
        )
    for col in REQUIRED_COLUMNS:
        if col not in header:
            file_errors.append(_err("missing_column", f"required column {col!r} is missing", col))
    if require_source and "source" not in header:
        file_errors.append(
            _err("missing_column", "column 'source' (where each sample came from) is required", "source")
        )
    body = records[1:]
    if len(body) > MAX_ROWS:
        file_errors.append(_err("too_many_rows", f"{len(body)} rows; the limit is {MAX_ROWS} per file"))
    if file_errors:
        return Parsed(header, [], file_errors, [])

    rows: list[Row] = []
    first_seen: dict[str, int] = {}
    warn_rows: dict[str, list[int]] = defaultdict(list)
    sha_rows: dict[str, list[int]] = defaultdict(list)
    for n, rec in enumerate(body, start=1):
        row = Row(n, {})
        if len(rec) != len(header):
            row.errors.append(_err("wrong_field_count", f"row has {len(rec)} fields but the header has {len(header)}"))
            rows.append(row)
            continue
        cells = dict(zip(header, (_clean(c) for c in rec), strict=True))
        for col, value in cells.items():
            if CONTROL.search(value):
                row.errors.append(_err("control_characters", "contains control characters", col))
            elif col in LIMITS and value.startswith(FORMULA_START):
                warn_rows["formula_like_cell"].append(n)
        ext = cells.get("external_id", "")
        if not ext:
            row.errors.append(_err("missing_value", "external_id is empty", "external_id"))
        elif ext in first_seen:
            row.errors.append(
                _err(
                    "duplicate_in_file", f"external_id {ext!r} already appears in row {first_seen[ext]}", "external_id"
                )
            )
        else:
            first_seen[ext] = n
        for col, limit in LIMITS.items():
            if len(cells.get(col, "")) > limit:
                row.errors.append(_err("too_long", f"longer than {limit} characters", col))
        sha = cells.get("content_sha256", "").lower()
        if sha and not SHA.match(sha):
            row.errors.append(
                _err("invalid_value", "must be 64 lower-case hexadecimal characters (SHA-256)", "content_sha256")
            )
        ph = cells.get("phash", "").lower()
        if ph and not PHASH.match(ph):
            row.errors.append(_err("invalid_value", "must be 16 hexadecimal characters", "phash"))
        fs = cells.get("file_status", "").lower()
        if fs and fs not in ("ok", "invalid"):
            row.errors.append(_err("invalid_value", "must be 'ok' or 'invalid'", "file_status"))
        dims: dict[str, int | None] = {}
        for col in ("width", "height"):
            raw = cells.get(col, "")
            dims[col] = None
            if raw:
                if not raw.isdigit() or not 0 < int(raw) <= 100_000:
                    row.errors.append(_err("invalid_value", "must be a whole number between 1 and 100000", col))
                else:
                    dims[col] = int(raw)
        source = cells.get("source", "")
        if require_source and not source and "source" in header:
            row.errors.append(
                _err("missing_provenance", "source is empty: every sample needs a recorded origin", "source")
            )
        if not cells.get("group_key"):
            warn_rows["missing_group"].append(n)
        if not cells.get("label"):
            warn_rows["missing_label"].append(n)
        if sha:
            sha_rows[sha].append(n)
        row.data = {
            "external_id": ext, "group_key": cells.get("group_key") or None, "label": cells.get("label") or None,
            "content_sha256": sha or None, "phash": ph or None, "file_status": fs or None,
            "width": dims["width"], "height": dims["height"],
            "provenance": {"source": source, "imported_from": "csv"} if source else {"imported_from": "csv"},
        }  # fmt: skip
        rows.append(row)

    texts = {
        "missing_group": "rows without a group_key cannot be kept apart in a grouped split, so they will be left out of splits",
        "missing_label": "rows without a label are imported unlabelled and will be left out of splits",
        "formula_like_cell": "cells starting with = + - or @ are stored as plain text; a spreadsheet could execute them if the data is exported",
    }
    warnings = [{"code": c, "message": texts[c], "count": len(v), "rows": v[:10]} for c, v in warn_rows.items()]
    dup = {s: r for s, r in sha_rows.items() if len(r) > 1}
    if dup:
        flat = sorted(n for r in dup.values() for n in r)
        warnings.append({
            "code": "identical_files_in_file", "count": len(flat), "rows": flat[:10],
            "message": f"{len(dup)} group(s) of rows share the same content_sha256: the same file registered under several identifiers",
        })  # fmt: skip
    return Parsed(header, rows, [], warnings)
