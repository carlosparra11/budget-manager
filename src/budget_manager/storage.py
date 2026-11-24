"""Persistence: CSV load/save. No business rules, no printing, no prompts.

Two guarantees:
1. ``load`` never drops or "fixes" a bad row silently. Valid rows are
   returned, invalid rows come back as row-numbered error messages.
2. ``save`` is atomic: it writes to a temp file and swaps it in with
   os.replace, so a crash mid-write leaves the old file intact rather
   than a half-written one.
"""
from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .models import FIELDS, Transaction
from .validation import ValidationError, parse_transaction


class StorageError(Exception):
    """File-level problem (wrong header, unreadable file...)."""


@dataclass
class LoadResult:
    transactions: list[Transaction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # e.g. "Row 4: amount must be > 0"

    @property
    def ok(self) -> bool:
        return not self.errors


def read_csv(path: Path) -> LoadResult:
    """Read and validate a transactions CSV. Missing file = empty result."""
    path = Path(path)
    result = LoadResult()
    if not path.exists():
        return result

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = [h.strip() for h in (reader.fieldnames or [])]
        if not header:
            return result  # empty file
        missing = [f for f in FIELDS if f not in header]
        if missing:
            raise StorageError(
                f"{path.name}: header is missing column(s): {', '.join(missing)}. "
                f"Expected: {','.join(FIELDS)}")
        reader.fieldnames = header

        seen_ids: dict[str, int] = {}
        # Row numbers match what a user sees in a spreadsheet: header is row 1.
        for row_number, row in enumerate(reader, start=2):
            if not any(_v.strip() for _v in row.values() if isinstance(_v, str)):
                continue  # skip fully blank lines
            if None in row:  # more cells than header columns
                result.errors.append(f"Row {row_number}: has more values than columns")
                continue
            # Duplicate check uses the raw id so it also catches a repeat of an
            # id whose first row was invalid.
            raw_id = (row.get("id") or "").strip()
            if raw_id and raw_id in seen_ids:
                result.errors.append(
                    f"Row {row_number}: id {raw_id} duplicates row {seen_ids[raw_id]}")
                continue
            if raw_id:
                seen_ids[raw_id] = row_number
            try:
                tx = parse_transaction(row)
            except ValidationError as exc:
                result.errors.extend(f"Row {row_number}: {e}" for e in exc.errors)
                continue
            result.transactions.append(tx)
    return result


def write_csv(path: Path, transactions: list[Transaction]) -> None:
    """Atomically write all transactions (full rewrite, header included)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(FIELDS))
            writer.writeheader()
            for tx in transactions:
                writer.writerow(tx.to_row())
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


class CsvStorage:
    """Thin object wrapper so the service can be given any storage."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> LoadResult:
        return read_csv(self.path)

    def save(self, transactions: list[Transaction]) -> None:
        write_csv(self.path, transactions)
