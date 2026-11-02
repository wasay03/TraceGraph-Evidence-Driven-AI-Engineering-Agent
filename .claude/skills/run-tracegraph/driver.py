"""Drive the TraceGraph web UI (served at /ui by `tg serve`) with headless Chromium.

Usage (run with a Python that has playwright installed, see SKILL.md):
  driver.py smoke [--base URL] [--key KEY] [--repo ID] [--out DIR]
      Every view end to end: repos, snapshot validation, impact simulate + derivation graph + source,
      invariants, query examples, runs, ontology, phone width. Screenshots to --out, exit 1 on any problem.
  driver.py shot ROUTE [--base URL] [--key KEY] [--out DIR] [--wait SELECTOR]
      Log in, open one hash route (e.g. "#/query", "#/runs/3") and screenshot it.
No step calls an LLM: starting an agent run is the only UI action that does, and the driver never does it.
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def login(page, base: str, key: str) -> None:
    page.goto(base)
    page.wait_for_selector("#api-key")
    page.fill("#api-key", key)
    page.press("#api-key", "Enter")
    page.wait_for_selector("h1:has-text('Repositories')")


def pick_repo(page, repo: str) -> None:
    # The first <select> on impact/query pages is the repository picker; it defaults to the first repo.
    page.select_option("select >> nth=0", repo)
    page.wait_for_timeout(500)


def smoke(page, browser, args, shot, problems) -> None:
    login(page, args.base, args.key)
    print("repos panels:", page.locator("section.panel").count(), "health:", page.get_attribute("#health", "class"))
    shot("1-repos")

    page.locator("tr.clickable").first.click()
    page.wait_for_selector("h1:has-text('Snapshot')")
    page.click("button:has-text('Run validation')")
    page.wait_for_selector("text=Graph is valid")
    shot("2-snapshot")

    page.goto(args.base + "#/impact")
    page.wait_for_selector("h1:has-text('Impact')")
    pick_repo(page, args.repo)
    page.fill("input[placeholder='orders.status']", "orders.discount_code")
    page.click("button:has-text('Simulate')")
    page.wait_for_selector("h2:has-text('Findings')")
    print("impact findings:", page.locator("tr.clickable").count())
    page.locator("tr.clickable", has_text="calculate_total").first.click()
    page.wait_for_selector("#graph-canvas canvas")
    page.locator("button:has-text('Source')").first.click()
    page.wait_for_selector("pre")
    shot("3-impact")
    before = page.locator("td:has-text('INV-')").count()  # the invariant-diff panel already lists some
    page.click("button:has-text('Check invariants')")
    page.wait_for_function(f"document.querySelectorAll('td').length && [...document.querySelectorAll('td')]"
                           f".filter(t => t.textContent.startsWith('INV-')).length > {before}")
    print("invariant rows:", page.locator("td:has-text('INV-')").count())
    shot("4-invariants")

    page.goto(args.base + "#/query")
    page.wait_for_selector("textarea")
    pick_repo(page, args.repo)
    examples = page.locator("select[aria-label='Example']")
    for name in [o.inner_text() for o in examples.locator("option").all()]:
        examples.select_option(label=name)
        page.click("button:has-text('Run query')")
        page.wait_for_timeout(600)
        error = page.locator(".error")
        if error.count():
            problems.append(f"query {name!r}: {error.inner_text()[:120]}")
        print(f"query {name[:44]:44} rows={page.locator('section.panel table tbody tr').count()}")
    shot("5-query")

    page.goto(args.base + "#/runs")
    page.wait_for_selector("h1:has-text('Agent runs')")
    shot("6-runs")
    page.goto(args.base + "#/ontology")
    page.wait_for_selector("h1:has-text('Ontology')")
    shot("7-ontology")

    phone = browser.new_context(viewport={"width": 390, "height": 800}, color_scheme="dark").new_page()
    phone.on("pageerror", lambda e: problems.append(f"phone pageerror: {e}"))
    login(phone, args.base, args.key)
    overflow = phone.evaluate("document.documentElement.scrollWidth - innerWidth")
    print("phone overflow px:", overflow)
    if overflow > 0:
        problems.append(f"horizontal overflow {overflow}px at 390px width")
    phone.screenshot(path=f"{args.out}/8-phone-dark.png")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["smoke", "shot"])
    parser.add_argument("route", nargs="?", default="#/")
    parser.add_argument("--base", default="http://localhost:8000/ui/")
    parser.add_argument("--key", default="dev-key")
    parser.add_argument("--repo", default="1", help="Repository id of the indexed shop fixture")
    parser.add_argument("--out", default="shots")
    parser.add_argument("--wait", default="h1", help="Selector to wait for before a 'shot' screenshot")
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1320, "height": 950}).new_page()
        # The page asks /health and the API before a key is entered; those 401s are expected.
        page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}")
                if m.type in ("error", "warning") and "401" not in m.text else None)
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

        def shot(name: str) -> None:
            page.wait_for_timeout(400)
            page.screenshot(path=f"{args.out}/{name}.png", full_page=True)
            print("screenshot:", f"{args.out}/{name}.png")

        if args.command == "smoke":
            smoke(page, browser, args, shot, problems)
        else:
            login(page, args.base, args.key)
            page.goto(args.base + args.route.lstrip("/"))
            page.wait_for_selector(args.wait)
            shot("view")
        browser.close()
    print("problems:", problems or "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
