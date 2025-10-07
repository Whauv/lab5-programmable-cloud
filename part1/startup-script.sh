#!/bin/bash
set -e
exec > >(tee -a /var/log/startup-script.log)
exec 2>&1

echo "=== Flask Tutorial Installation Started at $(date) ==="

# Create working directory
mkdir -p /opt/flask-app
cd /opt/flask-app

# Update and install dependencies
echo "Installing dependencies..."
apt-get update
apt-get install -y python3 python3-pip git

# Clone Flask tutorial
echo "Cloning Flask tutorial repository..."
git clone https://github.com/cu-csci-4253-datacenter/flask-tutorial
cd flask-tutorial

# Install Flask tutorial
echo "Installing Flask application..."
python3 setup.py install
pip3 install -e .

# Setup and run Flask
export FLASK_APP=flaskr
echo "Initializing database..."
flask init-db

echo "Starting Flask application..."
nohup flask run -h 0.0.0.0 > /var/log/flask.log 2>&1 &

echo "=== Flask Tutorial Installation Complete at $(date) ==="
echo "Flask is running on port 5000"


