#!/usr/bin/env python3

import time
import sys
import googleapiclient.discovery
import google.auth

# Configuration of the project

# Get credentials and set project ID
credentials, _ = google.auth.default()
PROJECT_ID = "lab5cloud-474120"  # Inserting the project id
compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials) # Computing the required credentials

ZONE = "us-west1-b" # defining the zone 
INSTANCE_NAME = "flask-tutorial-vm" #Defining instance name
MACHINE_TYPE = "f1-micro"  # Free tier - change to "e2-medium" for faster testing
IMAGE_FAMILY = "ubuntu-2204-lts" # Defining the image family
IMAGE_PROJECT = "ubuntu-os-cloud" 
NETWORK_TAG = "allow-5000" # defining firewall 
FIREWALL_RULE_NAME = "allow-5000"

# Setting upo the startup script 

STARTUP_SCRIPT = """#!/bin/bash
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
"""

#  Defining the helper functions

# Defining the wait function to process the operation in the loop
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

#  Defining loop to execute the golbal operation
def wait_for_global_operation(compute, project, operation):
    """Wait for a global operation to complete."""
    print(f"  Waiting for operation to complete...")
    while True:
        result = compute.globalOperations().get(
            project=project,
            operation=operation
        ).execute()

        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            print(f"  Operation completed")
            return result
        time.sleep(1)

# Defining loop for executing to check whether a firewall rule is defined or not
def firewall_rule_exists(compute, project, rule_name):
    """Check if a firewall rule exists."""
    try:
        compute.firewalls().get(project=project, firewall=rule_name).execute()
        return True
    except:
        return False

# Defining list of instances which are deployed
def list_instances(compute, project, zone):
    """List all instances in a zone."""
    result = compute.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else None

# MAIN FUNCTIONS

# Creating a firewall rule if it does not exist
def create_firewall_rule(compute, project, rule_name, network_tag):
    """Create firewall rule to allow TCP port 5000."""
    print(f"\nStep 1: Creating firewall rule '{rule_name}'...")
    
    if firewall_rule_exists(compute, project, rule_name):
        print(f"  Firewall rule already exists, skipping")
        return
    
    firewall_body = {
        "name": rule_name,
        "direction": "INGRESS",
        "priority": 1000,
        "network": f"projects/{project}/global/networks/default",
        "sourceRanges": ["0.0.0.0/0"],
        "targetTags": [network_tag],
        "allowed": [
            {
                "IPProtocol": "tcp",
                "ports": ["5000"]
            }
        ]
    }
    
    operation = compute.firewalls().insert(
        project=project,
        body=firewall_body
    ).execute()
    
    wait_for_global_operation(compute, project, operation['name'])
    print(f"  Firewall rule created")

# Getting image from mthe family 
def get_image_from_family(compute, image_project, family):
    """Get the latest image from a family."""
    image_response = compute.images().getFromFamily(
        project=image_project,
        family=family
    ).execute()
    return image_response['selfLink']

# Creating VM instances
def create_instance(compute, project, zone, instance_name, machine_type, 
                   image_project, image_family, startup_script):
    """Create VM instance."""
    print(f"\nStep 2: Creating VM instance '{instance_name}'...")
    
    # Get latest image
    print(f"  Fetching Ubuntu 22.04 LTS image...")
    source_disk_image = get_image_from_family(compute, image_project, image_family)
    print(f"  Image retrieved")
    
    # Configuring instance
    machine_type_url = f"zones/{zone}/machineTypes/{machine_type}"
    
    config = {
        'name': instance_name,
        'machineType': machine_type_url,
        
        # Booting disk
        'disks': [
            {
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': source_disk_image,
                    'diskSizeGb': 10
                }
            }
        ],
        
        # Setting up Network interface with external IP
        'networkInterfaces': [
            {
                'network': f'projects/{project}/global/networks/default',
                'accessConfigs': [
                    {
                        'type': 'ONE_TO_ONE_NAT',
                        'name': 'External NAT'
                    }
                ]
            }
        ],
        
        # Startup script
        'metadata': {
            'items': [
                {
                    'key': 'startup-script',
                    'value': startup_script
                }
            ]
        }
    }
    
    operation = compute.instances().insert(
        project=project,
        zone=zone,
        body=config
    ).execute()
    
    wait_for_operation(compute, project, zone, operation['name'])
    print(f"  Instance created")

