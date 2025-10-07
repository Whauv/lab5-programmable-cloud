#!/bin/bash
set -e
exec > >(tee -a /var/log/vm1-startup.log)
exec 2>&1

echo "=== VM-1 Startup Started at $(date) ==="

# Create working directory
mkdir -p /srv
cd /srv

# Download files from metadata
echo "Downloading metadata files..."
curl -s http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm2-startup-script -H "Metadata-Flavor: Google" > vm2-startup-script.sh
curl -s http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm1-launch-script -H "Metadata-Flavor: Google" > vm1-launch-script.py
curl -s http://metadata.google.internal/computeMetadata/v1/instance/attributes/service-credentials -H "Metadata-Flavor: Google" > service-credentials.json
curl -s http://metadata.google.internal/computeMetadata/v1/instance/attributes/config -H "Metadata-Flavor: Google" > config.txt

# Verify downloads
echo "Downloaded files:"
ls -la /srv/

# Install required packages
echo "Installing Python packages..."
apt-get update
apt-get install -y python3 python3-pip
pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

# Run the script to create VM-2
echo "Launching VM-2 creation script..."
python3 /srv/vm1-launch-script.py

echo "=== VM-1 Startup Complete at $(date) ==="