#!/bin/bash
# First-time setup script for crackmes.one Python app

set -e

echo "=== crackmes.one Python Setup ==="

# Create log directory
echo "Creating log directory..."
sudo mkdir -p /var/log/gunicorn
sudo chown crackmesone:crackmesone /var/log/gunicorn

# Create venv and install dependencies
echo "Setting up virtual environment..."
cd /home/crackmesone/crackmesone_python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
deactivate

# Copy gunicorn config
echo "Copying gunicorn config..."
cp deploy/gunicorn.conf.py .

# Install systemd service
echo "Installing systemd service..."
sudo cp deploy/crackmesone.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable crackmesone

# Make deploy script executable
chmod +x deploy/deploy.sh

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Copy config/config.json.example to config/config.json and edit it"
echo "  2. Update nginx to proxy to 127.0.0.1:8081"
echo "  3. Start the service: sudo systemctl start crackmesone"
echo "  4. Check status: sudo systemctl status crackmesone"
echo ""
