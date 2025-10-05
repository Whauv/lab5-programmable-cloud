#!/usr/bin/env python3

import time
import sys
import googleapiclient.discovery
import google.auth

# Get credentials and project
credentials, _ = google.auth.default()
PROJECT_ID = "lab5cloud-474120"  # Your project ID
compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)

# ============================================================================
# CONFIGURATION
# ============================================================================
ZONE = "us-west1-b"
SOURCE_INSTANCE_NAME = "flask-tutorial-vm"  # The instance from Part 1
SNAPSHOT_NAME = f"base-snapshot-{SOURCE_INSTANCE_NAME}"
NEW_INSTANCE_PREFIX = "cloned-instance"
MACHINE_TYPE = "f1-micro"
NUM_CLONES = 3

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

def list_instances(compute, project, zone):
    """List all instances in a zone."""
    result = compute.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else None

def instance_exists(compute, project, zone, instance_name):
    """Check if an instance exists."""
    try:
        compute.instances().get(
            project=project,
            zone=zone,
            instance=instance_name
        ).execute()
        return True
    except:
        return False

def get_boot_disk_name(compute, project, zone, instance_name):
    """Get the boot disk name from an instance."""
    instance = compute.instances().get(
        project=project,
        zone=zone,
        instance=instance_name
    ).execute()
    
    for disk in instance['disks']:
        if disk.get('boot'):
            # Extract disk name from the source URL
            # Format: projects/PROJECT/zones/ZONE/disks/DISK_NAME
            source = disk['source']
            disk_name = source.split('/')[-1]
            return disk_name
    
    raise Exception("No boot disk found")

def snapshot_exists(compute, project, snapshot_name):
    """Check if a snapshot exists."""
    try:
        compute.snapshots().get(
            project=project,
            snapshot=snapshot_name
        ).execute()
        return True
    except:
        return False

# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

def create_snapshot(compute, project, zone, instance_name, snapshot_name):
    """Create a snapshot from the instance's boot disk."""
    print(f"\nStep 1: Creating snapshot '{snapshot_name}'...")
    
    # Check if snapshot already exists
    if snapshot_exists(compute, project, snapshot_name):
        print(f"  Snapshot '{snapshot_name}' already exists, skipping creation")
        return
    
    # Get the boot disk name
    print(f"  Finding boot disk for instance '{instance_name}'...")
    disk_name = get_boot_disk_name(compute, project, zone, instance_name)
    print(f"  Boot disk found: {disk_name}")
    
    # Create snapshot
    snapshot_body = {
        "name": snapshot_name,
        "description": f"Snapshot of {instance_name} boot disk"
    }
    
    print(f"  Creating snapshot from disk '{disk_name}'...")
    operation = compute.disks().createSnapshot(
        project=project,
        zone=zone,
        disk=disk_name,
        body=snapshot_body
    ).execute()
    
    wait_for_operation(compute, project, zone, operation['name'])
    print(f"  Snapshot '{snapshot_name}' created successfully")

def create_instance_from_snapshot(compute, project, zone, instance_name, 
                                  snapshot_name, machine_type):
    """Create an instance from a snapshot."""
    print(f"\nCreating instance '{instance_name}' from snapshot...")
    
    # Get snapshot URL
    snapshot = compute.snapshots().get(
        project=project,
        snapshot=snapshot_name
    ).execute()
    
    snapshot_url = snapshot['selfLink']
    machine_type_url = f"zones/{zone}/machineTypes/{machine_type}"
    
    # Configure instance
    config = {
        'name': instance_name,
        'machineType': machine_type_url,
        
        # Boot disk from snapshot
        'disks': [
            {
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceSnapshot': snapshot_url,
                    'diskSizeGb': 10
                }
            }
        ],
        
        # Network interface with external IP
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
        
        # Apply network tag for firewall
        'tags': {
            'items': ['allow-5000']
        }
    }
    
    # Start timing
    start_time = time.time()
    
    operation = compute.instances().insert(
        project=project,
        zone=zone,
        body=config
    ).execute()
    
    wait_for_operation(compute, project, zone, operation['name'])
    
    # End timing
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    print(f"  Instance created in {elapsed_time:.2f} seconds")
    
    return elapsed_time

def get_external_ip(compute, project, zone, instance_name):
    """Get external IP of an instance."""
    instance = compute.instances().get(
        project=project,
        zone=zone,
        instance=instance_name
    ).execute()
    
    for interface in instance['networkInterfaces']:
        if 'accessConfigs' in interface:
            for access_config in interface['accessConfigs']:
                if 'natIP' in access_config:
                    return access_config['natIP']
    return None

