# Demo accounts (fictional)

These accounts exist only when `DEMO_MODE=true`. The people and companies are invented. The e-mails use the
reserved `.test` domain, so they can never reach a real inbox.

- **Easiest way in:** on the login page, click a name under **Demo accounts** (one click, no typing).
- **Typing instead:** use the e-mail below and the shared demo password **`Bunyah-Demo-2026`**.
- **Never use this password for a real account.** Set `DEMO_MODE=false` on any deployment that real people use.

| Role | E-mail | Use it for |
|---|---|---|
| Platform administrator | admin@bunyah.test | Scenario D: verification, request review, disputes, fees, settings, audit log |
| Organization – Owner | rawabi.owner@bunyah.test | Scenario A and C (full rights, signs contracts, records demo payments) |
| Organization – Project Manager | rawabi.pm@bunyah.test | Manage projects and requests, approve milestones and billing periods |
| Organization – Technical Reviewer | rawabi.reviewer@bunyah.test | Approve versions / request revisions |
| Organization – Finance | rawabi.finance@bunyah.test | Record simulated payments, view finance |
| Organization – Viewer | rawabi.viewer@bunyah.test | Read-only |
| Organization awaiting verification | najd.owner@bunyah.test | Shows the verification gate (can't publish yet) |
| Engineer – Structural (verified) | faisal.eng@bunyah.test | Scenario B: proposals, workspace, deliverables, active Model B contract |
| Engineer – MEP (verified) | reem.eng@bunyah.test | Escalated review and an open dispute |
| Engineer – BIM (verified) | majed.eng@bunyah.test | Proposals and a Model B application |
| Engineer awaiting verification | lama.eng@bunyah.test | Shows that unverified engineers can't apply |

## What the demo data already contains
**Model A projects**
- A published project that already has two proposals.
- Two more published projects.
- A project in progress with:
  - milestones;
  - deliverable V1 (revision requested) and V2 (under review);
  - tasks;
  - a paid demo invoice.
- A submitted project whose review window has passed, so it is escalated (not approved).
- A completed project with two-way ratings.
- One draft project and one disputed project.

**Model B requests and contracts**
- A request with applications open and two applicants.
- An active 90-working-day contract in which billing period 1 has been submitted for approval.
- A request waiting for BUNYAH review.
- One draft request.

**Admin work waiting**
- Two verification requests: one organization and one engineer.

To start again from scratch, stop the app and delete `local.db` (a copy of the original EngConnect database is in `_backup/`).
