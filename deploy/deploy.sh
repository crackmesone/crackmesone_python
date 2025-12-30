#!/bin/bash
# Deploy script for crackmes.one Python app

set -e

cd /home/crackmesone/crackmesone_python

echo "Pulling latest code..."
git pull

echo "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet
deactivate

echo "Reloading application..."
sudo systemctl reload crackmesone

echo "Deployed successfully!"
