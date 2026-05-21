# BMW i4 CPO inventory monitor

Polls BMW dealer inventory APIs on a schedule and sends an SMS when a Certified Pre-Owned BMW i4 matches a configured filter. Runs on GitHub Actions.

## Dealers

| Dealer | Platform |
|---|---|
| BMW of Sterling | DealerOn |
| Passport BMW | DealerOn |
| BMW of Fairfax | Dealer.com |
| BMW of Alexandria | Dealer.com |
| Crown Richmond BMW | Dealer.com |
| Richmond BMW Midlothian | Dealer.com |
| BMW of Silver Spring | Dealer.com |
| BMW of Towson | Dealer.com |
| BMW of Catonsville | Dealer.com |

Edit [dealers.py](dealers.py) to add or remove.

## Setup

Set these as GitHub Actions secrets:

- `GMAIL_USER` — Gmail address used for SMTP
- `GMAIL_APP_PASSWORD` — Gmail [app password](https://myaccount.google.com/apppasswords) (16 chars, requires 2-Step Verification)
- `SMS_TO` — destination email-to-SMS gateway address

Filter constants and the run schedule live at the top of [check.py](check.py) and in [.github/workflows/check.yml](.github/workflows/check.yml).

## Local

```bash
pip install -r requirements.txt
python check.py --dry-run
```
