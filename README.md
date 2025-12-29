# Crackmes.one - Python/Flask Port

A Python Flask port of the crackmes.one platform for sharing and solving reverse engineering challenges.

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
   - Set a secure `SecretKey` for sessions

4. Create upload directories:
```bash
mkdir -p tmp/crackme tmp/solution static/crackme static/solution
```

5. Copy static assets from the original project:
```bash
cp -r /path/to/crackmes.one/static/* static/
```

## Running

Development:
```bash
python run.py
```

Production (with gunicorn):
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 'app:create_app()'
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

- **Database.MongoDB.URL**: MongoDB connection string
- **Database.MongoDB.Database**: Database name
- **Recaptcha.Enabled**: Enable/disable reCAPTCHA
- **Recaptcha.SiteKey**: Your reCAPTCHA site key
- **Recaptcha.Secret**: Your reCAPTCHA secret key
- **Session.SecretKey**: Secret key for session encryption (change in production!)
- **Server.HTTPPort**: Port to run on

## Migration from Go

This is a direct port of the Go codebase with equivalent functionality:
- MongoDB operations use pymongo
- Templates converted from Go templates to Jinja2
- bcrypt password hashing preserved (compatible with existing data)
- Same database schema (works with existing MongoDB data)
