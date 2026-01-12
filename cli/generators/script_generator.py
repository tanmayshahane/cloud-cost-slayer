"""
Script Generator.

Generates executable bash and Python scripts for implementing recommendations:
- Right-sizing scripts
- Stop/start scripts
- Scheduling scripts
"""

from datetime import datetime
from typing import Optional
import os

from ..utils.logger import get_logger

logger = get_logger(__name__)


class ScriptGenerator:
    """Generate implementation scripts for cost optimization."""
    
    def __init__(self, output_dir: str = "./cost-sleuth-output"):
        """
        Initialize generator.
        
        Args:
            output_dir: Directory for generated scripts
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_rightsizing_script(
        self,
        instance_id: str,
        current_type: str,
        new_type: str,
        region: str,
    ) -> str:
        """
        Generate bash script to resize an EC2 instance.
        
        Args:
            instance_id: EC2 instance ID
            current_type: Current instance type
            new_type: Recommended instance type
            region: AWS region
        
        Returns:
            Path to generated script
        """
        script = f'''#!/bin/bash
# Cloud Cost Slayer - Instance Rightsizing Script
# Generated: {datetime.now().isoformat()}
# Instance: {instance_id}
# Change: {current_type} -> {new_type}

set -e

INSTANCE_ID="{instance_id}"
NEW_TYPE="{new_type}"
REGION="{region}"

echo "🔄 Rightsizing Instance: $INSTANCE_ID"
echo "   Current Type: {current_type}"
echo "   New Type: $NEW_TYPE"
echo ""

# Check current state
STATE=$(aws ec2 describe-instances \\
    --instance-ids $INSTANCE_ID \\
    --region $REGION \\
    --query 'Reservations[0].Instances[0].State.Name' \\
    --output text)

echo "Current state: $STATE"

# Stop instance if running
if [ "$STATE" = "running" ]; then
    echo ""
    echo "⏳ Stopping instance..."
    aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $REGION
    
    echo "Waiting for instance to stop..."
    aws ec2 wait instance-stopped --instance-ids $INSTANCE_ID --region $REGION
    echo "✓ Instance stopped"
fi

# Modify instance type
echo ""
echo "⏳ Changing instance type to $NEW_TYPE..."
aws ec2 modify-instance-attribute \\
    --instance-id $INSTANCE_ID \\
    --instance-type "${{NEW_TYPE}}" \\
    --region $REGION

echo "✓ Instance type modified"

# Start instance
echo ""
echo "⏳ Starting instance..."
aws ec2 start-instances --instance-ids $INSTANCE_ID --region $REGION

echo "Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION

echo ""
echo "✅ Successfully resized $INSTANCE_ID to $NEW_TYPE"
echo ""
echo "To rollback, run: ./rollback_{instance_id}.sh"
'''
        
        filename = f"resize_{instance_id}.sh"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, "w") as f:
            f.write(script)
        
        os.chmod(filepath, 0o755)
        logger.info(f"Generated rightsizing script: {filepath}")
        
        return filepath
    
    def generate_stop_start_script(
        self,
        instance_id: str,
        action: str,
        region: str,
    ) -> str:
        """
        Generate script to stop or start an instance.
        
        Args:
            instance_id: EC2 instance ID
            action: "stop" or "start"
            region: AWS region
        
        Returns:
            Path to generated script
        """
        if action == "stop":
            script = f'''#!/bin/bash
# Cloud Cost Slayer - Stop Instance Script
# Generated: {datetime.now().isoformat()}
# Instance: {instance_id}

set -e

INSTANCE_ID="{instance_id}"
REGION="{region}"

echo "🛑 Stopping Instance: $INSTANCE_ID"

aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $REGION

echo "Waiting for instance to stop..."
aws ec2 wait instance-stopped --instance-ids $INSTANCE_ID --region $REGION

echo ""
echo "✅ Instance $INSTANCE_ID stopped"
echo "To start again: aws ec2 start-instances --instance-ids $INSTANCE_ID --region $REGION"
'''
        else:  # start
            script = f'''#!/bin/bash
# Cloud Cost Slayer - Start Instance Script
# Generated: {datetime.now().isoformat()}
# Instance: {instance_id}

set -e

INSTANCE_ID="{instance_id}"
REGION="{region}"

echo "▶️ Starting Instance: $INSTANCE_ID"

aws ec2 start-instances --instance-ids $INSTANCE_ID --region $REGION

echo "Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION

echo ""
echo "✅ Instance $INSTANCE_ID started"
'''
        
        filename = f"{action}_{instance_id}.sh"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, "w") as f:
            f.write(script)
        
        os.chmod(filepath, 0o755)
        logger.info(f"Generated {action} script: {filepath}")
        
        return filepath
    
    def generate_batch_script(
        self,
        recommendations: list[dict],
        region: str,
    ) -> str:
        """
        Generate a batch script for multiple recommendations.
        
        Args:
            recommendations: List of recommendation dicts
            region: AWS region
        
        Returns:
            Path to generated script
        """
        instances = []
        for rec in recommendations:
            instances.append({
                "id": rec.get("instance_id"),
                "current": rec.get("current_type"),
                "new": rec.get("recommended_type"),
            })
        
        script = f'''#!/bin/bash
# Cloud Cost Slayer - Batch Rightsizing Script
# Generated: {datetime.now().isoformat()}
# Instances: {len(instances)}

set -e

REGION="{region}"
FAILED=0
SUCCESSFUL=0

echo "🔄 Batch Rightsizing: {len(instances)} instances"
echo ""

'''
        
        for i, inst in enumerate(instances, 1):
            script += f'''
# Instance {i}: {inst['id']}
echo "─────────────────────────────────────────"
echo "[{i}/{len(instances)}] {inst['id']}: {inst['current']} -> {inst['new']}"

if aws ec2 stop-instances --instance-ids {inst['id']} --region $REGION 2>/dev/null; then
    aws ec2 wait instance-stopped --instance-ids {inst['id']} --region $REGION
    aws ec2 modify-instance-attribute --instance-id {inst['id']} --instance-type "{{Value={inst['new']}}}" --region $REGION
    aws ec2 start-instances --instance-ids {inst['id']} --region $REGION
    aws ec2 wait instance-running --instance-ids {inst['id']} --region $REGION
    echo "✓ Success"
    ((SUCCESSFUL++))
else
    echo "✗ Failed"
    ((FAILED++))
fi

'''
        
        script += '''
echo ""
echo "═════════════════════════════════════════"
echo "Completed: $SUCCESSFUL successful, $FAILED failed"
'''
        
        filename = f"batch_resize_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sh"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, "w") as f:
            f.write(script)
        
        os.chmod(filepath, 0o755)
        logger.info(f"Generated batch script: {filepath}")
        
        return filepath
    
    def generate_python_script(
        self,
        instance_id: str,
        current_type: str,
        new_type: str,
        region: str,
    ) -> str:
        """
        Generate Python script to resize an instance.
        
        Args:
            instance_id: EC2 instance ID
            current_type: Current instance type
            new_type: Recommended instance type
            region: AWS region
        
        Returns:
            Path to generated script
        """
        script = f'''#!/usr/bin/env python3
"""
Cloud Cost Slayer - Instance Rightsizing Script
Generated: {datetime.now().isoformat()}
Instance: {instance_id}
Change: {current_type} -> {new_type}
"""

import boto3
import sys
import time

INSTANCE_ID = "{instance_id}"
NEW_TYPE = "{new_type}"
REGION = "{region}"


def main():
    ec2 = boto3.client("ec2", region_name=REGION)
    
    print(f"🔄 Rightsizing Instance: {{INSTANCE_ID}}")
    print(f"   Current Type: {current_type}")
    print(f"   New Type: {{NEW_TYPE}}")
    print()
    
    # Get current state
    response = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
    state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
    print(f"Current state: {{state}}")
    
    # Stop if running
    if state == "running":
        print()
        print("⏳ Stopping instance...")
        ec2.stop_instances(InstanceIds=[INSTANCE_ID])
        
        waiter = ec2.get_waiter("instance_stopped")
        waiter.wait(InstanceIds=[INSTANCE_ID])
        print("✓ Instance stopped")
    
    # Modify type
    print()
    print(f"⏳ Changing instance type to {{NEW_TYPE}}...")
    ec2.modify_instance_attribute(
        InstanceId=INSTANCE_ID,
        InstanceType={{"Value": NEW_TYPE}}
    )
    print("✓ Instance type modified")
    
    # Start instance
    print()
    print("⏳ Starting instance...")
    ec2.start_instances(InstanceIds=[INSTANCE_ID])
    
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[INSTANCE_ID])
    
    print()
    print(f"✅ Successfully resized {{INSTANCE_ID}} to {{NEW_TYPE}}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {{e}}")
        sys.exit(1)
'''
        
        filename = f"resize_{instance_id}.py"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, "w") as f:
            f.write(script)
        
        os.chmod(filepath, 0o755)
        logger.info(f"Generated Python script: {filepath}")
        
        return filepath
