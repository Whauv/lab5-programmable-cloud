#!/usr/bin/env python3

import sys
import time
import googleapiclient.discovery
from google.oauth2 import service_account

# ============================================================================
# CONFIGURATION
# ============================================================================
SERVICE_ACCOUNT_FILE = '/home/prch5047/lab5_programmable cloud/service-credentials.json'
PROJECT_ID = "lab5cloud-474120"  # Your project ID
ZONE = "us-west1-b"
VM1_NAME = "vm1-launcher"
VM2_NAME = "vm2-flask-app"
MACHINE_TYPE = "f1-micro"
IMAGE_FAMILY = "ubuntu-2204-lts"
IMAGE_PROJECT = "ubuntu-os-cloud"

# Load service account credentials
print("Loading service account credentials...")
try:
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    print(f"Service account credentials loaded successfully")
except FileNotFoundError:
    print(f"Error: Service account file '{SERVICE_ACCOUNT_FILE}' not found!")
    print("Please create a service account and download the JSON key file.")
    sys.exit(1)

print(f"Project ID: {PROJECT_ID}")

# Build compute service
compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

# ============================================================================
# VM-2 STARTUP SCRIPT (Flask installation on final VM)
# ============================================================================
VM2_STARTUP_SCRIPT = """#!/bin/bash
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
"""

# ============================================================================
# VM-1 PYTHON SCRIPT (runs on VM-1 to create VM-2)
# ============================================================================
VM1_LAUNCH_SCRIPT = f"""#!/usr/bin/env python3
import time
import googleapiclient.discovery
from google.oauth2 import service_account

# Get metadata
import requests
metadata_server = "http://metadata.google.internal/computeMetadata/v1"
metadata_flavor = {{'Metadata-Flavor': 'Google'}}

# Get project ID from metadata
project = requests.get(
    f'{{metadata_server}}/project/project-id',
    headers=metadata_flavor
).text

print(f"VM-1: Creating VM-2 in project {{project}}")

# Load service account credentials
credentials = service_account.Credentials.from_service_account_file(
    '/srv/service-credentials.json',
    scopes=['https://www.googleapis.com/auth/cloud-platform']
)

compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

# Read VM-2 startup script
with open('/srv/vm2-startup-script.sh', 'r') as f:
    vm2_startup_script = f.read()

# Read configuration
with open('/srv/config.txt', 'r') as f:
    config = {{}}
    for line in f:
        key, value = line.strip().split('=')
        config[key] = value

zone = config['ZONE']
vm2_name = config['VM2_NAME']
machine_type = config['MACHINE_TYPE']

# Get image
image_response = compute.images().getFromFamily(
    project='{IMAGE_PROJECT}',
    family='{IMAGE_FAMILY}'
).execute()

source_disk_image = image_response['selfLink']
machine_type_url = f"zones/{{zone}}/machineTypes/{{machine_type}}"

# Create VM-2 configuration
vm2_config = {{
    'name': vm2_name,
    'machineType': machine_type_url,
    'disks': [{{
        'boot': True,
        'autoDelete': True,
        'initializeParams': {{
            'sourceImage': source_disk_image,
            'diskSizeGb': 10
        }}
    }}],
    'networkInterfaces': [{{
        'network': f'projects/{{project}}/global/networks/default',
        'accessConfigs': [{{
            'type': 'ONE_TO_ONE_NAT',
            'name': 'External NAT'
        }}]
    }}],
    'metadata': {{
        'items': [{{
            'key': 'startup-script',
            'value': vm2_startup_script
        }}]
    }},
    'tags': {{
        'items': ['allow-5000']
    }}
}}

print(f"VM-1: Launching VM-2 '{{vm2_name}}'...")
operation = compute.instances().insert(
    project=project,
    zone=zone,
    body=vm2_config
).execute()

# Wait for operation
print(f"VM-1: Waiting for VM-2 creation to complete...")
while True:
    result = compute.zoneOperations().get(
        project=project,
        zone=zone,
        operation=operation['name']
    ).execute()
    
    if result['status'] == 'DONE':
        if 'error' in result:
            print(f"VM-1: Error creating VM-2: {{result['error']}}")
        else:
            print(f"VM-1: VM-2 '{{vm2_name}}' created successfully!")
        break
    time.sleep(2)

# Get VM-2 external IP
instance = compute.instances().get(
    project=project,
    zone=zone,
    instance=vm2_name
).execute()

external_ip = None
for interface in instance['networkInterfaces']:
    if 'accessConfigs' in interface:
        for access_config in interface['accessConfigs']:
            if 'natIP' in access_config:
                external_ip = access_config['natIP']
                break

if external_ip:
    print(f"VM-1: VM-2 external IP: {{external_ip}}")
    print(f"VM-1: Flask app will be available at: http://{{external_ip}}:5000")
    print(f"VM-1: Wait 2-3 minutes for Flask installation to complete")

    # Save results to file
    with open('/srv/vm2-results.txt', 'w') as f:
        f.write(f"VM-2 created successfully\\n")
        f.write(f"VM-2 Name: {{vm2_name}}\\n")
        f.write(f"VM-2 External IP: {{external_ip}}\\n")
        f.write(f"Flask URL: http://{{external_ip}}:5000\\n")
        f.write(f"Creation completed at: {{time.strftime('%Y-%m-%d %H:%M:%S')}}\\n")

print("VM-1: Job complete!")
"""