# ============================================================================
# MAIN PROGRAM
# ============================================================================

def main():
    """Main function."""
    print("=" * 70)
    print("  Part 2: Clone a Machine from Snapshot")
    print("=" * 70)
    print(f"\nProject ID: {PROJECT_ID}")
    print(f"Zone: {ZONE}")
    print(f"Source Instance: {SOURCE_INSTANCE_NAME}")
    print(f"Snapshot Name: {SNAPSHOT_NAME}")
    
    try:
        # Step 1: Check if source instance exists
        print(f"\nChecking if source instance '{SOURCE_INSTANCE_NAME}' exists...")
        if not instance_exists(compute, PROJECT_ID, ZONE, SOURCE_INSTANCE_NAME):
            print(f"\nError: Source instance '{SOURCE_INSTANCE_NAME}' does not exist!")
            print("Please run Part 1 first to create the instance, or change SOURCE_INSTANCE_NAME")
            sys.exit(1)
        print(f"  Source instance found")
        
        # Step 2: Create snapshot
        create_snapshot(compute, PROJECT_ID, ZONE, SOURCE_INSTANCE_NAME, SNAPSHOT_NAME)
        
        # Step 3: Create cloned instances and measure timing
        print(f"\nStep 2: Creating {NUM_CLONES} cloned instances...")
        timings = []
        instance_names = []
        
        for i in range(1, NUM_CLONES + 1):
            instance_name = f"{NEW_INSTANCE_PREFIX}-{i}"
            instance_names.append(instance_name)
            
            print(f"\n--- Clone {i}/{NUM_CLONES} ---")
            elapsed = create_instance_from_snapshot(
                compute, PROJECT_ID, ZONE, instance_name,
                SNAPSHOT_NAME, MACHINE_TYPE
            )
            timings.append(elapsed)
        
        # Display results
        print("\n" + "=" * 70)
        print("  SUCCESS! All Instances Created")
        print("=" * 70)
        
        print(f"\nTiming Results:")
        print(f"{'Instance Name':<25} {'Creation Time (seconds)':<25}")
        print("-" * 50)
        for name, timing in zip(instance_names, timings):
            print(f"{name:<25} {timing:<25.2f}")
        
        print(f"\nStatistics:")
        print(f"  Average time: {sum(timings)/len(timings):.2f} seconds")
        print(f"  Min time: {min(timings):.2f} seconds")
        print(f"  Max time: {max(timings):.2f} seconds")
        
        # List all instances with IPs
        print(f"\nInstance URLs:")
        for name in instance_names:
            ip = get_external_ip(compute, PROJECT_ID, ZONE, name)
            if ip:
                print(f"  {name}: http://{ip}:5000")
        
        # Create TIMING.md file
        print(f"\nCreating TIMING.md file...")
        with open('TIMING.md', 'w') as f:
            f.write("# Part 2 - Instance Creation Timing Results\n\n")
            f.write(f"*Project:* {PROJECT_ID}\n")
            f.write(f"*Zone:* {ZONE}\n")
            f.write(f"*Machine Type:* {MACHINE_TYPE}\n")
            f.write(f"*Source Snapshot:* {SNAPSHOT_NAME}\n\n")
            f.write("## Timing Results\n\n")
            f.write("| Instance Name | Creation Time (seconds) |\n")
            f.write("|---------------|------------------------|\n")
            for name, timing in zip(instance_names, timings):
                f.write(f"| {name} | {timing:.2f} |\n")
            f.write("\n## Statistics\n\n")
            f.write(f"- *Average time:* {sum(timings)/len(timings):.2f} seconds\n")
            f.write(f"- *Min time:* {min(timings):.2f} seconds\n")
            f.write(f"- *Max time:* {max(timings):.2f} seconds\n")
            f.write("\n## Notes\n\n")
            f.write("Instances were created from a snapshot containing a fully installed Flask tutorial application.\n")
        
        print("  TIMING.md created")
        
        print("\nYour running instances:")
        instances = list_instances(compute, PROJECT_ID, ZONE)
        if instances:
            for instance in instances:
                print(f"   - {instance['name']}")
        
        print("\n" + "=" * 70)
        print("\nIMPORTANT: Clean up when done!")
        print(f"Delete instances: gcloud compute instances delete {' '.join(instance_names)} --zone={ZONE}")
        print(f"Delete snapshot: gcloud compute snapshots delete {SNAPSHOT_NAME}")
        print(f"Keep source instance: {SOURCE_INSTANCE_NAME} (needed for reference)")
        print("=" * 70)
        
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
