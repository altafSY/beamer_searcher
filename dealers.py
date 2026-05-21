"""Target dealerships.

Each entry: name (display), host (no scheme), and an optional 'platform' pin.
If platform is omitted, the scraper auto-detects ("dealeron" or "dealercom").

Skipped for now:
- DealerInspire-hosted dealers (Owings Mills, Annapolis) — Cloudflare blocks bot UAs.
  Adding these requires either a residential proxy or a browser automation step.
- BMW of Bethesda — site returns a near-empty page; appears defunct or rebranded.
- BMW of Fredericksburg — could not locate a working domain.
"""

DEALERS = [
    {"name": "BMW of Sterling",      "host": "www.bmwofsterling.com",    "platform": "dealeron"},
    {"name": "Passport BMW",         "host": "www.passportbmw.com",      "platform": "dealeron"},
    {"name": "BMW of Fairfax",       "host": "www.bmwoffairfax.com",     "platform": "dealercom"},
    {"name": "BMW of Alexandria",    "host": "www.bmwofalexandria.com",  "platform": "dealercom"},
    {"name": "Crown Richmond BMW",   "host": "www.richmond-bmw.com",     "platform": "dealercom"},
    {"name": "Richmond BMW Midlothian", "host": "www.richmondbmwmidlothian.com", "platform": "dealercom"},
    {"name": "BMW of Silver Spring", "host": "www.bmwofsilverspring.com","platform": "dealercom"},
    {"name": "BMW of Towson",        "host": "www.bmwtowson.com",        "platform": "dealercom"},
    {"name": "BMW of Catonsville",   "host": "www.bmwofcatonsville.com", "platform": "dealercom"},

    # Disabled — Cloudflare-protected (DealerInspire). Re-enable if you add a
    # workaround (e.g. browser-based scrape).
    # {"name": "BMW of Owings Mills", "host": "www.bmwofowingsmills.com", "platform": "dealerinspire"},
    # {"name": "BMW of Annapolis",    "host": "www.bmwofannapolis.com",   "platform": "dealerinspire"},
]
