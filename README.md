# BMW i4 eDrive35 CPO inventory monitor

Polls ~8 BMW dealer sites in the DC/Baltimore/Richmond area every 30 minutes
and texts you when a Certified Pre-Owned i4 eDrive35 lands that matches your
filters. Runs entirely on GitHub Actions — free.

## What it looks for

- 2023+ BMW **i4 eDrive35** (trim string matched case-insensitively)
- **Certified Pre-Owned** (dealer-flagged)
- **≤ $39,000** Internet Price (target ~$37k + buffer; excludes doc fee / tax / tags)
- **≤ 33,000 mi** odometer (target ~30k + buffer)
- **Not white** (any color label not containing "white")
- **Harman/Kardon** sound system present in description/VDP

Matches are ranked by extra package count (`Features` list length + known BMW
package mentions) before sending — so a loaded car notifies first.

## Notification

SMS via Verizon's `vtext.com` email gateway, sent through Gmail SMTP.
Telegram support is stubbed in [notify.py](notify.py) — wire it up later by
filling in `send_telegram` and adding the two secrets below.

## Dealers covered

| Dealer | Platform |
|---|---|
| BMW of Sterling | DealerOn |
| Passport BMW | DealerOn |
| BMW of Fairfax | Dealer.com |
| BMW of Alexandria | Dealer.com |
| Richmond BMW | Dealer.com |
| BMW of Silver Spring | Dealer.com |
| BMW of Towson | Dealer.com |
| BMW of Catonsville | Dealer.com |

**Not covered** (skipped with a warning at runtime):
- BMW of Owings Mills, BMW of Annapolis — DealerInspire behind Cloudflare; bot UA is blocked.
- BMW of Bethesda — site appears defunct (returns near-empty page).
- BMW of Fredericksburg — no working domain found.

To add a dealer, append to [dealers.py](dealers.py).

## One-time setup

### 1. Push this folder to a new GitHub repo

```bash
cd /Users/altafsyed/Documents/BMW_Search
git init -b main
git add .
git commit -m "Initial commit"
# Create the repo on github.com first (any name, can be public or private),
# then:
git remote add origin git@github.com:<your-username>/<repo>.git
git push -u origin main
```

### 2. Create a Gmail app password

The vtext gateway needs Gmail SMTP to deliver. You'll need:

1. Enable 2-Step Verification on your Google account (required).
2. Go to https://myaccount.google.com/apppasswords
3. Create an app password (label it "bmw-monitor"). Copy the 16-char password.

### 3. Add GitHub secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**.
Add:

| Name | Value |
|---|---|
| `GMAIL_USER` | `hialtafs@gmail.com` |
| `GMAIL_APP_PASSWORD` | the 16-char app password from step 2 |
| `SMS_TO` | `REDACTED@vtext.com` |

Optional (only when you wire up Telegram later):
| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `TELEGRAM_CHAT_ID` | your chat ID |

### 4. Seed the state (recommended)

Otherwise the very first run will text you about every currently-listed
matching car. From your local machine:

```bash
pip install -r requirements.txt
GMAIL_USER=... GMAIL_APP_PASSWORD=... python check.py --seed
git add seen_vins.json && git commit -m "Seed VINs" && git push
```

This adds every currently-listed match to the seen list without notifying.
The next scheduled run will only text about *newly arriving* cars.

If you'd rather get pinged about current matches too, skip this step.

### 5. Enable the workflow

GitHub disables scheduled workflows on forks/new repos by default. Go to the
**Actions** tab and enable the "BMW i4 inventory check" workflow. You can also
hit **Run workflow** to trigger an immediate test.

## Local development

```bash
pip install -r requirements.txt

# See current inventory without sending texts
python check.py --dry-run

# Test a single SMS
GMAIL_USER=... GMAIL_APP_PASSWORD=... python -c "
from notify import send_sms
send_sms({'vin':'TEST','dealer':'Test','price':35000,'mileage':25000,'color':'Test','url':'https://example.com','extra_count':0})
"
```

## Maintenance notes

- Scheduled GitHub workflows are auto-disabled after **60 days of repo
  inactivity**. The check.yml workflow commits `seen_vins.json` back to the
  repo on every run with changes, which counts as activity — so this only
  becomes an issue if zero new matches show up for 60+ days. If that happens,
  push any dummy commit to re-enable.
- Polling cadence is `*/30 * * * *` (every 30 min). GitHub may delay scheduled
  runs by 5–15 min under load. Change in [check.yml](.github/workflows/check.yml).
- Dealer sites change their HTML/JSON structure occasionally — if a dealer
  stops returning candidates and you can't see why, fetch
  `https://{host}/...inventory page...` locally and diff against the parsing
  in `fetch_dealeron` / `fetch_dealercom`.
- The 30-min schedule fits comfortably in the GitHub Actions free tier
  (~1500 minutes/month used; the limit on private repos is 2000).

## Caveats

- **Harman/Kardon is the binding filter** — most CPO i4s ship with the
  standard Hi-Fi system. As of this writing, zero cars in the 8 supported
  dealerships match. The pipeline is verified working; you're waiting for
  inventory to turn over.
- **Prices exclude doc fees** ($849–$999) and tax/title. If your $37k cap is
  out-the-door, drop `MAX_PRICE` in [check.py](check.py) to ~33000.
- **vtext.com is officially deprecated** by Verizon. Currently working as of
  your test, but may stop without warning. Telegram stub is in
  [notify.py](notify.py) for when that day comes.
