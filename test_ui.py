"""
Playwright UI test — GnuKontrolR control panel.
Visits every menu item, captures errors, writes findings to bad.md.

Run:  python3 test_ui.py
"""

import asyncio
import re
import json
import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext

BASE_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "admin123"

# Pages to visit (route, display name, expected selector hints)
PAGES = [
    ("/",               "Dashboard"),
    ("/domains",        "Domains"),
    ("/docker",         "Docker / Containers"),
    ("/services",       "Services"),
    ("/marketplace",    "Marketplace"),
    ("/dns",            "DNS"),
    ("/files",          "Files"),
    ("/databases",      "Databases"),
    ("/email",          "Email"),
    ("/ssl",            "SSL"),
    ("/security",       "Security"),
    ("/logs",           "Logs"),
    ("/backups",        "Backups"),
    ("/terminal",       "Terminal"),
    ("/settings",       "Settings"),
    ("/activity-log",   "Activity Log"),
    ("/users",          "Users"),
    ("/ai-admin",       "AI Admin"),
    ("/admin-content",  "Admin Content"),
    ("/diagnostic",     "Diagnostic"),
]

issues = []
screenshots_dir = Path("/tmp/gnukontrolr_screenshots")
screenshots_dir.mkdir(exist_ok=True)


def log_issue(page_name: str, category: str, detail: str, screenshot: str = ""):
    entry = {
        "page": page_name,
        "category": category,
        "detail": detail,
        "screenshot": screenshot,
    }
    issues.append(entry)
    print(f"  [ISSUE] [{category}] {detail}")


async def login(page: Page):
    await page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    # Wait for React SPA to hydrate
    await page.wait_for_selector("input", timeout=15000)
    inputs = await page.query_selector_all("input")
    if len(inputs) < 2:
        raise Exception(f"Login page has only {len(inputs)} inputs — React may not have loaded")
    await inputs[0].fill(USERNAME)
    await inputs[1].fill(PASSWORD)
    await page.click('button[type="submit"]')
    # Wait for redirect away from /login
    await page.wait_for_function("window.location.pathname !== '/login'", timeout=10000)
    print(f"[OK] Logged in — now at {page.url}")


async def test_page(page: Page, route: str, name: str, api_errors: list):
    print(f"\n--- Testing: {name} ({route}) ---")
    js_errors = []
    console_errors = []
    failed_requests = []

    try:
        response = await page.goto(f"{BASE_URL}{route}", wait_until="load", timeout=20000)
    except Exception as e:
        log_issue(name, "NAVIGATION_ERROR", str(e))
        return

    # Set up listeners AFTER navigation starts (avoids capturing aborts from prev page)
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: js_errors.append(str(err)))
    page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url} — {req.failure}"))

    # Wait for React to render dynamic content
    await asyncio.sleep(5)

    # Check HTTP status
    if response and response.status >= 400:
        log_issue(name, "HTTP_ERROR", f"Page returned HTTP {response.status}")

    # Screenshot
    ss_path = screenshots_dir / f"{name.replace('/', '_').replace(' ', '_')}.png"
    await page.screenshot(path=str(ss_path), full_page=True)

    # Check for JS crashes
    for err in js_errors:
        log_issue(name, "JS_ERROR", err, str(ss_path))

    # Check for console errors
    for err in console_errors:
        # Filter noise
        if any(x in err for x in ["favicon", "ResizeObserver", "Warning:"]):
            continue
        log_issue(name, "CONSOLE_ERROR", err[:300], str(ss_path))

    # Check for failed network requests
    for req in failed_requests:
        if "favicon" in req or "hot-update" in req:
            continue
        log_issue(name, "NETWORK_FAILURE", req, str(ss_path))

    # Check visible text for error indicators (body text only, not JS source)
    body_text = await page.evaluate("document.body.innerText")
    error_patterns = [
        r"Internal Server Error",
        r"Traceback \(most recent call last\)",
        r"SyntaxError:",
        r"TypeError:",
        r"ReferenceError:",
        r"Cannot read propert",
        r"Unhandled Rejection",
        r"Failed to fetch",
        r"Something went wrong",
        r"Unexpected token",
    ]
    for pattern in error_patterns:
        if re.search(pattern, body_text, re.IGNORECASE):
            log_issue(name, "PAGE_ERROR_TEXT", f"Found '{pattern}' in visible page text", str(ss_path))

    # Check for blank/empty page (only a spinner or nothing)
    if len(body_text.strip()) < 50:
        log_issue(name, "BLANK_PAGE", f"Page body has very little text ({len(body_text.strip())} chars)", str(ss_path))

    # Check for API errors in page content
    for err in api_errors:
        if route in err.get("url", "") or name.lower() in err.get("url", "").lower():
            log_issue(name, "API_ERROR", f"API {err['method']} {err['url']} → {err['status']}: {err['body'][:200]}", str(ss_path))

    print(f"  [OK] {name} loaded (js_errors={len(js_errors)}, console_errors={len(console_errors)}, failed_reqs={len(failed_requests)})")
    return ss_path


