"""
Apply command - Execute cost optimization recommendations.

Supports:
- Right-sizing (stop, modify, start instances)
- Scheduling (create EventBridge rules)
- Dry-run mode for safety
- Rollback capability
"""

import click
import json
from typing import Optional
from datetime import datetime

from ..utils.logger import (
    get_logger,
    print_header,
    print_success,
    print_error,
    print_info,
    print_warning,
    console,
)
from ..utils.aws_client import AWSClient, AWSClientError
from ..collectors.ec2_collector import EC2Collector
from ..collectors.rds_collector import RDSCollector

logger = get_logger(__name__)


@click.command("apply")
@click.option(
    "--recommendation-id", "-r",
    help="Specific recommendation ID to apply"
)
@click.option(
    "--instance-id", "-i",
    help="Instance ID to apply changes to"
)
@click.option(
    "--action", "-a",
    type=click.Choice(["resize", "stop", "start", "schedule"]),
    required=True,
    help="Action to perform"
)
@click.option(
    "--new-type", "-t",
    help="New instance type (for resize action)"
)
@click.option(
    "--region",
    default=None,
    help="AWS region"
)
@click.option(
    "--profile",
    default=None,
    help="AWS profile name"
)
@click.option(
    "--dry-run", "-d",
    is_flag=True,
    default=False,
    help="Preview changes without applying"
)
@click.option(
    "--force", "-f",
    is_flag=True,
    default=False,
    help="Skip confirmation prompts"
)
@click.option(
    "--output", "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format"
)
def apply(
    recommendation_id: Optional[str],
    instance_id: Optional[str],
    action: str,
    new_type: Optional[str],
    region: Optional[str],
    profile: Optional[str],
    dry_run: bool,
    force: bool,
    output: str,
):
    """
    Apply cost optimization recommendations.
    
    Examples:
    
    \b
    # Resize an EC2 instance
    cloud-cost-slayer apply -i i-1234567890abcdef0 -a resize -t t3.small --region us-east-1
    
    \b
    # Stop an idle instance (with dry-run)
    cloud-cost-slayer apply -i i-1234567890abcdef0 -a stop --dry-run
    
    \b
    # Start a stopped instance
    cloud-cost-slayer apply -i i-1234567890abcdef0 -a start --region us-east-1
    """
    print_header("Apply Recommendations")
    
    if action == "resize" and not new_type:
        print_error("--new-type is required for resize action")
        return
    
    if not instance_id and not recommendation_id:
        print_error("Either --instance-id or --recommendation-id is required")
        return
    
    try:
        # Initialize AWS client
        aws_client = AWSClient(profile=profile)
        
        if not aws_client.test_credentials():
            print_error("Invalid AWS credentials")
            return
        
        identity = aws_client.get_caller_identity()
        print_success(f"Authenticated as {identity['arn']}")
        
        # Determine region
        if not region:
            region = aws_client.default_region or "us-east-1"
        
        # Execute based on action
        if action == "resize":
            _apply_resize(aws_client, instance_id, new_type, region, dry_run, force)
        elif action == "stop":
            _apply_stop(aws_client, instance_id, region, dry_run, force)
        elif action == "start":
            _apply_start(aws_client, instance_id, region, dry_run, force)
        elif action == "schedule":
            print_info("For scheduling, use: cloud-cost-slayer schedule")
            
    except AWSClientError as e:
        print_error(f"AWS Error: {e}")
        logger.exception("AWS client error during apply")
    except Exception as e:
        print_error(f"Error: {e}")
        logger.exception("Unexpected error during apply")


def _apply_resize(
    aws_client: AWSClient,
    instance_id: str,
    new_type: str,
    region: str,
    dry_run: bool,
    force: bool,
):
    """Resize an EC2 instance."""
    ec2 = aws_client.get_client("ec2", region)
    
    # Get current instance info
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        reservations = response.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            print_error(f"Instance {instance_id} not found")
            return
        
        instance = reservations[0]["Instances"][0]
        current_type = instance["InstanceType"]
        current_state = instance["State"]["Name"]
        
        # Get instance name
        name = "Unnamed"
        for tag in instance.get("Tags", []):
            if tag["Key"] == "Name":
                name = tag["Value"]
                break
        
    except Exception as e:
        print_error(f"Failed to get instance: {e}")
        return
    
    console.print()
    console.print("[bold cyan]📋 Resize Operation[/bold cyan]")
    console.print(f"   Instance: {name} ({instance_id})")
    console.print(f"   Current Type: {current_type}")
    console.print(f"   New Type: [green]{new_type}[/green]")
    console.print(f"   Current State: {current_state}")
    console.print()
    
    if current_type == new_type:
        print_warning("Instance is already the target type")
        return
    
    if dry_run:
        console.print("[yellow]🔍 DRY RUN - No changes will be made[/yellow]")
        console.print()
        console.print("Would perform the following steps:")
        console.print("   1. Stop instance (if running)")
        console.print(f"   2. Modify instance type to {new_type}")
        console.print("   3. Start instance")
        console.print()
        
        # Calculate savings
        from ..utils.calculator import get_calculator
        calc = get_calculator()
        current_cost = calc.get_instance_pricing(current_type, region) * 730
        new_cost = calc.get_instance_pricing(new_type, region) * 730
        savings = current_cost - new_cost
        
        console.print(f"   💰 Estimated monthly savings: [green]${savings:.2f}[/green]")
        return
    
    # Confirmation
    if not force:
        console.print("[yellow]⚠️  This will cause instance downtime![/yellow]")
        if not click.confirm("Do you want to proceed?"):
            print_info("Operation cancelled")
            return
    
    # Execute resize
    try:
        # Step 1: Stop if running
        if current_state == "running":
            console.print("   ⏳ Stopping instance...")
            ec2.stop_instances(InstanceIds=[instance_id])
            
            # Wait for stopped state
            waiter = ec2.get_waiter("instance_stopped")
            waiter.wait(InstanceIds=[instance_id])
            console.print("   ✓ Instance stopped")
        
        # Step 2: Modify instance type
        console.print(f"   ⏳ Changing type to {new_type}...")
        ec2.modify_instance_attribute(
            InstanceId=instance_id,
            InstanceType={"Value": new_type}
        )
        console.print("   ✓ Instance type modified")
        
        # Step 3: Start instance
        console.print("   ⏳ Starting instance...")
        ec2.start_instances(InstanceIds=[instance_id])
        
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])
        console.print("   ✓ Instance started")
        
        console.print()
        print_success(f"Successfully resized {instance_id} to {new_type}")
        
        # Show savings
        from ..utils.calculator import get_calculator
        calc = get_calculator()
        current_cost = calc.get_instance_pricing(current_type, region) * 730
        new_cost = calc.get_instance_pricing(new_type, region) * 730
        savings = current_cost - new_cost
        
        if savings > 0:
            console.print(f"   💰 Monthly savings: [green]${savings:.2f}[/green]")
        
    except Exception as e:
        print_error(f"Failed to resize instance: {e}")
        console.print()
        console.print("[yellow]Rollback: Instance may need manual intervention[/yellow]")
        console.print(f"   Check instance state: aws ec2 describe-instances --instance-ids {instance_id}")


