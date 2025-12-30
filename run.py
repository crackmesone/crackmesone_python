#!/usr/bin/env python3
"""
Main entry point for crackmes.one Flask application.

For production, use gunicorn:
    gunicorn -w 4 -b 127.0.0.1:8001 'app:create_app()'
"""

import os
import sys

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == '__main__':
    config = app.config.get('APP_CONFIG', {})
    server_config = config.get('Server', {})

    host = server_config.get('Host', '127.0.0.1')
    port = server_config.get('Port', 8001)

    print(f"Starting crackmes.one on http://{host}:{port}")
    app.run(host=host, port=port, debug=True)
