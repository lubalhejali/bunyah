# BUNYAH | بُنية – Prototype V1

A working prototype of a Saudi-focused B2B engineering services platform, built by evolving the earlier EngConnect
code. It has two separate service models:

- **Model A**: project-based engineering services.
- **Model B**: short-term daily-rate service contracts.

It also has organization teams, verification, versioned deliverables, simulated finance, disputes and an admin console.

> **Prototype only.**
> - All data is fictional.
> - Payments are **simulated**: no real money moves, no card details are collected, and the platform holds no funds.
> - Legal, tax and data-hosting assumptions are pending professional review (Blueprint D1, D2, D6).

**Non-technical owner?** Start with [docs/DELIVERY_REPORT.md](docs/DELIVERY_REPORT.md), then use [GUIDE.md](GUIDE.md) to deploy.

## Run it on your computer (Windows)
```bash
python -m venv .venv
```
```bash
.venv\Scripts\pip install -r requirements-dev.txt
```
```bash
.venv\Scripts\python -m uvicorn app.main:app --reload
```
Open http://localhost:8000.
- With `DEMO_MODE=true` (the default), the demo data is created automatically.
- The login page offers one-click demo accounts (see [DEMO_ACCOUNTS.md](DEMO_ACCOUNTS.md)).

The database structure is upgraded automatically when the app starts (`python -m app.migrate` does it by hand).

Run the automated tests:
```bash
.venv\Scripts\python -m pytest --cov=app
```

## Stack (kept from EngConnect)
- **Server**: FastAPI and SQLAlchemy 2.
  - Databases: SQLite locally, PostgreSQL on Render.
  - Inputs are checked with Pydantic v2.
  - Database changes use **Alembic migrations** (`migrations/`).
- **Front end**: vanilla JavaScript, with no build step.
  - Bilingual: Arabic RTL by default, English LTR.
  - Strict Content-Security-Policy.
- **Login and security**:
  - Login uses a signed cookie (HttpOnly, SameSite=Lax, 12 h).
  - Every change request needs an `X-Requested-With: fetch` header, which blocks cross-site request forgery.
  - Passwords are hashed with scrypt.
  - Login attempts are rate-limited.
- **Files**:
  - Stored through a replaceable storage layer: the database (default) or a local folder.
  - Each file's first bytes are checked against its extension.
  - Downloads are private by default.

## Code map
| Path | What it is |
|---|---|
| `app/models.py` | All tables (accounts, Model A, Model B, finance, disputes, audit, legacy) |
| `app/services/model_a.py` | Model A rules: projects, proposals, agreement, milestones, tasks, deliverable versions |
| `app/services/model_b.py` | Model B rules: requests, applications, contract, signatures, time entries, billing periods |
| `app/services/states.py` | Allowed status changes for both models (anything else is refused) |
| `app/services/finance.py` | Simulated invoices, payments, payouts and refunds; configurable fees; replaceable provider |
| `app/services/disputes.py` | Disputes: responses, evidence, reasoned decision, appeal, closure |
| `app/services/checks.py` | Review reminders, escalations (never auto-approve), proposal deadlines, near-expiry |
| `app/services/calendar.py` | Saudi working-day calendar (Sun–Thu, holidays, UTC+3) |
| `app/services/settings.py` | Admin-editable business rules (90-day limit, 20-day periods, review window…) |
| `app/security.py` | Login, organization roles and permissions |
| `app/routers/*` | HTTP endpoints (see `/api/docs`) |
| `app/static/` | Front end (`js/core.js` helpers, `js/views-*.js` screens, `css/app.css` identity) |
| `app/seed.py` | Reference data and fictional demo data |
| `tests/` | Automated tests for scenarios A–D, security, review windows, disputes and migrations |
| `tools/capture_screenshots.py` | Re-creates the screenshots in `docs/screenshots/` |

## API
All endpoints are under `/api/v1`. Interactive documentation is at `/api/docs`, and the same description is saved as `openapi.json`.
Errors always look like this:
```json
{"error": {"code": "...", "message": "...", "message_ar": "...", "details": []}}
```

The old EngConnect Stripe and escrow endpoints now answer `410 FEATURE_SWITCHED_OFF` (see [docs/LEGACY.md](docs/LEGACY.md)).
