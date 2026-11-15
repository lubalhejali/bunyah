# BUNYAH Prototype V1 – Delivery report (for the product owner)

**Date:** 15 November 2026. **Status:** working prototype on your computer.

- **Not deployed.** Nothing is on the internet.
- **No real payments.** All money is simulated.
- **Fictional data only.**

---

## 1. Summary
I kept the existing EngConnect project and grew it into BUNYAH. I did not start again from zero.
- **Kept**: the server technology, the login security and the file checks.
- **Upgraded**: the database is converted automatically and keeps all old data.
- **Rebuilt**: the screens, so that everything is bilingual. Arabic is the default and English is a full alternative.

All four acceptance scenarios (A organization, B engineer, C short-term contract, D administrator) work in the browser.
Automated tests check them end to end: **25 tests pass, covering 84% of the server code.**

---

## 2. Development phases (what, why, how, what you see)

### Phase 1 – Audit and preparation
**What I did:**
- Read every EngConnect file.
- Ran its 32 existing tests (all passed).
- Saved a complete untouched copy in `_backup/`.
- Added **migrations**: versioned scripts that change the database structure step by step.

**Why:** your brief says not to overwrite or lose existing data.

**How it works:**
- On the first start, the old database is recognised and upgraded.
- Offices become organizations and freelancers become engineers.
- Old payments and reviews are kept untouched.

I tested this on a copy of the real local database. I also tested the reverse step (downgrade).

**What you'll notice:** nothing. Your old test accounts still exist, now as an organization and an engineer.

**Limitation found:** the old Stripe escrow flow contradicts the brief (no real payments, no holding of funds). It is
switched off, not deleted. See `docs/LEGACY.md`.

### Phase 2 – Core platform
**What I built:**
- Three account types: organization, engineer and administrator.
- Organization teams with five roles (Owner, Project Manager, Technical Reviewer, Finance, Viewer), added by invitation link.
- Full organization and engineer profiles.
- Verification with private documents.
- Bilingual screens with Arabic/English switching.
- Optional Hijri dates.
- The admin console.

**Important decision:** every permission is checked **on the server**. Hiding a button is never the only protection,
and the tests try forbidden actions on purpose.

### Phase 3 – Model A (projects)
**What I built:**
- **Project flow:** draft → published → proposals closed → evaluation → shortlist → proposal accepted → in progress →
  submitted → revision → resubmitted → approved → completed, plus cancelled and disputed.
- **Proposals:** technical approach, price, duration, attachments and clarification questions.
- **Comparison:** a side-by-side table of proposals.
- **Agreement:** both parties confirm it.
- **Project workspace:**
  - optional milestones (up to 6, no minimum value);
  - tasks;
  - versioned deliverables (V1 → review → V2 → final approval; old versions are never overwritten);
  - files, discussion and technical reviews;
  - activity history and the financial summary.

### Phase 4 – Model B (short-term contracts)
**What I built:**
- **Request flow:** draft → submitted → BUNYAH review → published → applications open → evaluation → selected →
  contract preparation → awaiting signatures → active → near expiry → completed, plus terminated and disputed.
- **Candidates:** applications and a candidate comparison table.
- **Contract:** editable terms, then a simulated signature (you type your name).
- **Daily work log:** full or half days; weekends, holidays and future days are refused.
- **Billing periods** of 20 working days; the final period takes the rest (90 days = 20+20+20+20+10).
- **Fees:** daily rate × approved days.
- **Limits are settings:** the 90-day limit and the 20-day period are admin settings marked "pending legal review (D6)".

### Phase 5 – Supporting modules
**What I built:**
- In-app notifications in both languages.
- Messaging between organizations and engineers.
- **Simulated finance:** invoices, payments, payouts, refunds and transaction history, all labelled DEMO.
- Configurable fee rules: per model, who pays (organization, engineer or both), percentage or fixed.
- Disputes: evidence, responses, a reasoned decision, appeal and closure.
- Two-way ratings.
- Escalation of missed review windows.
- An audit log.

