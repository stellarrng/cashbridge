"""T02: real-browser end-to-end test (Chromium via Playwright) against a live uvicorn server.

    make e2e            (or: python -m pytest -m e2e tests/e2e -v)

Story: landing -> Chief accountant drafts the pack with the Autopilot -> refresh keeps the session ->
the accountant cannot reach the bank portal (UI and API) -> Director signs in with a passcode,
enters a wrong then the right action-bound OTP -> Credit reviewer opens the released case,
verifies the hashes and records the (MOCK) decision -> the SME sees the lender's answer.
Then: EN/VI/ZH without raw translation keys, a 375 px phone viewport without horizontal scrolling,
keyboard Escape on the OTP dialog, and no JavaScript errors anywhere.

Screenshots land in reports/e2e/. Skipped automatically when Playwright or Chromium is missing.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")
pyotp = pytest.importorskip("pyotp")

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "reports" / "e2e"
DEMO_OTP = "JBSWY3DPEHPK3PXP"
RAW_KEY = re.compile(r"\b(?:nav|ov|fund|bk|ap|app|grp|role|core|ws|lbl|btn|next|tr2|st|ev|chk|opt|col)\.[a-z][A-Za-z0-9_.]*\b")
CHROMIUM = os.environ.get("CASHBRIDGE_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    port = _free_port()
    env = {**os.environ, "CASHBRIDGE_ENV": "demo", "CASHBRIDGE_RUNTIME_DIR": str(tmp / "runtime"), "OTP_SECRET": DEMO_OTP,
           "CASHBRIDGE_SESSION_SECRET": "e2e-" + "x" * 40}
    for k in ("CASHBRIDGE_WORKSPACE_DB", "CASHBRIDGE_REQUIRE_DATA_GATE", "CASHBRIDGE_QUALITY_MANIFEST_PATH"):
        env.pop(k, None)
    log = open(tmp / "server.log", "wb")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    import httpx
    url = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            if httpx.get(url + "/api/health", timeout=1, trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not start: " + (tmp / "server.log").read_text())
    yield url
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def browser():
    exe = CHROMIUM if Path(CHROMIUM).exists() else None
    with playwright_sync.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        except Exception as error:  # no browser installed on this machine
            pytest.skip(f"Chromium unavailable: {error}")
        yield b
        b.close()


class Page:
    """Thin helper: one browser context per persona, console errors collected, screenshots named."""

    def __init__(self, browser, base, viewport=None, lang=None):
        self.ctx = browser.new_context(viewport=viewport or {"width": 1366, "height": 900}, service_workers="block")
        if lang:
            self.ctx.add_init_script(f"try {{ localStorage.setItem('cb.lang', '{lang}'); }} catch (e) {{}}")
        self.page = self.ctx.new_page()
        self.base = base
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        self.page.on("console", lambda m: self.errors.append(f"console.{m.type}: {m.text}")
                     if m.type == "error" and "Failed to load resource" not in m.text else None)
        self.page.on("dialog", lambda d: d.dismiss())

    def go(self, path):
        self.page.goto(self.base + path)
        self.page.wait_for_load_state("networkidle")

    def shot(self, name):
        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)

    def demo_sign_in(self, user, portal="sme"):
        self.go(f"/?signin={portal}")
        self.page.locator(f'[data-user="{user}"]').first.click()
        self.page.wait_for_url(re.compile(r"/app#"))
        self.page.wait_for_load_state("networkidle")

    def form_sign_in(self, user, passcode, portal="sme"):
        self.go(f"/?signin={portal}")
        self.page.fill("#loginUser", user)
        self.page.fill("#loginPass", passcode)
        self.page.click("#loginBtn")
        self.page.wait_for_url(re.compile(r"/app#"))
        self.page.wait_for_load_state("networkidle")

    def route(self, name):
        self.page.evaluate(f"location.hash = '{name}'")
        self.page.wait_for_load_state("networkidle")
        self.wait_js("!document.querySelector('#page > p.muted') || document.querySelector('#page').children.length > 1")

    def wait_js(self, expr, timeout=15000):
        """Poll a JS expression with evaluate(): wait_for_function needs eval, which our CSP forbids."""
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            if self.page.evaluate(f"() => Boolean({expr})"):
                return
            self.page.wait_for_timeout(100)
        raise AssertionError(f"timed out waiting for: {expr}")

    def api_status(self, path):
        return self.page.evaluate("""async (p) => {
            const s = JSON.parse(sessionStorage.getItem('cb.session') || 'null');
            const r = await fetch(p, {headers: {Authorization: 'Bearer ' + (s && s.token)}});
            return r.status; }""", path)

    def no_horizontal_scroll(self):
        return self.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    def close(self):
        self.ctx.close()


def test_full_three_role_journey(server, browser):
    # ---- landing
    visitor = Page(browser, server)
    visitor.go("/")
    assert "CashBridge" in visitor.page.title()
    visitor.shot("01_landing")
    visitor.close()

    # ---- Chief accountant drafts the pack
    acc = Page(browser, server)
    acc.demo_sign_in("sme.lan")
    assert "#overview" in acc.page.url
    acc.shot("02_accountant_overview")
    acc.route("autopilot")
    acc.page.click("#apRun")
    acc.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('awaiting approval')", timeout=30000)
    acc.shot("03_accountant_autopilot_pack_drafted")

    # refresh keeps the session and the page
    acc.page.reload()
    acc.page.wait_for_load_state("networkidle")
    assert "#autopilot" in acc.page.url and acc.page.locator("#apRun").is_visible()

    # wrong-role route: the UI falls back to the role's home and the API refuses
    acc.route("inbox")
    assert acc.page.locator('#side a[aria-current="page"]').get_attribute("href") == "#overview"
    assert acc.api_status("/api/bank/inbox") == 403
    acc.route("funding")
    assert acc.page.locator("#approveBtn").count() == 0  # the preparer is never offered the approval
    acc.page.locator("#sideLogout").scroll_into_view_if_needed()
    try:
        with acc.page.expect_navigation(url=re.compile(r"signedout=1"), wait_until="commit", timeout=20000):
            acc.page.click("#sideLogout")
    except Exception:
        acc.shot("ERROR_signout")
        raise
    assert acc.api_status("/api/snapshot") == 401
    acc.close()

    # ---- Director approves with a passcode sign-in and the action-bound OTP
    director = Page(browser, server)
    director.form_sign_in("sme.minh", "minh-demo-2026")
    assert "#core" in director.page.url
    director.page.wait_for_selector("#packWaiting")  # the pending approval is shown separately from cash-flow alerts
    body = director.page.inner_text("#page")
    assert "Nothing needs a decision" not in body
    plan = director.page.evaluate("""async () => { const s = JSON.parse(sessionStorage.getItem('cb.session'));
        const r = await fetch('/api/intelligence', {headers: {Authorization: 'Bearer ' + s.token}}); return (await r.json()).plan; }""")
    if plan and plan["status"] == "GOAL_NOT_REACHABLE":  # a plan under the target is never presented as meeting it
        assert "Best available plan" in body and director.page.locator(".kpi.hl", has_text="Best available").count() == 0
    director.shot("04_director_decision_center")
    # the user card at the bottom of the sidebar must not cover "Sign out" (regression seen in v7)
    assert director.page.evaluate("""() => { const b = document.querySelector('#sideLogout'); const side = document.querySelector('#side');
        side.scrollTop = 0; const r = b.getBoundingClientRect(); const sr = side.getBoundingClientRect();
        if (r.top >= sr.bottom) return true;  // below the fold: reachable by scrolling, not hidden behind anything
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return hit === b || b.contains(hit); }""")
    director.route("funding")
    director.page.click("#approveBtn")
    director.page.wait_for_selector("#otpModal:not([hidden])")
    director.page.keyboard.press("Escape")
    assert director.page.locator("#otpModal").is_hidden()
    director.page.click("#approveBtn")
    director.page.wait_for_selector("#otpModal:not([hidden])")
    good = pyotp.TOTP(DEMO_OTP).now()
    director.page.fill("#otpCode", f"{(int(good) + 500000) % 1000000:06d}")
    director.page.click("#otpApprove")
    director.wait_js("document.querySelector('#otpErr').textContent.length > 0")
    director.shot("05_director_wrong_otp")
    director.page.fill("#otpCode", pyotp.TOTP(DEMO_OTP).now())
    director.page.click("#otpApprove")
    director.page.wait_for_selector("#otpModal", state="hidden")
    director.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('submitted')", timeout=20000)
    director.shot("06_director_released")
    director.close()

    # ---- Credit reviewer
    bank = Page(browser, server)
    bank.demo_sign_in("bank.lihua", portal="bank")
    assert "#inbox" in bank.page.url
    bank.page.wait_for_selector("a.inbox-item")
    bank.shot("07_bank_inbox")
    assert bank.api_status("/api/snapshot") == 403
    bank.page.click("a.inbox-item")
    bank.page.wait_for_selector("#bverify")
    bank.page.click("#bverify")
    bank.page.wait_for_selector("#checks ul.checks")
    assert bank.page.locator("#checks .mark.no").count() == 0
    bank.page.select_option("#bdec select[name=decision]", "APPROVE_FUNDING")
    bank.page.fill("#bdec textarea[name=note]", "KYC done offline; notice of assignment sent (E2E).")
    bank.page.click("#bdec button")
    bank.page.wait_for_selector("#bdec", state="detached")
    bank.shot("08_bank_case_decided")
    bank.close()

    # ---- SME sees the outcome
    acc2 = Page(browser, server)
    acc2.demo_sign_in("sme.lan")
    acc2.route("funding")
    acc2.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('funded')")
    acc2.shot("09_accountant_sees_lender_decision")
    acc2.close()

    for p in (visitor, acc, director, bank, acc2):
        assert p.errors == [], p.errors


@pytest.mark.parametrize("lang,word", [("vi", "Tổng quan"), ("zh", "总览"), ("en", "Overview")])
def test_languages_render_without_raw_keys(server, browser, lang, word):
    p = Page(browser, server, lang=lang)
    p.demo_sign_in("sme.lan")
    seen = []
    for route in ("overview", "funding", "workspace", "trust", "settings"):
        p.route(route)
        text = p.page.inner_text("body")
        seen += [f"{route}: {k}" for k in RAW_KEY.findall(text)]
    assert word in p.page.inner_text("#side")
    p.shot(f"10_lang_{lang}_settings")
    assert seen == [], seen[:20]
    assert p.errors == [], p.errors
    p.close()


def test_phone_viewport_has_no_horizontal_scroll(server, browser):
    phone = {"width": 375, "height": 812}
    p = Page(browser, server, viewport=phone)
    p.go("/")
    wide = [] if p.no_horizontal_scroll() else ["landing"]
    p.shot("11_mobile_landing")
    p.demo_sign_in("sme.lan")
    for route in ("overview", "autopilot", "cash", "funding", "workspace", "trust"):
        p.route(route)
        if not p.no_horizontal_scroll():
            wide.append(route)
            p.shot(f"11_mobile_overflow_{route}")
    p.shot("11_mobile_funding")
    b = Page(browser, server, viewport=phone)
    b.demo_sign_in("bank.lihua", portal="bank")
    if not b.no_horizontal_scroll():
        wide.append("bank inbox")
    b.shot("11_mobile_bank_inbox")
    assert wide == [], wide
    assert p.errors == [] and b.errors == [], p.errors + b.errors
    p.close()
    b.close()


def test_director_sends_pack_back_and_accountant_reworks(server, browser):
    acc = Page(browser, server)
    acc.demo_sign_in("sme.lan")
    acc.route("autopilot")
    acc.page.click("#apRun")
    acc.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('awaiting approval')", 30000)
    director = Page(browser, server)
    director.demo_sign_in("sme.minh")
    director.route("funding")
    director.page.click("#rejectBtn")
    director.page.wait_for_selector("#rejectModal:not([hidden])")
    director.page.click("#rejectSend")  # empty reason is refused in the dialog
    assert director.page.inner_text("#rejectErr").strip()
    director.page.fill("#rejectReason", "Use the bridge loan: the buyer asked us not to assign this invoice.")
    director.page.click("#rejectSend")
    director.page.wait_for_selector("#rejectModal", state="hidden")
    director.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('needs human')")
    director.shot("12_director_sent_back")
    acc.route("overview")
    acc.route("funding")
    acc.page.wait_for_selector("#reopen")
    acc.page.click("#reopen")
    acc.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('invoice verified')")
    acc.shot("13_accountant_rework")
    assert acc.errors == [] and director.errors == [], acc.errors + director.errors
    acc.close()
    director.close()


def test_lender_evidence_loop_in_the_browser(server, browser, tmp_path):
    import hashlib
    acc = Page(browser, server)
    acc.demo_sign_in("sme.lan")
    acc.route("autopilot")
    acc.page.click("#apRun")
    acc.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('awaiting approval')", 30000)
    director = Page(browser, server)
    director.demo_sign_in("sme.minh")
    director.route("funding")
    director.page.click("#approveBtn")
    director.page.fill("#otpCode", pyotp.TOTP(DEMO_OTP).now())
    director.page.click("#otpApprove")
    director.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('submitted')", 20000)
    director.close()

    bank = Page(browser, server)
    bank.demo_sign_in("bank.lihua", portal="bank")
    bank.route("workspace")
    try:
        bank.page.wait_for_selector("#cb-evopen", timeout=45000)
    except Exception:  # keep what the page showed, to diagnose instead of guessing
        bank.shot("ERROR_bank_workspace")
        (SHOTS / "ERROR_bank_workspace.txt").write_text(bank.page.url + "\n" + bank.page.inner_text("body") + "\n" + "\n".join(bank.errors))
        raise
    bank.page.fill("#cb-evopen input[name=item]", "Signed bill of lading")
    bank.page.fill("#cb-evopen textarea[name=detail]", "Carrier-signed copy for the INV-1030 shipment")
    bank.page.click("#cb-evopen button[type=submit]")
    bank.page.wait_for_selector("[data-evr]")
    assert "Blocking the funding decision" in bank.page.inner_text("#page")

    doc = tmp_path / "bill_of_lading.pdf"
    doc.write_bytes(b"%PDF-1.4 synthetic bill of lading for the E2E test")
    acc.route("overview")
    acc.route("workspace")
    acc.page.wait_for_selector("[data-evsubmit]")
    assert "Signed bill of lading" in acc.page.inner_text("#page")  # notification + request
    acc.page.fill("[data-evsubmit] input[name=ref]", "DOC-BL-1030")
    acc.page.set_input_files("[data-evsubmit] input[name=file]", str(doc))
    acc.page.click("[data-evsubmit] button[type=submit]")
    acc.wait_js("document.querySelector('[data-evr] .pill') && document.querySelector('[data-evr]').textContent.includes('DOC-BL-1030')")
    expected = hashlib.sha256(doc.read_bytes()).hexdigest()[:16]
    assert expected in acc.page.inner_text("[data-evr]")  # hashed by the server from the uploaded bytes
    acc.shot("14_sme_evidence_submitted")

    bank.route("inbox")
    bank.route("workspace")
    bank.page.fill("[data-evreason]", "Carrier signature matches the B/L register")
    bank.page.click('[data-evreview][data-ok="true"]')  # not opened yet -> refused
    bank.wait_js("document.querySelector('#toast') && document.querySelector('#toast').textContent.includes('Open the uploaded document')")
    with bank.page.expect_download() as dl:
        bank.page.click("[data-evopen]")
    assert Path(dl.value.path()).read_bytes() == doc.read_bytes()  # the lender receives exactly what the SME uploaded
    bank.wait_js("document.querySelector('[data-evr]') && document.querySelector('[data-evr]').textContent.includes('opened by lender')")
    bank.page.fill("[data-evreason]", "Carrier signature matches the B/L register")
    bank.page.click('[data-evreview][data-ok="true"]')
    bank.wait_js("document.querySelector('#page').textContent.includes('Ready for a funding decision')")
    bank.shot("15_bank_evidence_accepted")
    assert acc.errors == [] and bank.errors == [], acc.errors + bank.errors
    acc.close()
    bank.close()


def test_click_a_pack_number_to_see_its_source_and_correct_it_four_eyes(server, browser):
    acc = Page(browser, server)
    acc.demo_sign_in("sme.lan")
    acc.route("autopilot")
    acc.page.click("#apRun")
    acc.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('awaiting approval')", 30000)
    acc.route("funding")
    acc.page.click('[data-prov="invoice_amount_usd"]')
    acc.wait_js("document.querySelector('#provModal') && !document.querySelector('#provModal').hidden && document.querySelector('#provDialog mark')")
    text = acc.page.inner_text("#provDialog")
    assert acc.page.inner_text("#provDialog mark").startswith("60,000.00")  # the exact characters in the scanned invoice
    assert "SCAN-INV-1030" in text and "No OCR coordinates" in text and "matches the locked value" in text
    acc.shot("17_provenance_click_to_source")
    acc.page.select_option("#pvForm select[name=source_ref]", "SCAN-INV-1030:amount")
    acc.page.fill("#pvForm input[name=proposed_value]", "59000.00")
    acc.page.fill("#pvForm textarea[name=reason]", "Credit note CN-12 reduces the invoice")
    acc.page.click("#pvForm button[type=submit]")
    acc.wait_js("document.querySelector('#provDialog').textContent.includes('59000.00') && document.querySelector('#provDialog').textContent.includes('COR-')")
    assert acc.page.query_selector("[data-cdec]") is None  # the preparer cannot decide their own correction
    director = Page(browser, server)
    director.demo_sign_in("sme.minh")
    director.route("funding")
    director.page.click('[data-prov="invoice_amount_usd"]')
    director.wait_js("document.querySelector('[data-cdec]') !== null")
    director.page.fill("[data-cnote]", "Checked CN-12 against the ledger")
    director.page.click('[data-cdec][data-ok="true"]')
    director.wait_js("document.querySelector('#provDialog').textContent.includes('Applies to the next pack')")
    assert "60,000.00" in director.page.inner_text("#provDialog")  # locked value unchanged
    assert acc.errors == [] and director.errors == [], acc.errors + director.errors
    acc.close()
    director.close()


@pytest.mark.parametrize("viewport", [{"width": 1366, "height": 768}, {"width": 375, "height": 812}], ids=["laptop", "phone"])
def test_each_roles_next_action_is_on_the_first_screen(server, browser, viewport):
    """Guidance-free check: on sign-in, the thing this person must do next is visible without scrolling."""
    def on_first_screen(p, selector):
        return p.page.evaluate("""(sel) => { const el = document.querySelector(sel); if (!el) return false;
            const r = el.getBoundingClientRect(); return r.width > 0 && r.top >= 0 && r.bottom <= window.innerHeight; }""", selector)

    acc = Page(browser, server, viewport=viewport)
    acc.demo_sign_in("sme.lan")
    # The React overview leads with a "Next step" card; the work-queue tile follows. Either link to the Autopilot counts.
    assert on_first_screen(acc, '#page a[href="#autopilot"]'), "accountant: the way to prepare funding is not on the first screen"
    acc.shot(f"16_first_screen_accountant_{viewport['width']}")
    acc.route("autopilot")
    acc.page.click("#apRun")
    acc.wait_js("document.querySelector('#caseTag').textContent.toLowerCase().includes('awaiting approval')", 30000)

    director = Page(browser, server, viewport=viewport)
    director.demo_sign_in("sme.minh")
    assert (on_first_screen(director, '#side a[href="#funding"]') or on_first_screen(director, '.work-tile[href="#funding"]')
            or on_first_screen(director, '#packWaiting a[href="#funding"]')), \
        "director: the approval is not reachable from the first screen"
    director.shot(f"16_first_screen_director_{viewport['width']}")
    assert acc.errors == [] and director.errors == [], acc.errors + director.errors
    acc.close()
    director.close()
