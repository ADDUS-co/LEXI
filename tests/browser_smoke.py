"""Functional browser checks. Start Flask first; install Playwright separately.

Run: python tests/browser_smoke.py
Optional: LEXI_TEST_URL, CHROMIUM_PATH. Screenshots are written to test-results/.
"""
from datetime import date, timedelta
from itertools import combinations
import json
import os
from pathlib import Path
import shutil
import sys
import time
from auth_support import BrowserAccount, choose_guide_language, advance_guide_time, finish_onboarding

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lexi.selection import select_word

BASE = os.environ.get("LEXI_TEST_URL", "http://127.0.0.1:5000").rstrip("/")
OUTPUT = ROOT / "test-results"
OUTPUT.mkdir(exist_ok=True)
checks = []


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label)
    print("PASS", label, flush=True)


def state(page):
    return page.evaluate("JSON.parse(localStorage.getItem('lexi:account:'+localStorage.getItem('lexi:active-account')+':v2'))")


def go(page, route):
    page.evaluate("route => { location.hash = route; }", route)
    expect(page.locator('[data-nav="' + ("home" if route.startswith("word/") else route) + '"]')).to_have_attribute("aria-current", "page")


def no_overflow(page, label):
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(60)
    check(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), label)


def run():
    with sync_playwright() as p:
        fixture=BrowserAccount(p,BASE)
        catalog=fixture.catalog
        executable = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("google-chrome")
        browser = p.chromium.launch(executable_path=executable, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, service_workers="block", timezone_id="Asia/Bishkek", permissions=["clipboard-read", "clipboard-write"])
        fixture.authenticate(context)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE, wait_until="networkidle")
        expect(page.locator("#onboarding-dialog")).to_be_visible()
        choose_guide_language(page)
        check(page.locator("#begin-button").is_disabled(), "First visit requires at least one interest")
        check(state(page)["history"] == [], "Onboarding preview does not record a word")
        page.locator("#onboarding-update-time").fill("00:00")
        advance_guide_time(page)
        for collection in ("law", "technology"):
            page.locator(f'input[name="onboarding"][value="{collection}"]').check()
        finish_onboarding(page)
        expect(page.locator("#onboarding-dialog")).not_to_be_visible()
        initial_id = state(page)["history"][0]["id"]
        initial_word = next(word for word in catalog["words"] if word["id"] == initial_id)
        expect(page.locator("#daily-word")).to_have_text(initial_word["word"] + ".")
        page.reload(wait_until="networkidle")
        check(not page.locator("#onboarding-dialog").is_visible() and len(state(page)["history"]) == 1, "Reload preserves interests and does not duplicate today's history")
        page.locator('[data-action="save"]').first.click()
        expect(page.locator("#saved-count")).to_have_text("1")
        page.reload(wait_until="networkidle")
        check(state(page)["saved"] == [initial_id], "Saved word persists across reload")
        page.locator('[data-action="synonym"]').first.click()
        expect(page.locator("#detail-dialog")).to_contain_text(initial_word["synonyms"][0]["definition"])
        page.keyboard.press("Escape")
        expect(page.locator("#detail-dialog")).not_to_be_visible()
        check(page.locator('[data-action="synonym"]').first.evaluate("e => e === document.activeElement"), "Synonym dialog supports Escape and restores focus")
        page.locator('[data-action="share"]').click()
        check(initial_id in page.evaluate("navigator.clipboard.readText()"), "Share copies a working word deep link")
        page.locator('[data-action="pronounce"]').click()
        page.wait_for_timeout(250)
        check(not errors, "Pronunciation action does not throw a JavaScript error")

        for theme in ("studio", "experimental", "noir"):
            go(page, "settings")
            page.locator(f'[data-theme-choice="{theme}"]').click()
            go(page, "home")
            expect(page.locator("#daily-word")).to_have_text(initial_word["word"] + ".")
            check(page.locator("html").get_attribute("data-theme") == theme, f"{theme}: theme changes without changing daily word")
            if theme == "studio":
                page.wait_for_timeout(300)
                check(page.locator("#daily-word").evaluate("e => getComputedStyle(e).color") == "rgb(83, 102, 51)", "Studio word uses a distinct olive color")
        go(page, "settings")
        page.locator("#motion-toggle").check()
        go(page, "home")
        check(page.locator("#daily-word").evaluate("e => getComputedStyle(e).animationName") == "none", "Reduced-motion preference disables entrance animation")

        go(page, "collections")
        for checkbox in page.locator('input[name="interests"]').all():
            checkbox.uncheck()
        check(page.locator('[data-action="apply-collections"]').is_disabled(), "Collections cannot be saved empty")
        next_collection = next(c["id"] for c in catalog["collections"] if select_word(catalog["collections"], catalog["words"], [c["id"]], catalog["today"])["id"] != initial_id)
        page.locator(f'input[name="interests"][value="{next_collection}"]').check()
        page.locator('[data-action="apply-collections"]').click()
        expect(page.locator("#daily-word")).to_be_visible()
        new_word = select_word(catalog["collections"], catalog["words"], [next_collection], catalog["today"])
        expect(page.locator("#daily-word")).to_have_text(new_word["word"] + ".")
        check(len(state(page)["history"]) == 2, "Changing interests recalculates and records only the viewed new word")
        go(page, "saved")
        expect(page.locator(".word-card")).to_have_count(1)
        page.locator(".word-card-main").click()
        expect(page.locator("#daily-word")).to_have_text(initial_word["word"] + ".")
        go(page, "saved")
        page.locator('[data-action="save"]').click()
        expect(page.locator("#saved-count")).to_have_text("0")
        check(page.locator(".empty-state").is_visible(), "Removing the last saved word shows a meaningful empty state")
        go(page, "history")
        check(page.locator(".word-card").count() == 2, "History contains the two encountered words, not the vocabulary database")
        page.locator("#word-search").fill("no-such-word-xyz")
        expect(page.locator("#word-list")).to_contain_text("No words found")
        page.locator('[data-action="clear-search"]').click()
        check(page.locator(".word-card").count() == 2, "Search and clear operate on real encountered words")
        future_word = next(word for word in catalog["words"] if word["id"] not in {initial_id, new_word["id"]})
        page.evaluate("async id => { const s=await import('/static/js/storage.js');s.updateStore({history:[...s.readStore().history,{id,date:'2999-01-01'}]}); }", future_word["id"])
        page.wait_for_function("()=>!JSON.parse(localStorage.getItem('lexi:sync:'+localStorage.getItem('lexi:active-account')+':v2')).dirty")
        page.reload(wait_until="networkidle")
        check(page.locator(".word-card").count() == 2, "Future-dated entries are excluded from History")

        cases = []
        ids = [c["id"] for c in catalog["collections"]]
        days = ["2024-02-29", "2024-12-31", "2025-01-01", "2028-02-29"] + [(date(2026, 10, 1) + timedelta(days=i)).isoformat() for i in range(35)]
        for size in range(1, len(ids) + 1):
            for selected in combinations(ids, size):
                cases.extend({"selected": list(selected), "day": day, "expected": select_word(catalog["collections"], catalog["words"], selected, day)["id"]} for day in days)
        parity = page.evaluate("""async ({catalog,cases}) => {
          const {selectWord,dateInTimezone} = await import('/static/js/selection.js');
          return {matches:cases.every(c=>selectWord(catalog.collections,catalog.words,c.selected,c.day).id===c.expected),
            before:dateInTimezone('Asia/Bishkek',new Date('2026-10-18T17:59:00Z')),
            after:dateInTimezone('Asia/Bishkek',new Date('2026-10-18T18:01:00Z'))};
        }""", {"catalog": catalog, "cases": cases})
        check(parity["matches"], f"Python and browser selectors match in {len(cases)} date/interest cases")
        check(parity["before"] == "2026-10-18" and parity["after"] == "2026-10-19", "Browser respects the Bishkek midnight boundary")

        for width, height in ((1440,1000),(1280,800),(768,1024),(390,844),(320,740)):
            page.set_viewport_size({"width":width,"height":height})
            for theme in ("noir", "studio", "experimental"):
                go(page, "settings")
                page.locator(f'[data-theme-choice="{theme}"]').click()
                go(page, "home")
                no_overflow(page, f"{theme}: no horizontal overflow at {width}px")
                if width in (1440,390):
                    page.screenshot(path=str(OUTPUT / f"{theme}-{width}.png"))
            for route in ("collections", "history", "saved", "settings"):
                go(page, route)
                no_overflow(page, f"{route}: responsive at {width}px")

        page.set_viewport_size({"width":1440,"height":1000})
        go(page, "home")
        page.locator('[data-action="explore"]').click()
        expect(page.locator("#beyond-title")).to_be_in_viewport()
        check(page.locator(".definition-block").inner_text().find(new_word["fullDefinition"]) >= 0, "Scroll reveals the full definition of the same word")
        for url in ("https://www.instagram.com/arddashh/", "https://t.me/whynotifye1", "tel:+77058733464", "mailto:ardaksok@mail.ru"):
            check(page.locator(f'#site-footer a[href="{url}"]').count() == 1, f"Footer contact wired: {url}")
        go(page, "settings")
        with page.expect_download() as download:
            page.locator('[data-action="export"]').click()
        payload = json.loads(Path(download.value.path()).read_text())
        check(payload["app"] == "LEXI" and payload["preferences"]["interests"] == [next_collection], "Export downloads the user's actual local data")
        page.locator('[data-action="reset"]').click()
        page.locator('[data-action="close-dialog"]').last.click()
        check(state(page)["onboarded"], "Canceling reset preserves data")
        page.locator('[data-action="reset"]').click()
        page.locator('[data-action="confirm-reset"]').click()
        expect(page.locator("#onboarding-dialog")).to_be_visible()
        choose_guide_language(page)
        cleared = state(page)
        check(cleared is None or (cleared["history"] == [] and cleared["saved"] == []), "Confirmed reset clears data and returns to onboarding")
        check(not errors, "No uncaught JavaScript errors in user flows")
        context.close()

        # Bad backend data: error is visible; retry really fetches again.
        context = browser.new_context(service_workers="block")
        fixture.authenticate(context)
        page = context.new_page()
        page.route("**/api/catalog", lambda route: route.fulfill(status=503, json={"error":"The vocabulary could not be loaded. Check the JSON data."}))
        page.goto(BASE)
        expect(page.locator("#main-content")).to_contain_text("Check the JSON data")
        page.unroute("**/api/catalog")
        page.locator('[data-action="retry"]').click()
        expect(page.locator("#onboarding-dialog")).to_be_visible()
        choose_guide_language(page)
        check(True, "Failed data load displays an error and Retry recovers")
        context.close()

        # Very long words and absent optional fields remain readable.
        context = browser.new_context(viewport={"width":320,"height":740},service_workers="block",reduced_motion="reduce")
        fixture.authenticate(context)
        page = context.new_page()
        modified = json.loads(json.dumps(catalog))
        word = modified["words"][0]
        word["word"] = "Pneumonoultramicroscopicsilicovolcanoconiosis"
        for field in ("synonyms","relatedWords","source","usageNote","difficulty"):
            word.pop(field,None)
        fixture.authenticate(context,{'onboarded':True,'interests':['law']})
        page.route("**/api/catalog",lambda route:route.fulfill(json=modified))
        page.goto(BASE + "/#word/" + word["id"],wait_until="networkidle")
        expect(page.locator("#daily-word")).to_contain_text(word["word"])
        no_overflow(page,"A 45-letter word and missing optional fields work at 320px")
        page.screenshot(path=str(OUTPUT / "long-word-320.png"))
        context.close()

        # A quota failure must preserve preferences in memory in the current tab.
        context = browser.new_context(service_workers="block")
        fixture.authenticate(context)
        page = context.new_page()
        page.add_init_script("Storage.prototype.setItem=function(){throw new DOMException('Storage is full','QuotaExceededError')}")
        page.goto(BASE,wait_until="networkidle")
        choose_guide_language(page)
        advance_guide_time(page)
        page.locator('input[name="onboarding"][value="law"]').check()
        finish_onboarding(page)
        page.locator('[data-action="save"]').first.click()
        go(page,"settings")
        page.locator('[data-theme-choice="studio"]').click()
        go(page,"saved")
        check(page.locator(".word-card").count() == 1 and page.locator("html").get_attribute("data-theme") == "studio", "Storage quota failure retains usable in-memory state")
        context.close()

        # Actual Service Worker and cached API, not a mock offline screen.
        context = browser.new_context(viewport={"width":390,"height":844})
        def delayed_worker(route):
            time.sleep(1)  # Exercise a catalog arriving before first worker activation.
            route.continue_()
        context.route("**/sw.js",delayed_worker)
        fixture.authenticate(context)
        page = context.new_page()
        fixture.authenticate(context,{'onboarded':True,'interests':['technology']})
        page.goto(BASE,wait_until="networkidle")
        page.evaluate("navigator.serviceWorker.ready")
        page.wait_for_function("()=>navigator.serviceWorker.controller !== null")
        page.wait_for_function("async()=>Boolean(await (await caches.open('lexi-shell-v7')).match('/api/catalog'))")
        before = page.locator("#daily-word").inner_text()
        context.set_offline(True)
        page.reload(wait_until="networkidle")
        expect(page.locator("#daily-word")).to_have_text(before)
        page.locator('[data-action="save"]').first.click()
        page.reload(wait_until="networkidle")
        expect(page.locator("#saved-count")).to_have_text("1")
        check(True,"Service Worker reloads vocabulary and preserves Saved fully offline")
        context.close()
        browser.close()
        fixture.dispose()
    (OUTPUT / "browser-results.json").write_text(json.dumps({"passed":len(checks),"checks":checks},indent=2),encoding="utf-8")
    print(f"\n{len(checks)} browser checks passed.",flush=True)


if __name__ == "__main__":
    run()
