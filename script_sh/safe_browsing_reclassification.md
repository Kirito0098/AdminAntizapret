# Safe Browsing Reclassification Checklist

This checklist helps remove the Chrome red interstitial after fixes are deployed.

## 1) Confirm technical status before request

Run:

`python3 script_sh/safe_browsing_status_cli.py admin.vpn.claymore-it.ru --json`

Record these fields in the incident note:

- `site`
- `status_code`
- `threat_flag`
- `checked_at_utc`

If `threat_flag=true`, continue with remediation/review request.

## 2) Submit review / reclassification

Use Google Search Console Security Issues review flow for the affected property:

- [https://search.google.com/search-console/security-issues](https://search.google.com/search-console/security-issues)

Include in the review text:

- exact host (`admin.vpn.claymore-it.ru`)
- what changed (header hardening, `noindex` on admin/mini-app paths, public-surface audit)
- evidence that there is no malware/phishing payload in served pages
- timestamp of latest Safe Browsing check

## 3) Monitor until warning disappears

Poll every 30-60 minutes:

`python3 script_sh/safe_browsing_status_cli.py admin.vpn.claymore-it.ru`

Exit code semantics:

- `0`: no threat flag in current API record
- `2`: threat flag still present
- `1`: query/parsing error

## 4) Post-review validation

When `threat_flag=false`:

1. Open `/login` and `/tg-mini/open` in Chrome Incognito.
2. Confirm no red warning page appears.
3. Save one screenshot per endpoint for closure.
