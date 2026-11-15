# EngConnect features: what was kept, changed or switched off

The complete original EngConnect project is preserved in `_backup/engconnect-original-2026-11-15/`, including its database
and code. Nothing from it was destroyed.

## How existing data is upgraded
The migration `0002` converts the old data and keeps everything:

| Old data | Becomes |
|---|---|
| Office accounts | Organizations, each with the office account as Owner |
| Freelancers | Engineers with a profile |
| `online` work mode | `remote` |
| Old statuses | Their new equivalents |
| Old one-way reviews | **Copied** into the new two-way ratings table |

The old `payments`, `withdrawals` and `reviews` tables are kept **unchanged and read-only**. The admin can see their
counts with `GET /api/v1/admin/legacy`.

The migration also has a tested downgrade back to the EngConnect structure.

## Switched off (needs your approval to remove permanently)
### Stripe Checkout escrow and wallet withdrawals
**What it did:** organizations paid real money through Stripe into an escrow, and freelancers asked for withdrawals.

**Why it is off:** the brief forbids real payments and any claim that BUNYAH holds funds. Payment custody and the
payment provider are also still undecided (Blueprint D1).

**Endpoints affected:** these now answer `410 FEATURE_SWITCHED_OFF` with a clear message:
- `/projects/{id}/payment` and `/projects/{id}/payment/confirm`
- `/payments`
- `/wallet` and `/wallet/withdrawals`
- `/admin/withdrawals`
- `/admin/escrow`

The code is in the backup. The `stripe` package was removed from `requirements.txt` because nothing uses it.

**Replacement plan:**
- `app/services/finance.py` already has a replaceable `SimulatedProvider`.
- Once D1 is approved (provider, custody model, accountant sign-off), a licensed Saudi provider is added as a second
  provider class with the same methods.
- No other code needs to change.

## Changed
| EngConnect | BUNYAH | Why |
|---|---|---|
| Hard file delete | Archive (`is_archived`), bytes kept | Never lose engineering records (blueprint 9.7 – awaiting your approval) |
| One office = one user | Organization with team members and five roles | Brief section 3 |
| 7 project statuses | 14 Model A statuses with server-checked transitions | Brief section 7 |
| One file list | Deliverables with immutable versions V1, V2… | Brief section 5 |
| Fee in an environment variable | Admin-configurable fee rules (per model, payer, % or fixed) | Brief section 6 |
| English only | Arabic (default, RTL) and English | Brief section 9 |
| `create_all` tables | Alembic migrations | Brief section 11 |