# Applying a network tag to the instance
def apply_network_tag(compute, project, zone, instance_name, network_tag):
    """Apply network tag to instance."""
    print(f"\nStep 3: Applying network tag '{network_tag}'...")
    
    # Get instance to retrieve fingerprint
    instance = compute.instances().get(
        project=project,
        zone=zone,
        instance=instance_name
    ).execute()
    
    # Set tags
    tags_body = {
        'items': [network_tag],
        'fingerprint': instance['tags']['fingerprint']
    }
    
    operation = compute.instances().setTags(
        project=project,
        zone=zone,
        instance=instance_name,
        body=tags_body
    ).execute()
    
    wait_for_operation(compute, project, zone, operation['name'])
    print(f"  Network tag applied")

# getting external ip for the isntance
def get_external_ip(compute, project, zone, instance_name):
    """Get external IP of instance."""
    print(f"\nStep 4: Retrieving external IP address...")
    
    instance = compute.instances().get(
        project=project,
        zone=zone,
        instance=instance_name
    ).execute()
    
    for interface in instance['networkInterfaces']:
        if 'accessConfigs' in interface:
            for access_config in interface['accessConfigs']:
                if 'natIP' in access_config:
                    external_ip = access_config['natIP']
                    print(f"  External IP: {external_ip}")
                    return external_ip
    return None

# Defining the main program

def main():
    """Main function."""
    print("=" * 70)
    print("  GCP VM Creator with Flask Tutorial Installation")
    print("=" * 70)
    print(f"\nProject ID: {PROJECT_ID}")
    print(f"Zone: {ZONE}")
    print(f"Instance: {INSTANCE_NAME}")
    print(f"Machine Type: {MACHINE_TYPE}")
    
    try:
        # Creating firewall rule
        create_firewall_rule(compute, PROJECT_ID, FIREWALL_RULE_NAME, NETWORK_TAG)
        
        # Creating VM instance
        create_instance(
            compute, PROJECT_ID, ZONE, INSTANCE_NAME, MACHINE_TYPE,
            IMAGE_PROJECT, IMAGE_FAMILY, STARTUP_SCRIPT
        )
        
        # Applying network tag
        apply_network_tag(compute, PROJECT_ID, ZONE, INSTANCE_NAME, NETWORK_TAG)
        
        # Get the external IP
        external_ip = get_external_ip(compute, PROJECT_ID, ZONE, INSTANCE_NAME)
        
        # Success message if the VM gets created
        print("\n" + "=" * 70)
        print("  SUCCESS! VM Created")
        print("=" * 70)
        
        if external_ip:
            print(f"\nInstance Details:")
            print(f"   Name: {INSTANCE_NAME}")
            print(f"   Zone: {ZONE}")
            print(f"   External IP: {external_ip}")
            print(f"\nFlask Application URL:")
            print(f"   http://{external_ip}:5000")
            print(f"\nWait 2-3 minutes for installation to complete")
            print(f"\nTo debug:")
            print(f"   gcloud compute ssh {INSTANCE_NAME} --zone={ZONE}")
            print(f"   sudo tail -f /var/log/startup-script.log")
            
            # Saving the configuration for other parts
            with open("part1_config.txt", "w") as f:
                f.write(f"PROJECT_ID={PROJECT_ID}\n")
                f.write(f"ZONE={ZONE}\n")
                f.write(f"INSTANCE_NAME={INSTANCE_NAME}\n")
                f.write(f"EXTERNAL_IP={external_ip}\n")
            
            print(f"\nYour running instances:")
            instances = list_instances(compute, PROJECT_ID, ZONE)
            if instances:
                for instance in instances:
                    print(f"   - {instance['name']}")
        else:
            print(f"\nCould not retrieve external IP")
        
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