### Phase 6 – QA and demonstration
**What I did:**
- Wrote automated tests for all scenarios, security, review windows, disputes and migrations.
- Clicked through **126 screens** as organization, engineer and admin, with zero errors.
- Checked phone width and fixed three layout problems.
- Ran a code review and fixed 4 of its 6 findings.
- Did a security review (section 9).

---

## 3. What works now – functional, simulated or placeholder

**Functional** means really implemented and tested. **Simulated** means it works but deliberately does not do the real
thing. **Placeholder** means shown or prepared, but not built.

| Area | Status | Notes |
|---|---|---|
| Landing page, sign-up, log-in, log-out, password change | Functional | Rate-limited log-in |
| One-click demo logins | Functional (demo mode only) | Turned off when `DEMO_MODE=false` |
| Organization profile, team invitations, 5 roles | Functional | Invitation is a one-time link to copy (e-mail not set up) |
| Engineer profile, CV, portfolio | Functional | CV visible only to organizations the engineer applied to |
| Verification (organization and engineer) with private documents | Functional | Admin approve / reject / ask for more information |
| Model A full workflow | Functional | Server refuses every invalid status change |
| Deliverable versions and technical reviews | Functional | Versions are immutable |
| Model B full workflow, work log, billing periods | Functional | Saudi working week, holiday table |
| Contract signature | **Simulated** | Typed name, not a legal e-signature |
| Contract / agreement text | **Placeholder template** | Needs a Saudi lawyer (D6) |
| Payments, invoices, payouts, refunds | **Simulated** | No real money or cards; labelled DEMO everywhere |
| Fee rules | Functional (configuration) | Values are demo placeholders (D3) |
| VAT on invoices | Configurable, set to 0% | Tax treatment needs an accountant |
| Review window: 5 working days, 2 reminders, escalation, no auto-approval | Functional | Runs on start-up, hourly, or from Admin → Run checks |
| Disputes with decision and appeal; no automatic release | Functional | Money actions only after a recorded decision |
| Notifications | Functional in-app | E-mail is a placeholder (recorded as "not configured") |
| Messaging | Functional | Checks for new messages every 5 seconds (no live push) |
| Ratings (two-way) | Functional | After completion |
| Search and filters | Functional | Projects, requests, engineers, users, audit log |
| Admin reports and analytics | Functional (on-screen counts) | No export to Excel/PDF yet |
| Audit log | Functional | Verification, fees, settings, disputes, money, roles, suspensions |
| Arabic / English, RTL / LTR, Western numerals, optional Hijri | Functional | |
| File storage | Functional (database or local folder) | Object storage is prepared but not built (D2) |

---

## 4. Not completed yet
- **E-mail:**
  - No e-mail delivery: no notification e-mails and no invitation e-mails.
  - No "forgot password" flow, because it needs e-mail.
- **Interviews:** no interview scheduling (the blueprint planned an external link).
- **Exports:** no export of reports, invoices or contracts as PDF or Excel.
- **Engagements:** one engineer per Model B request; no multi-position requests.
- **Logins:** no two-factor login.
- **Payments:** no real payment provider (blocked by D1).
- **File storage:** no object storage (blocked by D2).
- **Fonts:** not bundled. IBM Plex Sans Arabic shows only on computers that have it installed (yours does); others see a
  system Arabic font. *Decision needed* (section 10).
- **Dark mode:** not built. It wasn't required, though the blueprint described its colours.

## 5. Known bugs and limitations
- **Sessions:** changing a password does not log out other open sessions. They expire within 12 hours.
- **Rate limits** are kept in memory. That is fine for one server, not for several.
- **Speed:** list pages make several database lookups per row. That is fine for prototype volumes; it needs tuning for large data.
- **Large files:** stored inside the database on Render. The free database holds only 1 GB in total.
- **Holidays:** Islamic holiday dates are estimates until an admin marks them "confirmed".
- **Signing late:** if a contract is signed after its planned start date, the start moves to the next working day automatically.
- **Simulated dates:** the admin "run checks as of a date" feature only works in demo mode.
- **API documentation:** response shapes are not fully described in `/api/docs`. Inputs are fully described and validated.

## 6. Demo logins and how to test each scenario
See [`DEMO_ACCOUNTS.md`](../DEMO_ACCOUNTS.md). On the login page, click a demo name.

