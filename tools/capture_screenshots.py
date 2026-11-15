"""Takes screenshots of the key BUNYAH screens with a headless Microsoft Edge or Google Chrome.

Usage (with the app running locally in DEMO_MODE on port 8000):
    python tools/capture_screenshots.py [output_folder]

It uses the one-click demo logins, so it works only against a demo/testing instance. Nothing is sent anywhere
except to http://localhost:8000.
"""
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

BASE = "http://localhost:8000"
PORT = 9333
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "msedge", "google-chrome", "chromium"]

# (file name, demo account, route, language, mobile?)
SHOTS = [
    ("01-landing-ar", None, "/", "ar", False),
    ("02-login-demo-accounts-en", None, "/login", "en", False),
    ("03-org-dashboard-ar", "org_owner", "/dashboard", "ar", False),
    ("04-project-proposals-compare-en", "org_owner", "/projects/{p1}?tab=proposals", "en", False),
    ("05-project-deliverables-versions-ar", "org_reviewer", "/projects/{p4}?tab=deliverables", "ar", False),
    ("06-project-milestones-en", "org_owner", "/projects/{p4}?tab=milestones", "en", False),
    ("07-project-finance-simulated-en", "org_finance", "/projects/{p4}?tab=finance", "en", False),
    ("08-service-applications-compare-ar", "org_owner", "/services/{r1}?tab=applications", "ar", False),
    ("09-service-worklog-billing-en", "org_owner", "/services/{r2}?tab=time", "en", False),
    ("10-engineer-dashboard-ar", "eng_structural", "/dashboard", "ar", False),
    ("11-engineer-profile-en", "eng_structural", "/profile", "en", False),
    ("12-admin-overview-en", "admin", "/admin", "en", False),
    ("13-admin-verification-ar", "admin", "/admin?tab=verifications&status=pending&id={v1}", "ar", False),
    ("14-dispute-case-en", "admin", "/disputes/{d1}", "en", False),
    ("15-admin-settings-fees-ar", "admin", "/admin?tab=settings", "ar", False),
    ("16-mobile-project-workspace-ar", "eng_structural", "/projects/{p4}?tab=deliverables", "ar", True),
    ("17-mobile-dashboard-en", "org_owner", "/dashboard", "en", True),
]


def find_browser() -> str:
    for b in BROWSERS:
        if os.path.exists(b) or shutil.which(b):
            return b if os.path.exists(b) else shutil.which(b)
    raise SystemExit("No Edge or Chrome found.")


class CDP:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def send(self, method, **params):
        self.n += 1
        my = self.n
        await self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == my:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")


async def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp()
    proc = subprocess.Popen([find_browser(), "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                             "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank"])
    try:
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
                ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            c = CDP(ws)
            await c.send("Page.enable")
            await c.send("Page.navigate", url=BASE + "/")
            await asyncio.sleep(1.5)
            H = '{"X-Requested-With":"fetch","Content-Type":"application/json"}'
            await c.js(f'fetch("/api/v1/auth/demo-login",{{method:"POST",headers:{H},body:JSON.stringify({{key:"admin"}})}})')
            ids = await c.js("""(async()=>{
                const j = async u => (await fetch("/api/v1"+u)).json();
                const ps = await j("/admin/projects"); const rs = await j("/admin/service-requests?status=");
                const vs = await j("/admin/verifications"); const ds = await j("/disputes");
                const pid = t => (ps.find(p=>p.title.startsWith(t))||{}).id; const rid = t => (rs.find(r=>r.title.startsWith(t))||{}).id;
                return {p1: pid("Structural design – 4-storey"), p4: pid("Structural design – school"), r1: rid("BIM Specialist"),
                        r2: rid("Site Structural"), v1: (vs[0]||{}).id, d1: (ds[0]||{}).id};
            })()""")
            for name, who, route, lang, mobile in SHOTS:
                if mobile:
                    await c.send("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
                else:
                    await c.send("Emulation.setDeviceMetricsOverride", width=1366, height=900, deviceScaleFactor=1, mobile=False)
                await c.js(f'fetch("/api/v1/auth/logout",{{method:"POST",headers:{H}}})')
                if who:
                    await c.js(f'fetch("/api/v1/auth/demo-login",{{method:"POST",headers:{H},body:JSON.stringify({{key:"{who}"}})}})')
                await c.js(f'localStorage.setItem("bunyah.lang","{lang}")')
                await c.send("Page.navigate", url=BASE + "/#" + route.format(**ids))
                await asyncio.sleep(2.2)
                await c.send("Page.reload")
                await asyncio.sleep(2.2)
                height = await c.js("Math.min(document.documentElement.scrollHeight, 2600)")
                w = 390 if mobile else 1366
                shot = await c.send("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                                    clip={"x": 0, "y": 0, "width": w, "height": height, "scale": 1})
                (out / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
                print("saved", name)
            await c.js(f'fetch("/api/v1/auth/logout",{{method:"POST",headers:{H}}})')
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")))
