# Putting BUNYAH online with Render – a beginner's guide

> **Important.** Nothing has been deployed. Follow this guide only when you decide to.
>
> This guide sets up a **testing deployment**: a private online copy with fictional demo data that you and your reviewers can click through.
> It is **not** a production launch. Production waits for:
> - your explicit approval;
> - decisions D1 (payments), D2 (personal-data hosting) and D6 (contract limit);
> - paid plans.

The facts about Render below were checked against Render's own documentation on 15 Nov 2026 (render.com/docs/free,
/docs/deploys, /docs/postgresql-backups). Render changes its products and prices, so check the linked pages before you pay
for anything.

---

## 0. What "deployment" means, in plain words
At the moment BUNYAH runs only on your computer, at `http://localhost:8000`. Nobody else can open it.

**Deploying** means copying the program to a computer on the internet (a *server*) that is always on. That server gives
it a public web address, such as `https://bunyah-testing.onrender.com`, which anyone with the link can open.

**Render** is a company that rents out such servers. You give Render your code, and Render:
1. installs it;
2. starts it;
3. gives it a web address with HTTPS (the padlock);
4. restarts it if it crashes;
5. runs the **PostgreSQL database** (the place where accounts, projects and files are stored).

Your code travels to Render through **GitHub**, a website that stores code. Every time you upload a new version to
GitHub, Render rebuilds the site automatically.

### Three kinds of deployment
| Kind | Who uses it | Data | Settings |
|---|---|---|---|
| **Development** | You, on your computer | Fictional | `ENV=development`, `DEMO_MODE=true`, SQLite file |
| **Testing** (this guide) | You and invited reviewers, online | Fictional only | `ENV=production`, `DEMO_MODE=true`, free or paid plans |
| **Production** | Real organizations and engineers | Real | `ENV=production`, **`DEMO_MODE=false`**, paid plans, backups, approved D1/D2/D6, legal sign-off |

`ENV=production` only switches on the internet-grade security settings (secure cookies, HTTPS headers). It does not
mean "live business".

---

## 1. Accounts you need
1. **GitHub**: https://github.com/signup. Choose a username, confirm your e-mail, and pick the free plan.
2. **Render**: https://dashboard.render.com/register. Choose **Sign up with GitHub**, which links the two accounts in one step.

You do **not** need a card for free plans. Render asks for one only when you choose a paid plan.

---

## 2. Put the project on GitHub (no command line needed)
This project is in a folder the Claude app made for this session. Ask Claude to move it to a folder you keep, such as
`Documents\BUNYAH`, before you continue.

1. Install **GitHub Desktop**: https://desktop.github.com. Open it and sign in with your GitHub account.
2. Click **File → Add local repository** and choose the BUNYAH folder.
3. It will say the folder is not a repository yet. Click **create a repository**.
   - Name: `bunyah`.
   - Leave "Initialize with README" **unticked** (there is already one).
   - Click **Create repository**.
4. Check the list of files on the left. You should **not** see any of these, because `.gitignore` excludes them:
   - `.env` (secrets)
   - `local.db` (the database)
   - `_backup/` (the old project copy)
   - `uploads/`

   **If you see any of them, stop and ask for help.** They must not be uploaded.
5. Type a summary ("BUNYAH prototype V1") and click **Commit to main**.
6. Click **Publish repository**. Keep **"Keep this code private"** ticked, then click **Publish repository**.

**Success looks like:** on github.com, under your profile → Repositories, you see a private `bunyah` repository with
the `app` folder, `render.yaml` and `README.md`.

**Common mistakes**
- *Publishing as public*: in the repository on github.com, open **Settings → General → Danger Zone → Change visibility → Private**.
- *`.env` was uploaded*: don't just delete it. Change any secret it contained, then ask for help removing it from the history.

---

## 3. Connect GitHub to Render, and 4–5. Create the web service and the database
Render can create **both** the website and the database from the `render.yaml` file in the project (a "Blueprint").

1. Open https://dashboard.render.com, click **New +** (top right), then **Blueprint**.
2. Under "Connect a repository", click **Configure GitHub** (or **Connect GitHub**).
   - Allow Render to access **only** the `bunyah` repository, then click **Install**.
3. Back on Render, choose the `bunyah` repository and click **Connect**.
4. Render reads `render.yaml` and shows what it will create:
   - **bunyah-testing**: a Web Service on the Free plan.
   - **bunyah-testing-db**: a PostgreSQL database on the Free plan.