- **Scenario A (organization)**
  1. Log in as Organization – Owner.
  2. Open **Projects** and choose "Structural design – 4-storey office building".
  3. On the **Proposals** tab, compare the proposals.
  4. On **Overview**, click "Close proposals", then "Start evaluation".
  5. Shortlist a proposal and select the engineer.
  6. Log in as Faisal and accept the agreement. Log back in as the owner and click "Confirm agreement & start work".
  7. Add milestones and deliverables.

  To review versions straight away, open "Structural design – school extension". It already has V1 (revision
  requested) and V2 (waiting for review).
- **Scenario B (engineer)**
  1. Log in as Engineer – Structural.
  2. Open **Projects → Marketplace** and choose "Structural assessment of an existing warehouse".
  3. On **My proposal**, submit a proposal and track it on the dashboard.
  4. In "school extension → Deliverables", upload V1 of "Structural drawings".
  5. Click **Submit work for review**.
  6. Open **Payments** to see the payment records.
- **Scenario C (short-term contract)**
  1. As the Owner, open **Short-term services → New service request**. Submit it.
  2. As Admin, open **Request review** and approve it.
  3. As the Owner, open applications. Engineers apply. Close applications, then select a candidate.
  4. Prepare the contract, send it, and sign it as both parties.
  5. Record work days and submit the period.
  6. Approve the period, then check **Finance** for both parties.

  To skip ahead, use the existing active contract "Site Structural Engineer – tower podium". Period 1 is already
  waiting for approval.
- **Scenario D (administrator)**
  1. Log in as Administrator.
  2. On **Verification**, review two pending requests.
  3. Monitor **Projects** and **Contracts**.
  4. Handle **Disputes**: the "Fire-fighting system design" dispute is open.
  5. **Escalations**: the clinic project review is overdue.
  6. Adjust **Platform fees** and **Settings**.
  7. Check **Overview** (analytics) and the **Audit log**.

## 7. Starting it on your computer
1. Ask Claude to start the app; it starts at http://localhost:8000.

   *Or* follow `README.md` → "Run it on your computer". These are three commands: create the environment, install, start.
2. Open http://localhost:8000 and use the demo logins.
3. To reset the demo data: stop the app, delete `local.db`, and start it again.

## 8. Database and architecture overview
- **One program serves both the pages and the API.** API stands for "Application Programming Interface": the addresses
  the pages use to read and save data.
- **Model A and Model B are fully separate:**
  - Model A: tables `projects`, `offers` (proposals), `milestones`, `deliverables`, `deliverable_versions`, `tasks`.
  - Model B: tables `service_requests`, `service_applications`, `service_contracts`, `billing_periods`, `time_entries`.
- **They share:**
  - accounts (`users`, `organizations`, `org_members`, `engineer_profiles`, `verification_requests`);
  - files (`files`);
  - messages and notifications;
  - disputes (`disputes`, `dispute_entries`) and escalations;
  - ratings;
  - simulated finance (`fee_rules`, `sim_invoices`, `sim_transactions`);
  - settings, holidays and `audit_logs`.
- **Every status change** goes through one list of allowed changes (`app/services/states.py`).
- **Every money record** stores the fee rule that applied at that moment, so later fee changes never alter history.
- **Payment provider:** a replaceable "provider" object (currently `SimulatedProvider`).

## 9. Tests and reviews
- **Automated tests:** `python -m pytest --cov=app` gives **25 passed**, with **84% line coverage**.
  - They cover Scenarios A–D end to end.
  - They try invalid transitions and role permissions.
  - They check the 5-day review window: two reminders, then escalation with **no approval**.
  - They cover the dispute pause, decision, appeal and refund rules.
  - They check private files, upload checks, cross-site request protection, blocked hidden-field tampering, the
    rate limit, the switched-off legacy endpoints, the migration and its downgrade, and the calendar and fee maths.
- **Code review (6 findings):**
  - **Fixed (4):**
    - A cancelled project still gave the engineer access.
    - Escalations stayed open after the review happened.
    - Invoice numbers could clash.
    - A CV was stored before its type was checked.
  - **Remaining (2):** sessions survive a password change, and list pages are slow at scale (section 5).