async def intercept_api_errors(page: Page) -> list:
    """Return list of API errors observed during navigation."""
    api_errors = []

    async def on_response(response):
        if "/api/" in response.url and response.status >= 400:
            try:
                body = await response.text()
            except Exception:
                body = "(unreadable)"
            api_errors.append({
                "url": response.url,
                "method": response.request.method,
                "status": response.status,
                "body": body[:500],
            })

    page.on("response", on_response)
    return api_errors


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # Capture all API errors globally
        all_api_errors = []

        async def on_response(response):
            if "/api/" in response.url and response.status >= 400:
                try:
                    body = await response.text()
                except Exception:
                    body = "(unreadable)"
                all_api_errors.append({
                    "url": response.url,
                    "method": response.request.method,
                    "status": response.status,
                    "body": body[:500],
                })

        page.on("response", on_response)

        # Login
        try:
            await login(page)
        except Exception as e:
            print(f"[FATAL] Login failed: {e}")
            await browser.close()
            return

        # Test each page
        for route, name in PAGES:
            try:
                await test_page(page, route, name, all_api_errors)
            except Exception as e:
                log_issue(name, "TEST_EXCEPTION", str(e))

        await browser.close()

    # Deduplicate issues
    seen = set()
    unique_issues = []
    for issue in issues:
        key = (issue["page"], issue["category"], issue["detail"][:80])
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)

    # Write results
    print(f"\n{'='*60}")
    print(f"Total unique issues found: {len(unique_issues)}")
    print(f"API errors observed: {len(all_api_errors)}")
    print(f"Screenshots at: {screenshots_dir}")

    # Append to bad.md
    bad_md = Path("/home/gitmaster/GnuKontrolR/bad.md")
    existing = bad_md.read_text() if bad_md.exists() else ""

    new_section = f"\n\n## Playwright UI Test Results — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

    if not unique_issues and not all_api_errors:
        new_section += "No issues found by Playwright test.\n"
    else:
        # Group by page
        by_page = {}
        for issue in unique_issues:
            by_page.setdefault(issue["page"], []).append(issue)

        for page_name, page_issues in by_page.items():
            new_section += f"### {page_name}\n\n"
            for issue in page_issues:
                new_section += f"- **{issue['category']}** — {issue['detail']}\n"
                if issue.get("screenshot"):
                    new_section += f"  - Screenshot: `{issue['screenshot']}`\n"
            new_section += "\n"

        if all_api_errors:
            new_section += "### API Errors (all pages)\n\n"
            seen_api = set()
            for err in all_api_errors:
                key = f"{err['method']} {err['url']} {err['status']}"
                if key not in seen_api:
                    seen_api.add(key)
                    new_section += f"- **{err['status']}** `{err['method']} {err['url']}`\n"
                    if err["body"]:
                        new_section += f"  - Response: `{err['body'][:150]}`\n"
            new_section += "\n"

    bad_md.write_text(existing + new_section)
    print(f"\nResults appended to bad.md")

    # Also dump raw JSON for analysis
    results_json = Path("/tmp/playwright_results.json")
    results_json.write_text(json.dumps({
        "issues": unique_issues,
        "api_errors": all_api_errors,
    }, indent=2))
    print(f"Raw results: {results_json}")

    return unique_issues, all_api_errors


if __name__ == "__main__":
    asyncio.run(main())
