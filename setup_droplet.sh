#!/bin/bash

# Digital Ocean Droplet Setup Script
# Run this as root

# 1. System Updates
apt-get update && apt-get upgrade -y
apt-get install -y python3-pip python3-venv libxml2-dev libxslt-dev

# 2. Increase Open Files Limit (ulimit)
# This is crucial for high concurrency scraping
echo "* soft nofile 65535" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf
echo "root soft nofile 65535" >> /etc/security/limits.conf
echo "root hard nofile 65535" >> /etc/security/limits.conf
echo "session required pam_limits.so" >> /etc/pam.d/common-session

# Apply immediately for current session
ulimit -n 65535

# 3. Setup Project Environment
# Assuming the repo is cloned to /opt/scraper
PROJECT_DIR="/opt/scraper"
mkdir -p $PROJECT_DIR

# Create virtual environment
python3 -m venv $PROJECT_DIR/venv
source $PROJECT_DIR/venv/bin/activate

# Install dependencies
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "requirements.txt not found!"
fi

# 4. Create Systemd Service
cat <<EOF > /etc/systemd/system/scraper.service
[Unit]
Description=High Performance Web Scraper
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/run.sh
Restart=on-failure
RestartSec=10
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

echo "Setup complete. You can start the scraper with: systemctl start scraper"
echo "Or run manually with: ./run.sh"