- **Security review:** the automatic `/security-review` tool needs Git, which isn't installed here, so I checked by hand:
  - **Login:** scrypt password hashing; HttpOnly, Secure, SameSite cookies; generic error messages; equal timing for
    unknown e-mails; rate limit; suspended accounts are cut off immediately.
  - **Access control:** checked per role and per record on the server; private projects answer "not found".
  - **Files:** extension allow-list and file-signature check; random storage names; forced download with a sandboxed
    response; private by default; verification documents and dispute evidence are never public.
  - **Inputs:** every field validated; unknown fields refused, so nobody can set "status" or "verified" themselves.
  - **Browser protection:** a strict content security policy, no HTML injection (all text is inserted as plain text),
    and protection against cross-site requests.
  - **Secrets:** none in the code; `.env`, the database and the backup are excluded from GitHub.
  - **Errors:** a friendly message in both languages, no technical details shown, and the details logged on the server.
  - **Remaining risks:** see section 5, and add two-factor login before production.
- **Interface review:**
  - Fixed: a sideways scroll on phones, statistic cards overflowing, punctuation in mixed Arabic/English text, the menu
    wrapping, and step labels running together.
  - Every status shows an icon **and** a word, never colour alone.
  - Semantic colours meet the WCAG AA contrast standard, using the blueprint's checked values.
  - Sage and Stone are never used for small text.
- **API review:**
  - Consistent plural, hyphenated addresses under `/api/v1`.
  - Correct response codes (201, 204, 400, 401, 403, 404, 409, 410, 422, 429).
  - One error format, with Arabic and English messages.
  - Public responses list their fields explicitly, so e-mails, phone numbers, registration numbers and documents never
    leak.

## 10. Blockers and decisions needed from you
**Legal (Saudi lawyer):**
- **D1** – payment custody and escrow, and the choice of payment provider.
- **D6** – the Model B 90-working-day limit and whether these engagements could count as employment; the contract
  template; electronic signatures.
- **D2** – personal-data hosting and transfers under the PDPL; privacy notice and terms.
- Professional-licensing checks for engineers.

**Tax and accounting:**
- VAT and the e-invoicing requirements for platform fees and engineer invoices.

**Commercial:**
- **D3** – fee levels and who pays them. The demo values are 2.5% plus 5% for Model A and 8% for Model B.

**Technical (my recommendations):**
1. **Fonts:** let me add the IBM Plex Sans Arabic font files to the project (free, open licence), so every visitor sees
   the brand font. This is a small download; I need your yes.
2. **E-mail:** choose an e-mail provider before the pilot. It is a monthly cost.
3. **File storage:** after D2, choose object storage (Saudi-hosted if required).
4. **Production hosting:** use paid Render plans with backups (see GUIDE.md section 17).

**Operational:**
- Who confirms holiday dates each year.
- Who staffs verification, request review, escalations and disputes. The dispute target is 10 working days.

## 11. Screenshots
These are in [`docs/screenshots/`](screenshots/). You can re-create them with `python tools/capture_screenshots.py` while the app runs.

| # | Screen | Language |
|---|---|---|
| 01 | Landing page | Arabic |
| 02 | Log-in with demo accounts | English |
| 03 | Organization dashboard | Arabic |
| 04 | Proposal comparison | English |
| 05 | Deliverable versions (V1/V2) | Arabic |
| 06 | Milestones | English |
| 07 | Simulated finance | English |
| 08 | Candidate comparison | Arabic |
| 09 | Work log and billing periods | English |
| 10 | Engineer dashboard | Arabic |
| 11 | Engineer profile | English |
| 12 | Admin overview | English |
| 13 | Verification review | Arabic |
| 14 | Dispute case | English |
| 15 | Admin settings | Arabic |
| 16 | Phone: project workspace | Arabic |
| 17 | Phone: dashboard | English |

## 12. Next steps
1. Test the scenarios yourself using section 6.
2. Decide on the font download, and take the legal and accounting items to your advisers.
3. If you want an online testing copy, follow `GUIDE.md`. I won't deploy unless you approve.
4. Then: e-mail delivery, password reset, exports, two-factor login and object storage.
