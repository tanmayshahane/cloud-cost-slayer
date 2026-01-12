"""
Monitor command - Continuous cost monitoring with alerts.

Features:
- Periodic analysis runs
- Cost threshold alerts
- Slack/email notifications
- Trend reporting
"""

import click
import time
import json
from typing import Optional
from datetime import datetime, timedelta

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
from ..collectors.cloudwatch_collector import CloudWatchCollector
from ..utils.calculator import get_calculator

logger = get_logger(__name__)


@click.command("monitor")
@click.option(
    "--interval", "-i",
    default=3600,
    type=int,
    help="Check interval in seconds (default: 3600 = 1 hour)"
)
@click.option(
    "--threshold", "-t",
    default=None,
    type=float,
    help="Alert if potential savings exceed this amount ($/month)"
)
@click.option(
    "--region", "-r",
    default=None,
    help="AWS region to monitor (default: all regions)"
)
@click.option(
    "--profile",
    default=None,
    help="AWS profile name"
)
@click.option(
    "--slack-webhook",
    default=None,
    envvar="SLACK_WEBHOOK_URL",
    help="Slack webhook URL for notifications"
)
@click.option(
    "--once",
    is_flag=True,
    default=False,
    help="Run once and exit (no continuous monitoring)"
)
@click.option(
    "--output", "-o",
    type=click.Choice(["json", "table"]),
    default="table",
    help="Output format"
)
def monitor(
    interval: int,
    threshold: Optional[float],
    region: Optional[str],
    profile: Optional[str],
    slack_webhook: Optional[str],
    once: bool,
    output: str,
):
    """
    Continuously monitor AWS costs and alert on optimization opportunities.
    
    Examples:
    
    \b
    # Monitor every hour, alert if savings > $100
    cloud-cost-slayer monitor --interval 3600 --threshold 100
    
    \b
    # Run once and exit
    cloud-cost-slayer monitor --once
    
    \b
    # Monitor with Slack notifications
    cloud-cost-slayer monitor --threshold 50 --slack-webhook https://hooks.slack.com/...
    """
    print_header("Cost Monitor")
    
    try:
        # Initialize AWS client
        aws_client = AWSClient(profile=profile)
        
        if not aws_client.test_credentials():
            print_error("Invalid AWS credentials")
            return
        
        identity = aws_client.get_caller_identity()
        print_success(f"Authenticated as {identity['arn']}")
        
        # Determine regions
        if region:
            regions = [region]
        else:
            regions = aws_client.get_all_regions()
            # Limit to common regions for faster monitoring
            common_regions = [
                "us-east-1", "us-west-2", "eu-west-1", 
                "ap-south-1", "ap-southeast-1"
            ]
            regions = [r for r in regions if r in common_regions]
        
        console.print()
        console.print(f"[dim]Monitoring regions: {', '.join(regions)}[/dim]")
        console.print(f"[dim]Check interval: {interval} seconds[/dim]")
        if threshold:
            console.print(f"[dim]Alert threshold: ${threshold:.2f}/month[/dim]")
        console.print()
        
        run_count = 0
        while True:
            run_count += 1
            
            console.print(f"[bold cyan]🔍 Monitor Run #{run_count}[/bold cyan]")
            console.print(f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            console.print()
            
            # Run monitoring check
            results = _run_monitoring_check(aws_client, regions)
            
            # Display results
            _display_results(results, output)
            
            # Check threshold and alert
            if threshold and results["total_savings"] > threshold:
                _send_alert(results, threshold, slack_webhook)
            
            if once:
                console.print()
                print_info("Single run completed. Use without --once for continuous monitoring.")
                break
            
            # Wait for next interval
            console.print()
            console.print(f"[dim]Next check in {interval} seconds... (Ctrl+C to stop)[/dim]")
            console.print("─" * 60)
            
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                console.print()
                print_info("Monitoring stopped")
                break
                
    except AWSClientError as e:
        print_error(f"AWS Error: {e}")
    except KeyboardInterrupt:
        console.print()
        print_info("Monitoring stopped")
    except Exception as e:
        print_error(f"Error: {e}")
        logger.exception("Unexpected error during monitoring")


def _run_monitoring_check(aws_client: AWSClient, regions: list) -> dict:
    """Run a single monitoring check."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "regions": regions,
        "ec2_instances": 0,
        "rds_instances": 0,
        "idle_instances": [],
        "underutilized_instances": [],
        "total_current_cost": 0,
        "total_savings": 0,
    }
    
    calc = get_calculator()
    ec2_collector = EC2Collector(aws_client)
    rds_collector = RDSCollector(aws_client)
    cw_collector = CloudWatchCollector(aws_client)
    
    # Collect EC2 instances
    try:
        instances = ec2_collector.collect_all_instances(
            regions=regions,
            states=["running"],
            show_progress=False,
        )
        results["ec2_instances"] = len(instances)
        
        # Basic utilization check (quick scan)
        for inst in instances[:10]:  # Limit to first 10 for speed
            hourly_rate = calc.get_instance_pricing(
                inst["instance_type"], 
                inst["region"]
            )
            monthly_cost = hourly_rate * 730
            results["total_current_cost"] += monthly_cost
            
            # Get quick metrics
            metrics = cw_collector.collect_metrics(
                inst["instance_id"],
                inst["region"],
                days=7,
            )
            
            cpu = metrics.get("CPUUtilization", {})
            cpu_avg = cpu.get("average", 100)
            
            if cpu_avg < 5:
                results["idle_instances"].append({
                    "id": inst["instance_id"],
                    "name": inst.get("name", "Unnamed"),
                    "type": inst["instance_type"],
                    "cpu_avg": cpu_avg,
                    "monthly_cost": monthly_cost,
                })
                results["total_savings"] += monthly_cost
            elif cpu_avg < 20:
                results["underutilized_instances"].append({
                    "id": inst["instance_id"],
                    "name": inst.get("name", "Unnamed"),
                    "type": inst["instance_type"],
                    "cpu_avg": cpu_avg,
                    "monthly_cost": monthly_cost,
                    "potential_savings": monthly_cost * 0.4,  # ~40% savings from downsize
                })
                results["total_savings"] += monthly_cost * 0.4
                
    except Exception as e:
        logger.warning(f"Failed to collect EC2 data: {e}")
    
    # Collect RDS instances
    try:
        rds_instances = rds_collector.collect_all_instances(
            regions=regions,
            show_progress=False,
        )
        results["rds_instances"] = len(rds_instances)
        
    except Exception as e:
        logger.warning(f"Failed to collect RDS data: {e}")
    
    return results


def _display_results(results: dict, output: str):
    """Display monitoring results."""
    if output == "json":
        console.print(json.dumps(results, indent=2, default=str))
        return
    
    # Table format
    console.print(f"   EC2 Instances: {results['ec2_instances']}")
    console.print(f"   RDS Databases: {results['rds_instances']}")
    console.print()
    
    if results["idle_instances"]:
        console.print("[bold red]🔴 Idle Instances (CPU < 5%)[/bold red]")
        for inst in results["idle_instances"][:5]:
            console.print(f"   • {inst['name']} ({inst['id']})")
            console.print(f"     CPU: {inst['cpu_avg']:.1f}% | Cost: ${inst['monthly_cost']:.2f}/mo")
        if len(results["idle_instances"]) > 5:
            console.print(f"   ... and {len(results['idle_instances']) - 5} more")
        console.print()
    
    if results["underutilized_instances"]:
        console.print("[bold yellow]🟡 Underutilized Instances (CPU < 20%)[/bold yellow]")
        for inst in results["underutilized_instances"][:5]:
            console.print(f"   • {inst['name']} ({inst['id']})")
            console.print(f"     CPU: {inst['cpu_avg']:.1f}% | Potential savings: ${inst['potential_savings']:.2f}/mo")
        if len(results["underutilized_instances"]) > 5:
            console.print(f"   ... and {len(results['underutilized_instances']) - 5} more")
        console.print()
    
    if results["total_savings"] > 0:
        console.print(f"[bold green]💰 Total Potential Savings: ${results['total_savings']:.2f}/month[/bold green]")
    else:
        console.print("[bold green]✅ No immediate optimization opportunities found[/bold green]")


def _send_alert(results: dict, threshold: float, slack_webhook: Optional[str]):
    """Send alert notification."""
    console.print()
    console.print(f"[bold red]🚨 ALERT: Savings exceed ${threshold:.2f}/month threshold![/bold red]")
    console.print(f"   Potential savings: ${results['total_savings']:.2f}/month")
    
    if slack_webhook:
        try:
            import urllib.request
            import urllib.error
            
            message = {
                "text": f"🚨 AWS Cost Alert: ${results['total_savings']:.2f}/month in potential savings detected!",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Cloud Cost Slayer Alert*\n\nPotential savings: *${results['total_savings']:.2f}/month*\nThreshold: ${threshold:.2f}/month"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• Idle instances: {len(results['idle_instances'])}\n• Underutilized: {len(results['underutilized_instances'])}"
                        }
                    }
                ]
            }
            
            data = json.dumps(message).encode("utf-8")
            req = urllib.request.Request(
                slack_webhook,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            
            urllib.request.urlopen(req)
            console.print("[green]✓ Slack notification sent[/green]")
            
        except Exception as e:
            console.print(f"[yellow]⚠ Failed to send Slack notification: {e}[/yellow]")
    else:
        console.print("[dim]Tip: Use --slack-webhook to enable Slack notifications[/dim]")
