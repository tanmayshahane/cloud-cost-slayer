"""
Config command - Manage Cloud Cost Slayer configuration.

Handles credential testing, default settings, and profile management.
"""

import click
import os
from pathlib import Path

from ..utils.logger import (
    get_logger,
    print_header,
    print_success,
    print_error,
    print_info,
    console,
)
from ..utils.aws_client import AWSClient

logger = get_logger(__name__)


@click.group("config")
@click.pass_context
def config(ctx):
    """
    Manage Cloud Cost Slayer configuration.
    
    Commands for testing credentials, managing profiles,
    and configuring default settings.
    """
    pass


@config.command("test")
@click.pass_context
def test_credentials(ctx):
    """
    Test AWS credentials and permissions.
    
    Verifies that the configured AWS credentials are valid
    and have the necessary permissions for cost analysis.
    
    Example:
    
      cloud-cost-slayer config test
    """
    print_header("AWS Credential Test", "Verifying AWS credentials and permissions")
    
    profile = ctx.obj.get("profile")
    
    # Test basic credentials
    print_info("Testing AWS credentials...")
    
    client = AWSClient(profile=profile)
    success, message = client.test_credentials()
    
    if success:
        print_success(message)
    else:
        print_error(message)
        raise click.Abort()
    
    # Test EC2 permissions
    print_info("Testing EC2 permissions...")
    try:
        ec2 = client.get_ec2_client()
        ec2.describe_instances(MaxResults=5)
        print_success("✓ EC2: DescribeInstances")
    except Exception as e:
        print_error(f"✗ EC2: DescribeInstances - {e}")
    
    # Test CloudWatch permissions
    print_info("Testing CloudWatch permissions...")
    try:
        cw = client.get_cloudwatch_client()
        cw.list_metrics(Namespace="AWS/EC2", MaxRecords=5)
        print_success("✓ CloudWatch: ListMetrics")
    except Exception as e:
        print_error(f"✗ CloudWatch: ListMetrics - {e}")
    
    # Test Pricing permissions
    print_info("Testing Pricing API permissions...")
    try:
        pricing = client.get_pricing_client()
        pricing.describe_services(ServiceCode="AmazonEC2", MaxResults=1)
        print_success("✓ Pricing: DescribeServices")
    except Exception as e:
        print_error(f"✗ Pricing: DescribeServices - {e}")
    
    # Test regions
    print_info("Testing region access...")
    try:
        regions = client.get_all_regions()
        print_success(f"✓ Found {len(regions)} accessible regions")
    except Exception as e:
        print_error(f"✗ Failed to list regions - {e}")
    
    console.print()
    print_success("Credential test complete!")


@config.command("show")
@click.pass_context
def show_config(ctx):
    """
    Show current configuration.
    
    Displays the current AWS profile, region, and other settings.
    
    Example:
    
      cloud-cost-slayer config show
    """
    print_header("Current Configuration", "Cloud Cost Slayer settings")
    
    profile = ctx.obj.get("profile") or os.environ.get("AWS_PROFILE", "default")
    region = os.environ.get("AWS_REGION", "us-east-1")
    
    from rich.table import Table
    
    table = Table(title="Configuration", border_style="blue")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    
    table.add_row("AWS Profile", profile)
    table.add_row("AWS Region", region)
    table.add_row("AWS_ACCESS_KEY_ID", "****" if os.environ.get("AWS_ACCESS_KEY_ID") else "(not set)")
    table.add_row("AWS_SECRET_ACCESS_KEY", "****" if os.environ.get("AWS_SECRET_ACCESS_KEY") else "(not set)")
    table.add_row("Config Directory", str(Path.home() / ".cloud-cost-slayer"))
    
    console.print(table)


@config.command("init")
@click.option(
    "--profile", "-p",
    help="AWS profile to use as default."
)
@click.option(
    "--region", "-r",
    help="AWS region to use as default."
)
@click.pass_context
def init_config(ctx, profile: str, region: str):
    """
    Initialize configuration file.
    
    Creates a configuration file with default settings.
    
    Example:
    
      cloud-cost-slayer config init --profile production --region us-east-1
    """
    config_dir = Path.home() / ".cloud-cost-slayer"
    config_file = config_dir / "config.yaml"
    
    print_header("Initialize Configuration", "Setting up Cloud Cost Slayer")
    
    # Create config directory
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Create config file
    import yaml
    
    config_data = {
        "aws": {
            "profile": profile or "default",
            "region": region or "us-east-1",
        },
        "analysis": {
            "default_days": 30,
            "exclude_production": True,
            "min_savings_threshold": 5.0,
        },
        "output": {
            "default_format": "table",
            "output_directory": "./cost-sleuth-output",
        },
    }
    
    with open(config_file, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)
    
    print_success(f"Configuration saved to {config_file}")
    
    # Show the config
    console.print()
    console.print("[dim]Configuration contents:[/dim]")
    console.print(yaml.dump(config_data, default_flow_style=False))
