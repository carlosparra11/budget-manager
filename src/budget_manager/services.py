"""Business logic: add, list/filter, summarise, undo, import.

No input(), no print(), no file paths here. The service talks to storage
through an injected object, so tests can use a temp file and the CLI can
be swapped for a GUI later without touching these rules.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Protocol

from .models import Transaction
from .storage import LoadResult, read_csv
from .validation import ValidationError, parse_transaction


class Storage(Protocol):
    def load(self) -> LoadResult: ...
    def save(self, transactions: list[Transaction]) -> None: ...


class ReadOnlyError(RuntimeError):
    """Writing is blocked because the data file has invalid rows."""


@dataclass
class CurrencySummary:
    currency: str
    income: float = 0.0
    expense: float = 0.0
    count: int = 0
    by_category: dict[str, float] = field(default_factory=dict)

    @property
    def balance(self) -> float:
        return round(self.income - self.expense, 2)


@dataclass
class ImportResult:
    added: list[Transaction]
    errors: list[str]


class BudgetService:
    """Holds the current state and keeps the file in sync with it.

    Every mutating method saves to disk *before* changing memory, so the
    file on disk always reflects the true state. If saving fails, memory is
    left untouched and the exception propagates.
    """

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        loaded = storage.load()
        self._transactions: list[Transaction] = list(loaded.transactions)
        self.load_errors: list[str] = list(loaded.errors)

    # ----- queries ---------------------------------------------------------
    @property
    def read_only(self) -> bool:
        """True when the file had invalid rows.

        Saving would rewrite the file without those rows, i.e. silently
        delete the user's data, so we refuse to write until they fix it.
        """
        return bool(self.load_errors)

    def all(self) -> list[Transaction]:
        return list(self._transactions)

    def filter(self, kind: str | None = None, category: str | None = None,
               month: str | None = None, currency: str | None = None) -> list[Transaction]:
        """month uses 'YYYY-MM'. Filters are case-insensitive; None = no filter."""
        result = self._transactions
        if kind:
            result = [t for t in result if t.kind == kind.strip().lower()]
        if category:
            result = [t for t in result if t.category == category.strip().lower()]
        if month:
            result = [t for t in result if t.date.isoformat().startswith(month.strip())]
        if currency:
            result = [t for t in result if t.currency == currency.strip().upper()]
        return sorted(result, key=lambda t: (t.date, t.id))

    def next_id(self) -> str:
        numbers = [int(t.id[1:]) for t in self._transactions]
        return f"T{(max(numbers, default=0) + 1):03d}"

    def summarize(self, transactions: Iterable[Transaction] | None = None
                  ) -> dict[str, CurrencySummary]:
        """Totals per currency. Currencies are never mixed or converted."""
        txs = self._transactions if transactions is None else list(transactions)
        summaries: dict[str, CurrencySummary] = {}
        cat_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for t in txs:
            s = summaries.setdefault(t.currency, CurrencySummary(t.currency))
            s.count += 1
            if t.kind == "income":
                s.income += t.amount
            else:
                s.expense += t.amount
                cat_totals[t.currency][t.category] += t.amount
        for cur, s in summaries.items():
            s.income = round(s.income, 2)
            s.expense = round(s.expense, 2)
            s.by_category = {c: round(v, 2) for c, v in
                             sorted(cat_totals[cur].items(), key=lambda kv: -kv[1])}
        return dict(sorted(summaries.items()))

    # ----- commands --------------------------------------------------------
    def _ensure_writable(self) -> None:
        if self.read_only:
            raise ReadOnlyError(
                f"changes are blocked: the data file has {len(self.load_errors)} invalid "
                "row problem(s), and saving now would delete those rows. "
                "Fix them first (see load_errors / the warning above).")

    def _commit(self, new_state: list[Transaction]) -> None:
        self.storage.save(new_state)       # disk first...
        self._transactions = new_state     # ...then memory

    def add(self, raw: Mapping[str, object]) -> Transaction:
        """Validate and persist one transaction. The id is assigned here."""
        self._ensure_writable()
        data = dict(raw)
        data["id"] = self.next_id()
        tx = parse_transaction(data)
        self._commit(self._transactions + [tx])
        return tx

    def undo_last(self) -> Transaction | None:
        """Remove the most recently added transaction and persist that.

        "Most recent" = last row in the file, which is also what we get after
        a crash and reload, so undo behaves the same either way.
        Returns the removed transaction, or None when there is nothing to undo.
        """
        self._ensure_writable()
        if not self._transactions:
            return None
        removed = self._transactions[-1]
        self._commit(self._transactions[:-1])
        return removed

    def import_csv(self, path: Path | str) -> ImportResult:
        """Append the valid rows of another CSV, assigning fresh ids.

        Incoming ids are still validated (format + uniqueness inside that
        file) but replaced, so imports can never collide with existing ids.
        Invalid rows are skipped and reported with their row number.
        """
        self._ensure_writable()
        loaded = read_csv(Path(path))
        new_state = list(self._transactions)
        added: list[Transaction] = []
        next_number = max((int(t.id[1:]) for t in new_state), default=0) + 1
        for t in loaded.transactions:
            fresh = Transaction(f"T{next_number:03d}", t.date, t.kind,
                                t.category, t.amount, t.currency)
            next_number += 1
            new_state.append(fresh)
            added.append(fresh)
        if added:
            self._commit(new_state)
        return ImportResult(added=added, errors=loaded.errors)


__all__ = ["BudgetService", "CurrencySummary", "ImportResult",
           "ReadOnlyError", "ValidationError"]
