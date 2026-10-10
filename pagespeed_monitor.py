import os
import re
import time
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ---------- CONFIG ----------
REPORT_TIMEOUT_MS = 180_000      # max wait for a PageSpeed report
RENDER_BUFFER_MS = 15_000        # extra wait so all metric values render
PAGE_LOAD_TIMEOUT_MS = 120_000
MAX_ATTEMPTS = 2                 # retries per URL

# ---------- URL LIST ----------
urls = [
    # Quick Heal India
    {"url": "https://www.quickheal.co.in/", "env": "Live"},
    {"url": "https://www.quickheal.co.in/home-users", "env": "Live"},
    {"url": "https://www.quickheal.co.in/home-users/quick-heal-total-security/", "env": "Live"},
    {"url": "https://www.quickheal.co.in/home-users/quick-heal-internet-security", "env": "Live"},
    {"url": "https://www.quickheal.co.in/home-users/quick-heal-antivirus-pro", "env": "Live"},
    {"url": "https://www.quickheal.co.in/download-free-antivirus", "env": "Live"},
    {"url": "https://www.quickheal.co.in/installer", "env": "Live"},
    {"url": "https://www.quickheal.co.in/quick-heal-product-renew", "env": "Live"},
    {"url": "https://www.quickheal.co.in/multirenew", "env": "Live"},

    # Quick Heal Global
    {"url": "https://www.quickheal.com/", "env": "Live"},
    {"url": "https://www.quickheal.com/blogs/", "env": "Live"},
    {"url": "https://www.quickheal.com/quick-heal-product-renew/", "env": "Live"},

    # Quick Heal US
    {"url": "https://us.quickheal.com/", "env": "Live"},
    {"url": "https://us.quickheal.com/quick-heal-product-renew/", "env": "Live"},

    # Knowledge Centre
    {"url": "https://www.quickheal.co.in/knowledge-centre/", "env": "Live"},

    # Seqrite
    {"url": "https://www.seqrite.com/", "env": "Live"},
    {"url": "https://www.seqrite.com/contact-sales-person/", "env": "Live"},
    {"url": "https://www.seqrite.com/endpoint-protection-cloud/", "env": "Live"},

    # Guardian
    {"url": "https://www.guardianav.co.in/", "env": "Live"},
    {"url": "https://www.guardianav.co.in/renew", "env": "Live"},

    # Foundation
    {"url": "https://www.quickhealfoundation.org/", "env": "Live"},

    # Academy
    {"url": "https://www.quickhealacademy.com/", "env": "Live"},
]

# ---------- VARIABLES ----------
results = []
current_date = datetime.now().strftime("%Y-%m-%d")
screenshots_folder = f"screenshots/screenshots_{current_date}"
reports_folder = "reports"
os.makedirs(screenshots_folder, exist_ok=True)
os.makedirs(reports_folder, exist_ok=True)

COLUMNS = [
    "Date", "Environment", "URL", "Device",
    "Performance", "Accessibility", "Best Practices", "SEO",
    "FCP", "LCP", "Speed Index", "TBT", "CLS",
]

METRICS_JS = """
() => {
    const data = {
        "Performance":"N/A","Accessibility":"N/A","Best Practices":"N/A","SEO":"N/A",
        "FCP":"N/A","LCP":"N/A","Speed Index":"N/A","TBT":"N/A","CLS":"N/A"
    };
    document.querySelectorAll('.lh-gauge__wrapper').forEach(g => {
        const label = g.querySelector('.lh-gauge__label')?.innerText;
        const score = g.querySelector('.lh-gauge__percentage')?.innerText;
        if (label && score && Object.prototype.hasOwnProperty.call(data, label)) data[label] = score;
    });
    document.querySelectorAll('.lh-metric').forEach(m => {
        const title = m.querySelector('.lh-metric__title')?.innerText || "";
        const value = m.querySelector('.lh-metric__value')?.innerText || "";
        if (title.includes("First Contentful Paint")) data["FCP"] = value;
        if (title.includes("Largest Contentful Paint")) data["LCP"] = value;
        if (title.includes("Speed Index")) data["Speed Index"] = value;
        if (title.includes("Total Blocking Time")) data["TBT"] = value;
        if (title.includes("Cumulative Layout Shift")) data["CLS"] = value;
    });
    return data;
}
"""


# ---------- SAVE REPORT ----------
def save_report():
    if not results:
        return
    df = pd.DataFrame(results).reindex(columns=COLUMNS)
    report_file = f"{reports_folder}/pagespeed_report_{current_date}.xlsx"
    df.to_excel(report_file, index=False)
    print(f"Report saved: {report_file}")


# ---------- SCREENSHOT ----------
def capture_fullpage(page, path):
    try:
        print("  Preparing full page screenshot...")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(2000)
        page.screenshot(path=path, full_page=True)
        print(f"  Screenshot saved: {path}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")


