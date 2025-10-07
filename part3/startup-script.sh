#!/bin/bash
set -e
exec > >(tee -a /var/log/vm2-startup.log)
exec 2>&1

echo "=== VM-2 Flask Installation Started at $(date) ==="

# Create working directory
mkdir -p /opt/flask-app
cd /opt/flask-app

# Update and install dependencies
apt-get update
apt-get install -y python3 python3-pip git

# Clone Flask tutorial
git clone https://github.com/cu-csci-4253-datacenter/flask-tutorial
cd flask-tutorial

# Install Flask tutorial
python3 setup.py install
pip3 install -e .

# Setup and run Flask
export FLASK_APP=flaskr
flask init-db

# Start Flask application
nohup flask run -h 0.0.0.0 > /var/log/flask.log 2>&1 &

echo "=== VM-2 Flask Installation Complete at $(date) ==="
