#!/usr/bin/env python3
"""
Main entry point for crackmes.one Flask application.
"""

import os
import sys

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Get configuration
    config = app.config.get('APP_CONFIG', {})
    server_config = config.get('Server', {})

    host = server_config.get('Hostname', '0.0.0.0')
    port = server_config.get('HTTPPort', 5000)
    use_https = server_config.get('UseHTTPS', False)

    print(f"Starting crackmes.one on http://{host}:{port}")

    if use_https:
        cert_file = server_config.get('CertFile', '')
        key_file = server_config.get('KeyFile', '')
        if cert_file and key_file:
            app.run(host=host, port=port, ssl_context=(cert_file, key_file), debug=True)
        else:
            print("Warning: HTTPS enabled but cert/key files not specified")
            app.run(host=host, port=port, debug=True)
    else:
        app.run(host=host, port=port, debug=True)