# ---------- DISMISS COOKIE BANNER ----------
def dismiss_cookie_banner(page):
    for pattern in (r"got it", r"accept", r"agree"):
        try:
            btn = page.get_by_role("button", name=re.compile(pattern, re.I)).first
            btn.click(timeout=4000)
            print("  Cookie banner dismissed.")
            page.wait_for_timeout(1000)
            return
        except Exception:
            continue


# ---------- WAIT FOR REPORT ----------
def wait_for_report_ready(page, expected_url_fragment):
    """
    PageSpeed changes the URL when switching Mobile <-> Desktop,
    so first confirm the URL, then wait for loading to finish and
    for the result elements to exist.
    """
    print(f"  Waiting for URL to contain: '{expected_url_fragment}'")
    page.wait_for_url(lambda u: expected_url_fragment in u, timeout=REPORT_TIMEOUT_MS)
    print(f"  URL confirmed: {page.url}")

    # Loading indicator may not exist if loading is already done
    try:
        page.wait_for_selector(".lh-header--loading", state="detached", timeout=REPORT_TIMEOUT_MS)
    except PlaywrightTimeout:
        pass

    page.wait_for_selector(".lh-gauge__percentage", state="attached", timeout=REPORT_TIMEOUT_MS)
    page.wait_for_selector(".lh-metrics-container", state="attached", timeout=REPORT_TIMEOUT_MS)
    print("  Report DOM is ready.")

    page.wait_for_timeout(RENDER_BUFFER_MS)


# ---------- EXPAND AUDITS ----------
def expand_audit_sections(page):
    keywords = ("show audits", "show details", "passed audits", "expand view")
    try:
        buttons = page.locator("button").all()
        for btn in buttons:
            try:
                txt = (btn.inner_text(timeout=500) or "").strip().lower()
                if any(k in txt for k in keywords):
                    btn.evaluate("el => el.click()")
                    page.wait_for_timeout(500)
            except Exception:
                continue
    except Exception:
        pass


# ---------- RUN ONE DEVICE ----------
def run_device(page, url, environment, device, encoded_url, filename):
    psi_url = f"https://pagespeed.web.dev/report?url={encoded_url}&form_factor={device}"
    print(f"  Loading {device.capitalize()} PSI URL: {psi_url}")
    page.goto(psi_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)

    wait_for_report_ready(page, f"form_factor={device}")
    dismiss_cookie_banner(page)
    expand_audit_sections(page)
    capture_fullpage(page, f"{screenshots_folder}/{filename}_{device}.png")

    metrics = page.evaluate(METRICS_JS)
    row = {
        "Date": current_date,
        "Environment": environment,
        "URL": url,
        "Device": device.capitalize(),
        **metrics,
    }
    results.append(row)
    print(f"  {device.capitalize()} Performance: {row['Performance']} | FCP: {row['FCP']} | LCP: {row['LCP']}")


# ---------- ANALYZE ----------
def analyze_url(browser, url, environment):
    print(f"\nAnalyzing: {url}")
    encoded_url = quote(url, safe="")
    filename = re.sub(r"[^a-zA-Z0-9_-]", "_", url)

    for device in ("mobile", "desktop"):
        # Fresh context per run = clean cookies/storage (replaces manual clearing)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.set_default_timeout(REPORT_TIMEOUT_MS)
        try:
            run_device(page, url, environment, device, encoded_url, filename)
        except Exception:
            try:
                page.screenshot(path=f"{screenshots_folder}/debug_{filename}_{device}.png")
            except Exception:
                pass
            raise
        finally:
            context.close()


def error_row(url, environment):
    return {
        "Date": current_date,
        "Environment": environment,
        "URL": url,
        "Device": "Error",
        **{c: "FAILED" for c in COLUMNS[4:]},
    }


# ---------- MAIN ----------
def main():
    start_time = time.time()
    total_sites = len(urls)
    print(f"Total Sites: {total_sites}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            for index, item in enumerate(urls, start=1):
                print(f"\nProcessing {index}/{total_sites}")
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    before = len(results)
                    try:
                        analyze_url(browser, item["url"], item["env"])
                        break
                    except Exception as e:
                        del results[before:]  # drop partial rows from the failed attempt
                        print(f"Attempt {attempt}/{MAX_ATTEMPTS} failed for {item['url']}: {e!r}")
                        if attempt == MAX_ATTEMPTS:
                            results.append(error_row(item["url"], item["env"]))
                save_report()
        finally:
            save_report()
            browser.close()

    elapsed = round((time.time() - start_time) / 60, 2)
    print("\nCompleted Successfully")
    print(f"Total Records: {len(results)}")
    print(f"Execution Time: {elapsed} minutes")


if __name__ == "__main__":
    main()
