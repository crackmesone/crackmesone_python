# Crackmes.one

The source code for [crackmes.one](https://crackmes.one), a platform for sharing and solving reverse engineering challenges. Built with Python and Flask.

## Requirements

- Python 3.8+
- MongoDB 4.0+

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

## Previous Codebase

The site was originally written in Go. The old codebase is archived at [crackmesone/crackmes.one](https://github.com/crackmesone/crackmes.one).
