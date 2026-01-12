"""
Rollback Generator.

Generates rollback scripts for safely reverting changes:
- Instance type rollback
- State restoration
- Configuration backup
"""

from datetime import datetime
from typing import Optional
import os
import json

from ..utils.logger import get_logger

logger = get_logger(__name__)


class RollbackGenerator:
    """Generate rollback scripts to revert changes safely."""
    
    def __init__(self, output_dir: str = "./cost-sleuth-output"):
        """
        Initialize generator.
        
        Args:
            output_dir: Directory for generated scripts
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Store original configurations
        self.backup_dir = os.path.join(output_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def backup_instance_config(
        self,
        instance_id: str,
        instance_type: str,
        region: str,
        tags: dict = None,
    ) -> str:
        """
        Save instance configuration for potential rollback.
        
        Args:
            instance_id: EC2 instance ID
            instance_type: Current instance type
            region: AWS region
            tags: Instance tags
        
        Returns:
            Path to backup file
        """
        backup = {
            "instance_id": instance_id,
            "instance_type": instance_type,
            "region": region,
            "tags": tags or {},
            "timestamp": datetime.now().isoformat(),
        }
        
        filename = f"backup_{instance_id}.json"
        filepath = os.path.join(self.backup_dir, filename)
        
        with open(filepath, "w") as f:
            json.dump(backup, f, indent=2)
        
        logger.info(f"Backed up config: {filepath}")
        return filepath
    
    def generate_rollback_script(
        self,
        instance_id: str,
        original_type: str,
        region: str,
    ) -> str:
        """
        Generate bash script to rollback an instance to original type.
        
        Args:
            instance_id: EC2 instance ID
            original_type: Original instance type to restore
            region: AWS region
        
        Returns:
            Path to generated script
        """
        script = f'''#!/bin/bash
# Cloud Cost Slayer - Rollback Script
# Generated: {datetime.now().isoformat()}
# Instance: {instance_id}
# Restore to: {original_type}

set -e

INSTANCE_ID="{instance_id}"
ORIGINAL_TYPE="{original_type}"
REGION="{region}"

echo "⏪ Rolling Back Instance: $INSTANCE_ID"
echo "   Restoring to: $ORIGINAL_TYPE"
echo ""

# Get current state
CURRENT_TYPE=$(aws ec2 describe-instances \\
    --instance-ids $INSTANCE_ID \\
    --region $REGION \\
    --query 'Reservations[0].Instances[0].InstanceType' \\
    --output text)

STATE=$(aws ec2 describe-instances \\
    --instance-ids $INSTANCE_ID \\
    --region $REGION \\
    --query 'Reservations[0].Instances[0].State.Name' \\
    --output text)

echo "Current type: $CURRENT_TYPE"
echo "Current state: $STATE"

if [ "$CURRENT_TYPE" = "$ORIGINAL_TYPE" ]; then
    echo ""
    echo "✓ Instance is already the original type. Nothing to do."
    exit 0
fi

# Confirm rollback
read -p "Proceed with rollback? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

# Stop instance if running
if [ "$STATE" = "running" ]; then
    echo ""
    echo "⏳ Stopping instance..."
    aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $REGION
    
    echo "Waiting for instance to stop..."
    aws ec2 wait instance-stopped --instance-ids $INSTANCE_ID --region $REGION
    echo "✓ Instance stopped"
fi

# Restore instance type
echo ""
echo "⏳ Restoring instance type to $ORIGINAL_TYPE..."
aws ec2 modify-instance-attribute \\
    --instance-id $INSTANCE_ID \\
    --instance-type "${{ORIGINAL_TYPE}}" \\
    --region $REGION

echo "✓ Instance type restored"

# Start instance
echo ""
echo "⏳ Starting instance..."
aws ec2 start-instances --instance-ids $INSTANCE_ID --region $REGION

echo "Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION

echo ""
echo "✅ Successfully rolled back $INSTANCE_ID to $ORIGINAL_TYPE"
'''
        
        filename = f"rollback_{instance_id}.sh"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, "w") as f:
            f.write(script)
        
        os.chmod(filepath, 0o755)
        logger.info(f"Generated rollback script: {filepath}")
        
        return filepath
    
    def generate_batch_rollback_script(
        self,
        instances: list[dict],
        region: str,
    ) -> str:
        """
        Generate batch rollback script for multiple instances.
        
        Args:
            instances: List of {"instance_id": str, "original_type": str}
            region: AWS region
        
        Returns:
            Path to generated script
        """
        script = f'''#!/bin/bash
# Cloud Cost Slayer - Batch Rollback Script
# Generated: {datetime.now().isoformat()}
# Instances: {len(instances)}

set -e

REGION="{region}"
FAILED=0
SUCCESSFUL=0

echo "⏪ Batch Rollback: {len(instances)} instances"
echo ""
echo "⚠️  This will rollback all instances to their original types."
echo ""

read -p "Proceed with batch rollback? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

'''
        
        for i, inst in enumerate(instances, 1):
            script += f'''
# Instance {i}: {inst['instance_id']}
echo "─────────────────────────────────────────"
echo "[{i}/{len(instances)}] Rolling back {inst['instance_id']} to {inst['original_type']}"

if aws ec2 stop-instances --instance-ids {inst['instance_id']} --region $REGION 2>/dev/null; then
    aws ec2 wait instance-stopped --instance-ids {inst['instance_id']} --region $REGION
    aws ec2 modify-instance-attribute --instance-id {inst['instance_id']} --instance-type "{{Value={inst['original_type']}}}" --region $REGION
    aws ec2 start-instances --instance-ids {inst['instance_id']} --region $REGION
    aws ec2 wait instance-running --instance-ids {inst['instance_id']} --region $REGION
    echo "✓ Rolled back"
    ((SUCCESSFUL++))
else
    echo "✗ Failed"
    ((FAILED++))
fi

'''
        
        script += '''
echo ""
echo "═════════════════════════════════════════"
echo "Completed: $SUCCESSFUL rolled back, $FAILED failed"
'''
        
        filename = f"batch_rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sh"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, "w") as f:
            f.write(script)
        
        os.chmod(filepath, 0o755)
        logger.info(f"Generated batch rollback script: {filepath}")
        
        return filepath
    
    def generate_terraform_rollback(
        self,
        instances: list[dict],
    ) -> str:
        """
        Generate Terraform rollback configuration.
        
        Args:
            instances: List of instance configs to restore
        
        Returns:
            Path to generated Terraform file
        """
        tf_content = f'''# Cloud Cost Slayer - Terraform Rollback
# Generated: {datetime.now().isoformat()}
# This configuration restores instances to their original types

terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

'''
        
        for inst in instances:
            tf_content += f'''
# Rollback {inst['instance_id']} to {inst['original_type']}
resource "null_resource" "rollback_{inst['instance_id'].replace('-', '_')}" {{
  provisioner "local-exec" {{
    command = <<-EOT
      aws ec2 stop-instances --instance-ids {inst['instance_id']} --region {inst.get('region', 'us-east-1')}
      aws ec2 wait instance-stopped --instance-ids {inst['instance_id']} --region {inst.get('region', 'us-east-1')}
      aws ec2 modify-instance-attribute --instance-id {inst['instance_id']} --instance-type "{{Value={inst['original_type']}}}" --region {inst.get('region', 'us-east-1')}
      aws ec2 start-instances --instance-ids {inst['instance_id']} --region {inst.get('region', 'us-east-1')}
    EOT
  }}
}}

'''
        
        filepath = os.path.join(self.output_dir, "rollback.tf")
        
        with open(filepath, "w") as f:
            f.write(tf_content)
        
        logger.info(f"Generated Terraform rollback: {filepath}")
        return filepath