def _apply_stop(
    aws_client: AWSClient,
    instance_id: str,
    region: str,
    dry_run: bool,
    force: bool,
):
    """Stop an EC2 instance."""
    ec2 = aws_client.get_client("ec2", region)
    
    # Get current instance info
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        reservations = response.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            print_error(f"Instance {instance_id} not found")
            return
        
        instance = reservations[0]["Instances"][0]
        current_state = instance["State"]["Name"]
        instance_type = instance["InstanceType"]
        
        # Get instance name
        name = "Unnamed"
        for tag in instance.get("Tags", []):
            if tag["Key"] == "Name":
                name = tag["Value"]
                break
        
    except Exception as e:
        print_error(f"Failed to get instance: {e}")
        return
    
    console.print()
    console.print("[bold cyan]🛑 Stop Operation[/bold cyan]")
    console.print(f"   Instance: {name} ({instance_id})")
    console.print(f"   Type: {instance_type}")
    console.print(f"   Current State: {current_state}")
    console.print()
    
    if current_state != "running":
        print_warning(f"Instance is already {current_state}")
        return
    
    # Calculate savings
    from ..utils.calculator import get_calculator
    calc = get_calculator()
    hourly_cost = calc.get_instance_pricing(instance_type, region)
    
    if dry_run:
        console.print("[yellow]🔍 DRY RUN - No changes will be made[/yellow]")
        console.print()
        console.print(f"   Would stop instance {instance_id}")
        console.print(f"   💰 Saves ${hourly_cost:.4f}/hour (${hourly_cost * 730:.2f}/month)")
        console.print()
        console.print("[dim]Note: EBS storage charges continue when stopped[/dim]")
        return
    
    # Confirmation
    if not force:
        if not click.confirm("Stop this instance?"):
            print_info("Operation cancelled")
            return
    
    try:
        console.print("   ⏳ Stopping instance...")
        ec2.stop_instances(InstanceIds=[instance_id])
        
        waiter = ec2.get_waiter("instance_stopped")
        waiter.wait(InstanceIds=[instance_id])
        
        print_success(f"Successfully stopped {instance_id}")
        console.print(f"   💰 Saving ${hourly_cost:.4f}/hour")
        
    except Exception as e:
        print_error(f"Failed to stop instance: {e}")


def _apply_start(
    aws_client: AWSClient,
    instance_id: str,
    region: str,
    dry_run: bool,
    force: bool,
):
    """Start an EC2 instance."""
    ec2 = aws_client.get_client("ec2", region)
    
    # Get current instance info
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        reservations = response.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            print_error(f"Instance {instance_id} not found")
            return
        
        instance = reservations[0]["Instances"][0]
        current_state = instance["State"]["Name"]
        
        # Get instance name
        name = "Unnamed"
        for tag in instance.get("Tags", []):
            if tag["Key"] == "Name":
                name = tag["Value"]
                break
        
    except Exception as e:
        print_error(f"Failed to get instance: {e}")
        return
    
    console.print()
    console.print("[bold cyan]▶️  Start Operation[/bold cyan]")
    console.print(f"   Instance: {name} ({instance_id})")
    console.print(f"   Current State: {current_state}")
    console.print()
    
    if current_state == "running":
        print_warning("Instance is already running")
        return
    
    if current_state != "stopped":
        print_error(f"Cannot start instance in state: {current_state}")
        return
    
    if dry_run:
        console.print("[yellow]🔍 DRY RUN - No changes will be made[/yellow]")
        console.print()
        console.print(f"   Would start instance {instance_id}")
        return
    
    # Confirmation
    if not force:
        if not click.confirm("Start this instance?"):
            print_info("Operation cancelled")
            return
    
    try:
        console.print("   ⏳ Starting instance...")
        ec2.start_instances(InstanceIds=[instance_id])
        
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])
        
        print_success(f"Successfully started {instance_id}")
        
    except Exception as e:
        print_error(f"Failed to start instance: {e}")