5. It asks for the values marked "sync: false":
   - **PUBLIC_BASE_URL**: type `https://bunyah-testing.onrender.com`. If Render later shows a different address, come back and correct it (step 7).
   - **ADMIN_EMAILS**: leave empty. In demo mode the demo administrator already exists.
6. Give the Blueprint a name (`bunyah`) and click **Apply**.

**Success looks like:** both items appear in your dashboard. The database becomes "Available" in about a minute. The web
service shows "Build in progress", then **"Live"** after a few minutes.

---

## 6. How the app connects to the database
You don't type anything for this. In `render.yaml`, `DATABASE_URL` is filled in automatically with the database's
connection string (`fromDatabase`).

To check: open **bunyah-testing → Environment**. You will see `DATABASE_URL` with a hidden value. **Never copy it into
e-mails or chats**, because it contains the database password.

---

## 7. Environment variables (settings)
Open **bunyah-testing → Environment** to see or change them. After a change, click **Save, rebuild, and deploy**.

| Name | Testing value | Meaning |
|---|---|---|
| `ENV` | `production` | Secure cookies and HTTPS headers |
| `SECRET_KEY` | (generated by Render) | Signs login cookies. Never share it or change it casually: changing it logs everyone out |
| `DATABASE_URL` | (from the database) | Where the data lives |
| `DEMO_MODE` | `true` | Creates fictional demo accounts and one-click logins. **Must be `false` for real users** |
| `STORAGE_BACKEND` | `database` | Uploaded files are stored inside PostgreSQL (see step 10) |
| `CURRENCY` | `SAR` | Currency shown |
| `PUBLIC_BASE_URL` | your address | Used in invitation links |
| `ADMIN_EMAILS` | empty or e-mails | Extra administrator accounts (register first, then add the e-mail) |

Business rules such as fees, the 90-working-day limit and review windows are **not** environment variables. Change them
inside the app: **Administration → Settings / Platform fees**.

---

## 8. Build and start commands (already set)
These come from `render.yaml`. You can see them under **bunyah-testing → Settings → Build & Deploy**.
- **Build command:** `pip install -r requirements.txt` installs the program's building blocks.
- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`
- **Health check path:** `/health`. Render opens it to check the site is alive.

---

## 9. Database migrations
A *migration* is a small, versioned script that updates the database structure without losing data.

**You don't need to run anything.** Every time the app starts, it applies any missing migrations automatically
(`app/migrate.py`). The deploy log shows lines like `Running upgrade 0001 -> 0002`.

Render's separate "pre-deploy command" feature is only for paid services, so this project doesn't depend on it.

Before any upgrade of a database with real data, take a backup (step 15).

---

## 10. File storage (engineering drawings, PDFs…)
On Render, a service's own disk is **temporary**. Render's documentation says Free web services cannot attach a
persistent disk, and local files are lost on every redeploy, restart or spin-down.

That is why the testing setup uses `STORAGE_BACKEND=database`: files are stored inside PostgreSQL, so they survive
restarts and are included in database backups.

**Limits of this approach**
- The free database has **1 GB** in total.
- Large BIM models (RVT, ZIP) fill it quickly. Uploads are limited to 25 MB each.

**For production:** use object storage (for example Amazon S3, Cloudflare R2 or a Saudi-hosted equivalent). The code
has a storage layer (`app/services/storage.py`) ready for one more backend. Where files may be stored is part of
decision **D2** (personal-data hosting), so this needs your decision and possibly legal advice.

The alternative is a paid Render persistent disk with `STORAGE_BACKEND=local`.

---

## 11. Front end and back end
They are **one** service: the same app serves the pages (`/`) and the API (`/api/v1`). There is no separate front-end
deployment and no cross-site setup to configure.

---

## 12. Test the deployed site
1. Open your address, for example `https://bunyah-testing.onrender.com`.
   - On the free plan, the first visit after 15 minutes without visitors takes about a minute, because the server is waking up.
2. Check the padlock in the address bar (HTTPS).
3. Open `https://…/health`. It should show `{"status":"ok"}`.
4. Click **Log in**. You should see **Demo accounts**. Work through the scenarios in `docs/DELIVERY_REPORT.md` (section 6).
5. Switch **العربية / English** in the top bar and check that both layouts look right.
6. Open `https://…/api/docs` to see the API documentation.

---

## 13. Read the logs and find errors
Open **bunyah-testing → Logs**.

- A healthy start ends with `BUNYAH started (env=production, demo_mode=True, storage=database). Payments are SIMULATED.`
- Common problems:

| You see | Meaning | Fix |
|---|---|---|
| `SECRET_KEY must be set to a long random value` | Secret missing | Environment → `SECRET_KEY` → **Generate**, then save and deploy |
| `could not connect to server` / `password authentication failed` | Database not ready or wrong URL | Wait until the database is "Available"; check `DATABASE_URL` comes from the database |
| `ModuleNotFoundError` | Install failed | Look higher in the **build** log; make sure `requirements.txt` was uploaded |
| `Exited with status 1` right after `Running upgrade` | A migration failed | Don't retry repeatedly – copy the log lines and ask for help |
| Site shows "Service unavailable" for ~1 minute | Free plan waking up | Wait; a paid plan stays awake |

Use the **Events** tab to see each deploy and whether it succeeded.

---

## 14. Update the site after changes
1. Make or receive the code change on your computer.
2. In GitHub Desktop, write a summary and click **Commit to main**, then **Push origin**.
3. Render notices the push and rebuilds automatically: by default, Render redeploys whenever you push to the linked branch.
   Watch **Events**: "Deploy live" means done.
4. To undo a bad version: **Events** → find the last good deploy → **Rollback**.

To pause automatic deploys: **Settings → Build & Deploy → Auto-Deploy → No**.

---

## 15. Back up and restore the database
**Free database: there are no backups.** Render's documentation states that free Postgres databases don't support any
form of backups. Free databases also **expire 30 days after creation**. After that you have 14 days to upgrade, then Render
deletes the database. This is fine for a short test with fictional data, and **not acceptable for real data**.

**Paid database**
- *Point-in-time recovery*: Render continuously backs up paid databases.
  - The recovery window is 3 days on the Hobby workspace plan and 7 days on Pro or higher.
  - To restore: **database → Recovery → Restore Database**, choose a time (at least 10 minutes ago), and click
    **Start Recovery**. This creates a **new** database. Check it, then point `DATABASE_URL` at it.
- *Manual export*: **database → Recovery → Create export**. You get a `.dir.tar.gz` file, which Render keeps for 7 days.
  Download it and keep it somewhere safe; it contains everything, including uploaded files.
- Restore an export only into an **empty** database (ask for help: it needs PostgreSQL command-line tools).

---

## 16. Custom domain and HTTPS
Do this only when you have a domain (for example `bunyah.sa`) and are close to a real pilot.
1. **bunyah-testing → Settings → Custom Domains → Add Custom Domain**. Enter for example `app.bunyah.sa`.
2. Render shows a DNS record, usually a **CNAME** pointing to `bunyah-testing.onrender.com`.
3. Log in where you bought the domain, open its **DNS** settings and add that record exactly.
4. Back on Render, click **Verify**. Once verified, Render issues the HTTPS certificate automatically and free of charge.
5. Update `PUBLIC_BASE_URL` to the new address.

A `.sa` domain is registered through SaudiNIC-accredited registrars, which have their own requirements.

---

## 17. What it can cost
Render's pricing page could not be read automatically when this guide was written, so **no prices are quoted here**.
Check https://render.com/pricing before choosing a plan.

| Item | Free plan | When you would pay |
|---|---|---|
| Web service | Free: sleeps after 15 minutes without visitors (about 1 minute to wake), 750 free hours per month per workspace, no persistent disk | A paid instance (monthly) for always-on and a pre-deploy step |
| PostgreSQL | Free: 1 GB, **expires after 30 days**, no backups | A paid database (monthly) for anything that must be kept, with backups |
| Persistent disk | Not available on free | Paid per GB per month, only if you choose local file storage |
| Workspace plan | Hobby | A paid workspace plan for teams and longer recovery windows |
| Custom domain + HTTPS | HTTPS certificate is free | The domain itself is paid yearly to the registrar |
| Object storage (S3/R2…) | – | Separate provider; monthly per GB stored plus traffic |

For a production pilot, plan at least: one paid web instance, one paid database with backups, object storage and the
domain, **all recurring monthly or yearly**.

Do not buy anything until the D1, D2 and D6 decisions and the legal review are done.

---

## Before any production launch (checklist)
- [ ] Your written approval to launch.
- [ ] `DEMO_MODE=false` (removes demo logins and demo data creation).
- [ ] Paid database with backups, and a restore test done.
- [ ] Object storage decided (D2) and configured.
- [ ] Payment provider and custody model approved (D1); real payments are **not** in this prototype.
- [ ] Model B contract limit and contract template reviewed by a Saudi lawyer (D6).
- [ ] Privacy notice, terms and data-hosting location reviewed under the Saudi PDPL (D2).
- [ ] E-mail delivery set up (notifications are in-app only today).
- [ ] Remaining security items in `docs/DELIVERY_REPORT.md` section 9 addressed.
