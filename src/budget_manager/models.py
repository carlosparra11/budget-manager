"""Transaction schema: the single contract every layer depends on.

Fields are always present (no optional fields), and the allowed values are
defined here once so validation, services and storage cannot drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

KINDS: tuple[str, ...] = ("expense", "income")

EXPENSE_CATEGORIES: tuple[str, ...] = (
    "food", "housing", "transport", "utilities",
    "health", "entertainment", "education", "other",
)
INCOME_CATEGORIES: tuple[str, ...] = ("salary", "freelance", "gift", "other")

CATEGORIES_BY_KIND: dict[str, tuple[str, ...]] = {
    "expense": EXPENSE_CATEGORIES,
    "income": INCOME_CATEGORIES,
}

CURRENCIES: tuple[str, ...] = ("EUR", "USD", "GBP")

# Column order used in CSV files. Same order as the schema in the brief.
FIELDS: tuple[str, ...] = ("id", "date", "kind", "category", "amount", "currency")


@dataclass(frozen=True)
class Transaction:
    """One validated money movement. Immutable once built.

    Build instances through ``validation.parse_transaction`` so every
    transaction in the system has passed the same boundary checks.
    """

    id: str          # e.g. "T001"
    date: date       # ISO date, e.g. 2026-09-04
    kind: str        # "expense" | "income"
    category: str    # controlled vocabulary, depends on kind
    amount: float    # strictly positive, max 2 decimals
    currency: str    # ISO 4217 code from CURRENCIES

    def signed_amount(self) -> float:
        """Income counts positive, expenses negative."""
        return self.amount if self.kind == "income" else -self.amount

    def to_row(self) -> dict[str, str]:
        """Serialise to a CSV-ready dict of strings."""
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "kind": self.kind,
            "category": self.category,
            "amount": f"{self.amount:.2f}",
            "currency": self.currency,
        }
