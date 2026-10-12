# Crackmes.one

The source code for [crackmes.one](https://crackmes.one), a platform for sharing and solving reverse engineering challenges. Built with Python and Flask.

## Requirements

- Python 3.9+
- MongoDB 4.0+
- `zip` command (for creating password-protected archives when approving submissions)

## Installation

1. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the application:
   - Edit `config/config.json` with your settings
   - Set up MongoDB connection details
   - Generate two independent local ALTCHA signing secrets before setting `Altcha.Enabled: true` (see `ALTCHA_DEPLOYMENT.md`)
   - For production with multiple Gunicorn workers, configure a shared rate-limit backend such as Redis (the sample `memory://` URI is for development only)
   - Configure Discord webhook for notifications (optional)
   - Set a secure `SecretKey` for sessions

## Running

### Development

```bash
python run.py
```

### Production Deployment

#### First-time setup

1. Clone the repository on your server:
```bash
cd /home/crackmesone
git clone <repo-url> crackmesone_python
cd crackmesone_python
```

2. Run the setup script:
```bash
chmod +x deploy/setup.sh
./deploy/setup.sh
```

3. Configure the application:
```bash
cp config/config.json.example config/config.json
nano config/config.json  # Edit with your settings
```

4. Update nginx to proxy to the Python app:
```nginx
upstream python_backend {
    server 127.0.0.1:8081;
}

location / {
    proxy_pass http://python_backend;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

5. Start the service:
```bash
sudo systemctl start crackmesone
sudo systemctl status crackmesone
```

#### Subsequent deployments

```bash
./deploy/deploy.sh
```

Or manually:
```bash
git pull
source venv/bin/activate
pip install -r requirements.txt --quiet
deactivate
sudo systemctl reload crackmesone
```

#### Useful commands

```bash
# Check status
sudo systemctl status crackmesone

# View logs
sudo journalctl -u crackmesone -f
tail -f /var/log/gunicorn/error.log

# Restart (if reload doesn't work)
sudo systemctl restart crackmesone
```

## Project Structure

```
crackmesone_python/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── controllers/         # Route handlers
│   ├── models/              # Database models
│   └── services/            # Shared services
├── config/
│   └── config.json          # Configuration file
├── deploy/
│   ├── gunicorn.conf.py     # Gunicorn configuration
│   ├── crackmesone.service  # Systemd service file
│   ├── setup.sh             # First-time setup script
│   └── deploy.sh            # Deployment script
├── review/                  # Reviewer tool (moderation interface)
│   ├── routes.py            # Reviewer Flask blueprint
│   ├── users.json           # Reviewer credentials
│   └── templates/           # Reviewer templates
├── script/                  # Utility scripts
│   └── generate_reviewer_password_hash.py  # Password hash generator
├── templates/               # Jinja2 templates
├── static/                  # Static files (CSS, JS, images)
├── tmp/                     # Upload staging area
├── requirements.txt         # Python dependencies
├── run.py                   # Entry point
└── README.md
```

## Features

- User registration and authentication
- Upload crackmes (reverse engineering challenges)
- Upload solutions/writeups
- Comments on crackmes
- Rating system (difficulty and quality)
- Search functionality
- RSS feed
- Notifications
- Content moderation (reviewer tool for approving/rejecting submissions)

## Configuration

Edit `config/config.json`:

- **Database.URL**: MongoDB connection string (default: `mongodb://127.0.0.1:27017`)
- **Database.Name**: Database name (default: `crackmesone`)
- **Server.Host**: Host to bind to (default: `127.0.0.1`)
- **Server.Port**: Port to run on (default: `8081`)
- **Session.SecretKey**: Secret key for session signing (change in production!)
- **Session.CookieName**: Session cookie name
- **Altcha.Enabled**: Master switch for the self-hosted ALTCHA v2 proof-of-work CAPTCHA (default: false).
- **Altcha.HmacSecret / HmacKeySecret**: Two independent, random, server-only secrets (at least 32 characters each). No Google account, API key or network verification required.
- **Altcha.Protect**: Independent switches for `Crackme`, `Writeup`, `Register`, `Comment`. Missing entries default to enabled when the master switch is on.
- **Altcha.Cost / MinCounter / MaxCounter / ExpiresMinutes**: Controls the PBKDF2 work factor and challenge expiry. Keep parameters within the documented limits.
- **RateLimiter.StorageUri**: Use `redis://127.0.0.1:6379/0` (or a shared backend) with multiple Gunicorn workers. `memory://` is for development only.

#### Self-hosted ALTCHA deployment

1. Generate **two different** secrets locally, e.g. run `python -c 'import secrets; print(secrets.token_hex(32))'` twice. Never commit the secrets. Store them in the private `config/config.json` (or inject them securely during deployment).
2. Replace the sample blank `Altcha.HmacSecret` and `Altcha.HmacKeySecret`, set `Altcha.Enabled` to `true`, and configure `Altcha.Protect`. The example protects crackme and writeup submissions, not comments or registration.
3. Ensure the `altcha==2.3.0` Python dependency is installed (`pip install -r requirements.txt` in a virtualenv). Frontend templates use ALTCHA widget v3.2.1 from a **version-pinned jsDelivr static CDN**. The actual single-file module is under `dist/main/altcha.min.js`, **not** `dist/altcha.min.js`. This has no verification API/key, but loading that script does require internet access from visitors. For a strictly self-hosted/no-third-party-request deployment, download that *exact* widget release into `static/vendor/altcha.min.js` and set `Altcha.WidgetUrl` to `/static/vendor/altcha.min.js`. Confirm the upstream license when vendoring.
4. MongoDB is mandatory for replay protection: each accepted challenge signature is inserted into the `altcha_used` collection using a unique `_id`. A TTL index removes the consumed entries after they expire. A database failure rejects submissions rather than allowing replay. This works across multiple Gunicorn workers.
5. Use **HTTPS** (or `localhost` during local testing) for the browser's WebCrypto. Test challenge generation (`GET /altcha/challenge/Crackme`), normal upload, missing token, replayed token, expired token and your existing rate limits. Rate-limit storage remains independent of the CAPTCHA replay registry.
6. Execute `python -m pytest -q` using the project environment before opening a PR. Tests use real locally solved ALTCHA challenges and simulated MongoDB, without external CAPTCHA services. A final manual browser smoke test is still essential.

The widget adds a base64 `altcha` field to each protected form. The server verifies its signature, expiry, per-form secret, and solution; then **atomically consumes it** in MongoDB. JavaScript form handlers reset the widget after failed AJAX submissions so the user can retry without losing the file selection or writeup text. ALTCHA's proof of work raises the cost of automated abuse, but does not replace CSRF protection, moderation or rate limiting.

- **Discord.Enabled**: Enable/disable Discord notifications for new submissions
- **Discord.WebhookURL**: Your Discord webhook URL (get from Discord channel settings → Integrations → Webhooks)
- **Reviewer.Enabled**: Enable/disable the reviewer tool (for moderating submissions)
- **Reviewer.PasswordSalt**: Salt used for hashing reviewer passwords (change in production!)

### Reviewer Tool

The reviewer tool is a separate authentication system for site moderators to approve/reject crackme and solution submissions. It is accessed at `/review`.

#### Enabling the Reviewer Tool

1. Set `Reviewer.Enabled` to `true` in `config/config.json`
2. Set a secure random string for `Reviewer.PasswordSalt`

#### Reviewer Credentials (`review/users.json`)

Reviewer accounts are stored in `review/users.json` with the following format:

```json
{
  "username": {
    "password_hash": "sha256-hash-of-password-plus-salt",
    "is_admin": false
  }
}
```

- **password_hash**: SHA256 hash of the password concatenated with the `PasswordSalt` from config
- **is_admin**: If `true`, the user has admin privileges (can delete approved content, manage reviewers, delete users)

#### Creating Reviewer Accounts

Use the password hash generator script to create password hashes:

```bash
python script/generate_reviewer_password_hash.py <password>
```

Then add the username and hash to `review/users.json`:

```json
{
  "newreviewer": {
    "password_hash": "<output-from-script>",
    "is_admin": false
  }
}
```

Alternatively, an existing admin can add new reviewers through the web interface at `/review/managereviewers`.

#### Reviewer vs Admin Permissions

| Action | Reviewer | Admin |
|--------|----------|-------|
| Approve/reject pending crackmes | Yes | Yes |
| Approve/reject pending solutions | Yes | Yes |
| Delete approved crackmes | No | Yes |
| Delete approved solutions | No | Yes |
| Delete comments | No | Yes |
| Delete user accounts | No | Yes |
| Reset user passwords | No | Yes |
| Manage reviewer accounts | No | Yes |

## Contributing

Interested in contributing? Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. **Note:** You must contact the maintainer before starting any work.

## FAQ

**How do I report a security vulnerability?**

Please see [SECURITY.md](SECURITY.md) for instructions on reporting security issues.

## Previous Codebase

The site was originally written in Go. The old codebase is archived at [crackmesone/crackmes.one](https://github.com/crackmesone/crackmes.one).

## ALTCHA rollout

See [`ALTCHA_DEPLOYMENT.md`](ALTCHA_DEPLOYMENT.md) for secure configuration, offline asset hosting, rollout and rollback.
