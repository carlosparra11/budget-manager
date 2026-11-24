"""Command-line interface: prompts, argument parsing and printing only.

All rules live in services.py / validation.py. This module translates
user input into calls and results into text.

Usage (from the project root, with PYTHONPATH=src):
    python -m budget_manager                      # interactive menu
    python -m budget_manager add --kind expense --category food --amount 18.50
    python -m budget_manager list --month 2026-09
    python -m budget_manager report
    python -m budget_manager undo
    python -m budget_manager import data/sample_transactions.csv
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Sequence

from . import validation
from .models import CATEGORIES_BY_KIND, CURRENCIES, KINDS, Transaction
from .services import BudgetService, ReadOnlyError
from .storage import CsvStorage, StorageError
from .validation import ValidationError

DEFAULT_FILE = Path("data") / "transactions.csv"
DEFAULT_CURRENCY = "EUR"


# ----- formatting -----------------------------------------------------------
def format_table(transactions: Sequence[Transaction]) -> str:
    if not transactions:
        return "No transactions found."
    header = f"{'ID':<6} {'DATE':<10} {'KIND':<8} {'CATEGORY':<14} {'AMOUNT':>11} CUR"
    lines = [header, "-" * len(header)]
    for t in transactions:
        sign = "+" if t.kind == "income" else "-"
        lines.append(f"{t.id:<6} {t.date.isoformat():<10} {t.kind:<8} "
                     f"{t.category:<14} {sign}{t.amount:>10.2f} {t.currency}")
    lines.append(f"{len(transactions)} transaction(s)")
    return "\n".join(lines)


def format_report(service: BudgetService, transactions: Sequence[Transaction]) -> str:
    summaries = service.summarize(transactions)
    if not summaries:
        return "No transactions to report."
    out: list[str] = []
    for cur, s in summaries.items():
        out.append(f"=== {cur} ({s.count} transaction(s)) ===")
        out.append(f"  Income : {s.income:>12.2f}")
        out.append(f"  Expense: {s.expense:>12.2f}")
        out.append(f"  Balance: {s.balance:>12.2f}")
        if s.by_category:
            out.append("  Expenses by category:")
            for cat, total in s.by_category.items():
                share = total / s.expense * 100 if s.expense else 0
                out.append(f"    {cat:<14}{total:>10.2f}  ({share:4.1f}%)")
    if len(summaries) > 1:
        out.append("Note: currencies are reported separately (no conversion).")
    return "\n".join(out)


def warn_load_errors(service: BudgetService, out: Callable[[str], None]) -> None:
    if service.load_errors:
        out(f"WARNING: {len(service.load_errors)} problem(s) in the data file "
            "(those rows are ignored; changes are blocked until fixed):")
        for e in service.load_errors:
            out(f"  {e}")


# ----- interactive mode -----------------------------------------------------
def ask(prompt: str, validator: Callable[[str], tuple[object, str | None]],
        input_fn: Callable[[str], str], out: Callable[[str], None],
        default: str | None = None) -> str:
    """Ask until the validator accepts the answer. Returns the raw text."""
    while True:
        suffix = f" [{default}]" if default else ""
        answer = input_fn(f"{prompt}{suffix}: ").strip()
        if not answer and default is not None:
            answer = default
        _, error = validator(answer)
        if error is None:
            return answer
        out(f"  ✗ {error}")


def interactive_add(service: BudgetService, input_fn, out) -> None:
    kind = ask(f"Kind ({'/'.join(KINDS)})", validation.validate_kind, input_fn, out).lower()
    allowed = ", ".join(CATEGORIES_BY_KIND[kind])
    category = ask(f"Category ({allowed})",
                   lambda v: validation.validate_category(v, kind), input_fn, out)
    amount = ask("Amount (e.g. 18.50)", validation.validate_amount, input_fn, out)
    currency = ask(f"Currency ({'/'.join(CURRENCIES)})", validation.validate_currency,
                   input_fn, out, default=DEFAULT_CURRENCY)
    tx_date = ask("Date (YYYY-MM-DD)", validation.validate_date, input_fn, out,
                  default=date.today().isoformat())
    tx = service.add({"date": tx_date, "kind": kind, "category": category,
                      "amount": amount, "currency": currency})
    out(f"Saved {tx.id}: {tx.kind} {tx.amount:.2f} {tx.currency} ({tx.category}) on {tx.date}")


MENU = """
--- Personal Budget Manager ---
1) Add transaction
2) List transactions
3) Report
4) Undo last transaction
5) Import CSV
6) Quit"""


def run_interactive(service: BudgetService, input_fn=input, out=print) -> int:
    warn_load_errors(service, out)
    while True:
        out(MENU)
        choice = input_fn("Choose 1-6: ").strip()
        try:
            if choice == "1":
                interactive_add(service, input_fn, out)
            elif choice == "2":
                month = input_fn("Filter by month YYYY-MM (Enter = all): ").strip() or None
                out(format_table(service.filter(month=month)))
            elif choice == "3":
                out(format_report(service, service.all()))
            elif choice == "4":
                removed = service.undo_last()
                out(f"Undid {removed.id} ({removed.kind} {removed.amount:.2f} "
                    f"{removed.currency})." if removed else "Nothing to undo.")
            elif choice == "5":
                path = input_fn("CSV path: ").strip()
                _print_import(service, path, out)
            elif choice in ("6", "q", "quit", "exit"):
                out("Bye!")
                return 0
            else:
                out("Please choose a number from 1 to 6.")
        except (ReadOnlyError, ValidationError, StorageError, OSError) as exc:
            out(f"Error: {exc}")


def _print_import(service: BudgetService, path: str, out) -> int:
    if not Path(path).exists():
        out(f"Error: file not found: {path}")
        return 1
    result = service.import_csv(path)
    out(f"Imported {len(result.added)} transaction(s).")
    if result.errors:
        out(f"Skipped {len(result.errors)} problem(s):")
        for e in result.errors:
            out(f"  {e}")
    return 0 if not result.errors else 2


# ----- argparse mode --------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="budget_manager",
                                description="Interactive personal budget manager.")
    p.add_argument("--file", default=str(DEFAULT_FILE),
                   help=f"transactions CSV (default: {DEFAULT_FILE})")
    sub = p.add_subparsers(dest="command")

    a = sub.add_parser("add", help="add a transaction")
    a.add_argument("--kind", required=True, help="expense | income")
    a.add_argument("--category", required=True)
    a.add_argument("--amount", required=True, help="positive, max 2 decimals, e.g. 18.50")
    a.add_argument("--currency", default=DEFAULT_CURRENCY)
    a.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")

    for name, helptext in (("list", "list transactions"), ("report", "summary report")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--kind")
        s.add_argument("--category")
        s.add_argument("--month", help="YYYY-MM")
        s.add_argument("--currency")

    sub.add_parser("undo", help="remove the last transaction (persisted)")
    i = sub.add_parser("import", help="append valid rows from another CSV")
    i.add_argument("path")
    sub.add_parser("interactive", help="menu-driven mode (default)")
    return p


def main(argv: Sequence[str] | None = None, input_fn=input, out=print) -> int:
    args = build_parser().parse_args(argv)
    try:
        service = BudgetService(CsvStorage(args.file))
    except StorageError as exc:
        out(f"Error: {exc}")
        return 1

    try:
        if args.command in (None, "interactive"):
            return run_interactive(service, input_fn, out)

        warn_load_errors(service, out)
        if args.command == "add":
            tx = service.add({"date": args.date or date.today().isoformat(),
                              "kind": args.kind, "category": args.category,
                              "amount": args.amount, "currency": args.currency})
            out(f"Saved {tx.id}: {tx.kind} {tx.amount:.2f} {tx.currency} "
                f"({tx.category}) on {tx.date}")
        elif args.command in ("list", "report"):
            txs = service.filter(kind=args.kind, category=args.category,
                                 month=args.month, currency=args.currency)
            out(format_table(txs) if args.command == "list" else format_report(service, txs))
        elif args.command == "undo":
            removed = service.undo_last()
            out(f"Undid {removed.id}." if removed else "Nothing to undo.")
        elif args.command == "import":
            return _print_import(service, args.path, out)
        return 0
    except ValidationError as exc:
        out("Error: transaction rejected:")
        for e in exc.errors:
            out(f"  - {e}")
        return 2
    except (ReadOnlyError, StorageError, OSError) as exc:
        out(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
