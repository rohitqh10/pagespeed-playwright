# Quick Heal PageSpeed Monitor

Automatically checks PageSpeed Insights scores for Quick Heal websites using **Playwright**.

## Features

- Mobile and Desktop scores (Performance, Accessibility, Best Practices, SEO, FCP, LCP, Speed Index, TBT, CLS)
- Full-page screenshots
- Excel report
- Runs automatically using GitHub Actions (15th and 30th of each month, or manually)

## Run locally

```bash
pip install -r requirements.txt
playwright install chromium
python pagespeed_monitor.py
```

Output goes to `reports/` (Excel) and `screenshots/` (PNG).

## Repo structure

```
.
├── .github/workflows/pagespeed.yml
├── pagespeed_monitor.py
├── requirements.txt
└── README.md
```
