# Design Rationale

The program is split into layers: CLI → service → validation/models → storage. Each layer has one job.
`validation.parse_transaction` is the **only** way raw text becomes a `Transaction`.
Interactive answers, command-line flags and CSV rows all go through it, so they all follow the same rules.

The key business decision is how the program treats a data file that contains invalid rows.
It could drop those rows silently, or "fix" them (for example, turn `-12` into `12`).
Either would make the report look clean while hiding real money movements from the user.
Instead, the file loads in **read-only** mode. Valid rows are shown, and every invalid row is reported with its row number ("Row 5: amount must be > 0").
Any write is refused until the user fixes those rows, because saving would rewrite the file without them.

Undo (the stretch goal) follows the same idea of trust. Every change is written to disk **before** it is applied in memory, using an atomic temp-file + `os.replace` write.
"Last transaction" is defined as the last row in the file, not as an in-memory history list.
So undo gives the same result whether or not the program crashed and was restarted in between.

## Exit ticket notes

- **Verified:** `test_undo_after_crash_and_reload`. It adds T001 and T002, discards the service, reloads from disk, and undoes. The test asserts that the file then contains only `T001`.
- **Boundary that changed the design:** the duplicate-ID check. At first it only compared *valid* rows, so a repeated `T013` slipped through when the first `T013` was itself invalid. The check now runs on the raw ID before validation.
- **Next refactor (Release 2):** change `amount` from `float` to `decimal.Decimal`, and give `BudgetService` an operation log so it can support multi-step undo and edit/delete by ID.