# ============================================================================
# VM-1 STARTUP SCRIPT (sets up VM-1 and runs the launch script)
# ============================================================================
VM1_STARTUP_SCRIPT = """#!/bin/bash
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
"""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def wait_for_operation(compute, project, zone, operation):
    """Wait for a zone operation to complete."""
    print(f"  Waiting for operation to complete...")
    while True:
        result = compute.zoneOperations().get(
            project=project,
            zone=zone,
            operation=operation
        ).execute()

        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            print(f"  Operation completed")
            return result
        time.sleep(1)

def get_image_from_family(compute, image_project, family):
    """Get the latest image from a family."""
    image_response = compute.images().getFromFamily(
        project=image_project,
        family=family
    ).execute()
    return image_response['selfLink']

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main function to create VM-1."""
    print("=" * 70)
    print("  Part 3: VM Creating VM")
    print("=" * 70)
    print(f"\nProject: {PROJECT_ID}")
    print(f"Zone: {ZONE}")
    print(f"VM-1 (Launcher): {VM1_NAME}")
    print(f"VM-2 (Flask App): {VM2_NAME}")
    
    try:
        # Read service credentials file
        print("\nReading service credentials...")
        with open(SERVICE_ACCOUNT_FILE, 'r') as f:
            service_creds_content = f.read()
        print("Service credentials file read successfully")
        
        # Create config file content
        config_content = f"ZONE={ZONE}\nVM2_NAME={VM2_NAME}\nMACHINE_TYPE={MACHINE_TYPE}\n"
        
        # Get image for VM-1
        print("\nFetching Ubuntu image...")
        source_disk_image = get_image_from_family(compute, IMAGE_PROJECT, IMAGE_FAMILY)
        machine_type_url = f"zones/{ZONE}/machineTypes/{MACHINE_TYPE}"
        print("Ubuntu image retrieved")
        
        # Create VM-1 configuration
        print(f"\nCreating VM-1 '{VM1_NAME}'...")
        vm1_config = {
            'name': VM1_NAME,
            'machineType': machine_type_url,
            'disks': [{
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': source_disk_image,
                    'diskSizeGb': 10
                }
            }],
            'networkInterfaces': [{
                'network': f'projects/{PROJECT_ID}/global/networks/default',
                'accessConfigs': [{
                    'type': 'ONE_TO_ONE_NAT',
                    'name': 'External NAT'
                }]
            }],
            'metadata': {
                'items': [
                    {'key': 'startup-script', 'value': VM1_STARTUP_SCRIPT},
                    {'key': 'vm2-startup-script', 'value': VM2_STARTUP_SCRIPT},
                    {'key': 'vm1-launch-script', 'value': VM1_LAUNCH_SCRIPT},
                    {'key': 'service-credentials', 'value': service_creds_content},
                    {'key': 'config', 'value': config_content}
                ]
            }
        }
        
        # Create VM-1
        operation = compute.instances().insert(
            project=PROJECT_ID,
            zone=ZONE,
            body=vm1_config
        ).execute()
        
        wait_for_operation(compute, PROJECT_ID, ZONE, operation['name'])
        print(f"VM-1 '{VM1_NAME}' created successfully!")
        
        # Get VM-1 external IP
        time.sleep(5)
        instance = compute.instances().get(
            project=PROJECT_ID,
            zone=ZONE,
            instance=VM1_NAME
        ).execute()
        
        vm1_ip = None
        for interface in instance['networkInterfaces']:
            if 'accessConfigs' in interface:
                for access_config in interface['accessConfigs']:
                    if 'natIP' in access_config:
                        vm1_ip = access_config['natIP']
        
        print("\n" + "=" * 70)
        print("  SUCCESS! VM-1 Created")
        print("=" * 70)
        print(f"\nVM-1 Name: {VM1_NAME}")
        print(f"VM-1 IP: {vm1_ip}")
        print(f"\nVM-1 is now creating VM-2 '{VM2_NAME}'...")
        print(f"This will take 2-3 minutes.")
        print(f"\nTo monitor progress:")
        print(f"  gcloud compute ssh {VM1_NAME} --zone={ZONE}")
        print(f"  sudo tail -f /var/log/vm1-startup.log")
        print(f"\nTo check VM-2 creation results:")
        print(f"  gcloud compute ssh {VM1_NAME} --zone={ZONE}")
        print(f"  cat /srv/vm2-results.txt")
        print(f"\nTo find VM-2's IP after creation:")
        print(f"  gcloud compute instances list")
        print(f"\nExpected timeline:")
        print(f"  - VM-1 setup: 2-3 minutes")
        print(f"  - VM-2 creation: 1-2 minutes")
        print(f"  - VM-2 Flask app: 2-3 minutes")
        print(f"  - Total: 5-8 minutes")
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
