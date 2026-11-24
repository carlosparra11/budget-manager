"""Boundary validation: the only place raw input becomes a Transaction.

Rules
-----
* Every problem is reported with the field name and what a valid value
  looks like, so the user can fix it.
* Nothing is silently corrected. The only normalisation applied is
  trimming surrounding whitespace and case-folding of codes
  (" Food " -> "food", "eur" -> "EUR"), which cannot change meaning.
  Anything ambiguous (e.g. "18,50", "1.234", "04/09/2026") is rejected.
* All errors in a record are collected, not just the first one, so the
  user can fix a row in a single pass.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Mapping

from .models import CATEGORIES_BY_KIND, CURRENCIES, FIELDS, KINDS, Transaction

ID_PATTERN = re.compile(r"^T\d{3,}$")
AMOUNT_PATTERN = re.compile(r"^\d+(\.\d{1,2})?$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_AMOUNT = 1_000_000.00


class ValidationError(ValueError):
    """Raised when raw input cannot become a valid Transaction.

    ``errors`` holds one human-readable message per problem.
    """

    def __init__(self, errors: list[str], context: str = "") -> None:
        self.errors = list(errors)
        self.context = context
        prefix = f"{context}: " if context else ""
        super().__init__("; ".join(prefix + e for e in self.errors))


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def validate_id(raw: object) -> tuple[str | None, str | None]:
    value = _clean(raw)
    if not value:
        return None, "id is required (format T001)"
    if not ID_PATTERN.match(value):
        return None, f"id '{value}' must look like T001 (T + at least 3 digits)"
    return value, None


def validate_date(raw: object) -> tuple[date | None, str | None]:
    value = _clean(raw)
    if not value:
        return None, "date is required (format YYYY-MM-DD)"
    if not DATE_PATTERN.match(value):
        return None, f"date '{value}' must use ISO format YYYY-MM-DD, e.g. 2026-09-04"
    try:
        return date.fromisoformat(value), None
    except ValueError:
        return None, f"date '{value}' is not a real calendar date"


def validate_kind(raw: object) -> tuple[str | None, str | None]:
    value = _clean(raw).lower()
    if value not in KINDS:
        shown = _clean(raw) or "(empty)"
        return None, f"kind '{shown}' must be one of: {', '.join(KINDS)}"
    return value, None


def validate_category(raw: object, kind: str | None) -> tuple[str | None, str | None]:
    """Unknown-category policy: REJECT, and list the allowed values.

    We never map unknown categories to 'other' automatically, because that
    would silently distort the per-category report.
    """
    value = _clean(raw).lower()
    if not value:
        return None, "category is required"
    if kind is None:  # kind invalid: we cannot judge the category yet
        return value, None
    allowed = CATEGORIES_BY_KIND[kind]
    if value not in allowed:
        return None, (f"category '{_clean(raw)}' is not allowed for {kind}; "
                      f"use one of: {', '.join(allowed)}")
    return value, None


def validate_amount(raw: object) -> tuple[float | None, str | None]:
    value = _clean(raw)
    if not value:
        return None, "amount is required"
    if value.startswith("-"):
        return None, f"amount must be > 0 (got {value}); use kind=expense for money out"
    if "," in value:
        return None, f"amount '{value}' uses a comma; use a dot for decimals, e.g. 18.50"
    if not AMOUNT_PATTERN.match(value):
        try:
            number = float(value)
        except ValueError:
            return None, f"amount '{value}' is not a number"
        if math.isnan(number) or math.isinf(number):
            return None, f"amount '{value}' is not a finite number"
        return None, f"amount '{value}' must have at most 2 decimal places"
    number = float(value)
    if number <= 0:
        return None, "amount must be > 0"
    if number > MAX_AMOUNT:
        return None, f"amount must be <= {MAX_AMOUNT:,.2f} (got {value})"
    return number, None


def validate_currency(raw: object) -> tuple[str | None, str | None]:
    value = _clean(raw).upper()
    if value not in CURRENCIES:
        shown = _clean(raw) or "(empty)"
        return None, f"currency '{shown}' must be one of: {', '.join(CURRENCIES)}"
    return value, None


def parse_transaction(raw: Mapping[str, object], context: str = "") -> Transaction:
    """Turn a raw mapping (CSV row or CLI answers) into a Transaction.

    Raises ValidationError listing *every* problem found.
    """
    errors: list[str] = []

    missing = [f for f in FIELDS if f not in raw]
    if missing:
        raise ValidationError([f"missing column(s): {', '.join(missing)}"], context)

    def check(result: tuple[object, str | None]) -> object:
        value, err = result
        if err:
            errors.append(err)
        return value

    tx_id = check(validate_id(raw["id"]))
    tx_date = check(validate_date(raw["date"]))
    kind = check(validate_kind(raw["kind"]))
    category = check(validate_category(raw["category"], kind))
    amount = check(validate_amount(raw["amount"]))
    currency = check(validate_currency(raw["currency"]))

    if errors:
        raise ValidationError(errors, context)

    return Transaction(id=tx_id, date=tx_date, kind=kind, category=category,
                       amount=amount, currency=currency)
