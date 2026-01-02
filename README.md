# Crackmes.one

The source code for [crackmes.one](https://crackmes.one), a platform for sharing and solving reverse engineering challenges. Built with Python and Flask.

## Requirements

- Python 3.8+
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
   - Configure reCAPTCHA if needed (set `Enabled: true`)
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
- **Recaptcha.Enabled**: Enable/disable reCAPTCHA
- **Recaptcha.SiteKey**: Your reCAPTCHA site key
- **Recaptcha.Secret**: Your reCAPTCHA secret key
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

## FAQ

**How do I report a security vulnerability?**

Please see [SECURITY.md](SECURITY.md) for instructions on reporting security issues.

## Previous Codebase

The site was originally written in Go. The old codebase is archived at [crackmesone/crackmes.one](https://github.com/crackmesone/crackmes.one).
