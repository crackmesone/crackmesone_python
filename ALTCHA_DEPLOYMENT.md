# ALTCHA v2 deployment and rollback

This change replaces Google reCAPTCHA with ALTCHA v2 self-hosted **verification**.
The Python server uses `altcha==2.3.0`. The browser widget is the official
ALTCHA JavaScript **v3.2.1**, which supports the v2 challenge format.

## Configuration

1. Install requirements in a virtual environment: `python -m pip install -r requirements.txt`.
2. Generate **two independent**, high-entropy local secrets (do not commit them):

   ```bash
   python -c 'import secrets; print(secrets.token_hex(32))'
   python -c 'import secrets; print(secrets.token_hex(32))'
   ```

3. Copy `config/config.json.example` to `config/config.json` and set
   `Altcha.HmacSecret` and `Altcha.HmacKeySecret` to the two different values.
4. Enable `Altcha.Enabled` and set `Altcha.Protect` to the desired forms.
   The example protects `Crackme` and `Writeup`, not `Register` or `Comment`.
5. The MongoDB account must be able to insert into `altcha_used` and create its
   `expires_at` TTL index. This index is provisioned once on application startup
   when ALTCHA is enabled. An indexing failure **prevents startup** rather than
   silently dropping replay protection.
6. For multi-worker production, set `RateLimiter.StorageUri` to a common Redis
   backend (e.g. `redis://127.0.0.1:6379/0`). The example uses `memory://` so
   developers without Redis can still start the project; it is **not suitable**
   for distributed or multi-process rate limiting.
7. Deploy all updated templates, code and dependencies together. Do not enable
   ALTCHA on only some of the Gunicorn workers.

## Browser widget: CDN vs first-party hosting

The sample configuration uses a version-pinned CDN script:

`https://cdn.jsdelivr.net/npm/altcha@3.2.1/dist/main/altcha.min.js`

The CAPTCHA challenges and proof verification are performed locally. The CDN
is a *separate frontend availability dependency*; if your goal is fully
first-party delivery, retrieve and commit the official MIT-licensed browser
asset before rollout:

```bash
python script/vendor_altcha_widget.py
```

The command installs `static/js/altcha-3.2.1.min.js` plus upstream license text,
checks that the downloaded file is JavaScript of the expected approximate size,
and prints its SHA-256. Review the downloaded file and include both files in
this PR. Configure `Altcha.WidgetUrl` as:

`/static/js/altcha-3.2.1.min.js`

**Important:** the complete asset cannot be regenerated from Python package
`altcha`. Do not enable the local URL before the file has been vendored.
For strict supply-chain requirements, independently pin/verify its digest or
npm package integrity before releasing. Ensure your CSP permits the selected
script source and web workers (and verify CSP in a real browser).

## Verification checklist

```bash
python -m pytest -v tests/test_altcha.py
python -m pytest --cov=app --cov=review --cov-branch --cov-report=term-missing --cov-fail-under=75
```

CI (`.github/workflows/tests.yml`) already runs Python 3.12 and the coverage
threshold, plus a separate MongoDB integration job. Follow the current GitHub
Actions run to confirm this revision passes on the repository's CI.

Before production, test browser flows with the *real* widget and real DB:
- POST without ALTCHA and with tampered/expired/cross-scope proof: rejected.
- Correct proof accepted once for both crackme and writeup uploads.
- Retries after a failed upload refresh the challenge and preserve form values.
- Multiple Gunicorn workers cannot consume the same proof twice.
- The challenge endpoint and widget asset respond under deployed HTTP security
  headers, HTTPS, and reverse proxy configuration.

**Rollback:** disable `Altcha.Enabled` only as a deliberate emergency change
(uploads then have no CAPTCHA), or revert the PR and restore the old Google
reCAPTCHA configuration and credentials together. MongoDB collection
`altcha_used` may remain and expire automatically; do not drop it while
mixed versions of the application are running. Use staging first.

## Risk notes

ALTCHA PoW is an abuse deterrent, not a human-identity guarantee. Bots can
compute proof-of-work. Keep upload reviews, size checks, account controls and
shared rate limits. The HMAC keys must remain secret and constant across
workers, and MongoDB writes must be durable and shared.
