"""
Schedule command - Configure automatic start/stop schedules for EC2 instances.

Uses EventBridge Scheduler to stop instances during idle hours
and start them before business hours.
"""

import click
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
from ..utils.validators import parse_regions
from ..collectors.ec2_collector import EC2Collector
from ..collectors.cloudwatch_collector import CloudWatchCollector
from ..analyzers.pattern_detector import PatternDetector

logger = get_logger(__name__)

# AWS region to timezone offset mapping (hours from UTC)
REGION_TIMEZONE_OFFSETS = {
    # Asia Pacific
    "ap-south-1": 5.5,       # Mumbai (IST)
    "ap-southeast-1": 8,     # Singapore (SGT)
    "ap-southeast-2": 10,    # Sydney (AEST, without DST)
    "ap-northeast-1": 9,     # Tokyo (JST)
    "ap-northeast-2": 9,     # Seoul (KST)
    "ap-northeast-3": 9,     # Osaka (JST)
    "ap-east-1": 8,          # Hong Kong (HKT)
    # US
    "us-east-1": -5,         # N. Virginia (EST)
    "us-east-2": -5,         # Ohio (EST)
    "us-west-1": -8,         # N. California (PST)
    "us-west-2": -8,         # Oregon (PST)
    # Europe
    "eu-west-1": 0,          # Ireland (GMT/UTC)
    "eu-west-2": 0,          # London (GMT)
    "eu-west-3": 1,          # Paris (CET)
    "eu-central-1": 1,       # Frankfurt (CET)
    "eu-north-1": 1,         # Stockholm (CET)
    # Others
    "sa-east-1": -3,         # São Paulo (BRT)
    "ca-central-1": -5,      # Canada (EST)
    "me-south-1": 3,         # Bahrain (AST)
    "af-south-1": 2,         # Cape Town (SAST)
}

def _get_timezone_offset(region: str) -> float:
    """Get timezone offset in hours for a region."""
    return REGION_TIMEZONE_OFFSETS.get(region, 0)

def _utc_to_local(utc_hour: int, utc_min: int, offset_hours: float) -> tuple:
    """Convert UTC time to local time."""
    total_minutes = utc_hour * 60 + utc_min + int(offset_hours * 60)
    if total_minutes < 0:
        total_minutes += 24 * 60
    elif total_minutes >= 24 * 60:
        total_minutes -= 24 * 60
    return total_minutes // 60, total_minutes % 60

def _local_to_utc(local_hour: int, local_min: int, offset_hours: float) -> tuple:
    """Convert local time to UTC time."""
    total_minutes = local_hour * 60 + local_min - int(offset_hours * 60)
    if total_minutes < 0:
        total_minutes += 24 * 60
    elif total_minutes >= 24 * 60:
        total_minutes -= 24 * 60
    return total_minutes // 60, total_minutes % 60


@click.command()
@click.option(
    "--region", "-r",
    multiple=True,
    help="AWS region(s) to analyze. Can specify multiple times.",
)
@click.option(
    "--profile", "-p",
    help="AWS profile to use",
)
@click.option(
    "--instance-id", "-i",
    help="Specific instance ID to schedule",
)
@click.option(
    "--stop-time",
    help="Time to stop instance (24h format, e.g., '22:00')",
)
@click.option(
    "--start-time", 
    help="Time to start instance (24h format, e.g., '06:00')",
)
@click.option(
    "--days",
    default=7,
    help="Days of CloudWatch data to analyze for recommendations",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be created without actually creating",
)
@click.option(
    "--remove",
    is_flag=True,
    help="Remove existing schedules instead of creating",
)
@click.pass_context
def schedule(
    ctx,
    region: tuple,
    profile: Optional[str],
    instance_id: Optional[str],
    stop_time: Optional[str],
    start_time: Optional[str],
    days: int,
    dry_run: bool,
    remove: bool,
):
    """
    Configure automatic start/stop schedules for EC2 instances.
    
    Analyzes instance usage patterns and creates EventBridge rules
    to stop instances during idle hours and start them before peak usage.
    
    Examples:
    
        # Auto-detect and apply schedules based on usage patterns
        cloud-cost-slayer schedule --region us-east-1
        
        # Schedule specific instance with custom times
        cloud-cost-slayer schedule -i i-1234567890 --stop-time 22:00 --start-time 06:00
        
        # Preview what would be created
        cloud-cost-slayer schedule --region us-east-1 --dry-run
        
        # Remove existing schedules
        cloud-cost-slayer schedule --region us-east-1 --remove
    """
    print_header("EC2 Instance Scheduling", "Configure automatic start/stop schedules")
    
    try:
        # Initialize AWS client
        aws_client = AWSClient(profile=profile)
        
        # Test credentials
        success, message = aws_client.test_credentials()
        if not success:
            print_error(message)
            raise click.Abort()
        print_success(message)
        
        # Parse regions
        regions = list(region) if region else parse_regions(None)
        if not regions:
            # Default to common regions if none specified
            regions = ["us-east-1", "us-west-2", "eu-west-1"]
        print_info(f"Regions: {', '.join(regions)}")
        
        # Initialize collectors
        ec2_collector = EC2Collector(aws_client)
        cw_collector = CloudWatchCollector(aws_client)
        pattern_detector = PatternDetector(idle_threshold=10.0, low_usage_threshold=20.0)
        
        # Collect instances
        if instance_id:
            # Get specific instance
            for r in regions:
                inst = ec2_collector.get_instance_by_id(instance_id, r)
                if inst:
                    instances = [inst]
                    break
            else:
                print_error(f"Instance {instance_id} not found in specified regions")
                return
        else:
            # Get all running instances
            instances = ec2_collector.collect_all_instances(
                regions=regions,
                states=["running"],
                show_progress=True,
            )
        
        if not instances:
            print_info("No running instances found")
            return
        
        # Handle removal
        if remove:
            _remove_schedules(aws_client, instances, dry_run)
            return
        
        # Collect metrics and analyze patterns
        print_info("Analyzing usage patterns...")
        metrics = cw_collector.collect_batch_metrics(instances, days=days, show_progress=True)
        
        # Find scheduling candidates
        scheduling_candidates = []
        
        for inst in instances:
            inst_id = inst["instance_id"]
            inst_metrics = metrics.get(inst_id, {})
            
            # Detect patterns
            pattern = pattern_detector.detect_patterns(inst, inst_metrics)
            
            if pattern.can_schedule or (stop_time and start_time):
                # Use custom times if provided, otherwise use detected pattern
                if stop_time and start_time:
                    suggested_stop = stop_time
                    suggested_start = start_time
                elif pattern.suggested_schedule:
                    # Parse suggested schedule
                    suggested_stop, suggested_start = _parse_schedule_suggestion(
                        pattern.suggested_schedule, 
                        pattern.idle_hours
                    )
                else:
                    continue
                
                scheduling_candidates.append({
                    "instance": inst,
                    "pattern": pattern,
                    "stop_time": suggested_stop,
                    "start_time": suggested_start,
                })
        
        if not scheduling_candidates:
            print_info("No instances suitable for scheduling found")
            print_info("Tip: Use --stop-time and --start-time to force a schedule")
            return
        
        # Display recommendations
        console.print()
        console.print("[bold]📅 Scheduling Recommendations:[/bold]")
        console.print()
        
        for candidate in scheduling_candidates:
            inst = candidate["instance"]
            pattern = candidate["pattern"]
            stop = candidate["stop_time"]
            start = candidate["start_time"]
            region = inst["region"]
            
            # Get timezone info
            offset = _get_timezone_offset(region)
            tz_name = "UTC" if offset == 0 else f"UTC{'+' if offset > 0 else ''}{offset:g}"
            
            # Parse times (assumed local) and convert to UTC for display
            stop_h, stop_m = map(int, stop.replace(":", " ").split())
            start_h, start_m = map(int, start.replace(":", " ").split())
            stop_utc_h, stop_utc_m = _local_to_utc(stop_h, stop_m, offset)
            start_utc_h, start_utc_m = _local_to_utc(start_h, start_m, offset)
            
            console.print(f"  [cyan]{inst['instance_id']}[/cyan] ({inst['instance_type']})")
            if inst.get("name"):
                console.print(f"    Name: {inst['name']}")
            console.print(f"    Region: {region} ({tz_name})")
            console.print(f"    Schedule (local): [yellow]Stop at {stop}, Start at {start}[/yellow]")
            console.print(f"    [dim]EventBridge (UTC): Stop at {stop_utc_h:02d}:{stop_utc_m:02d}, Start at {start_utc_h:02d}:{start_utc_m:02d}[/dim]")
            
            # Calculate savings
            if pattern.weekly_idle_hours:
                from ..utils.calculator import get_calculator
                calc = get_calculator()
                hourly_rate = calc.get_instance_pricing(inst["instance_type"], inst["region"])
                hours_per_month = pattern.weekly_idle_hours * 4.3
                savings = hours_per_month * hourly_rate
                console.print(f"    Potential savings: [green]${savings:.2f}/month[/green]")
            console.print()
        
        if dry_run:
            print_warning("Dry run mode - no changes made")
            print_info("Remove --dry-run to apply schedules")
            return
        
        # Confirm with user
        console.print()
        if not click.confirm("Apply these schedules?", default=False):
            print_info("Cancelled - no changes made")
            return
        
        # Create EventBridge rules
        console.print()
        for candidate in scheduling_candidates:
            _create_schedule(aws_client, candidate)
        
        console.print()
        print_success("Schedules created successfully!")
        print_info("Tip: Use 'cloud-cost-slayer schedule --remove' to remove schedules")
        
    except AWSClientError as e:
        print_error(str(e))
        raise click.Abort()
    except Exception as e:
        logger.exception("Schedule command failed")
        print_error(f"Unexpected error: {e}")
        raise click.Abort()


def _parse_schedule_suggestion(suggestion: str, idle_hours: list) -> tuple:
    """Parse schedule suggestion into stop/start times."""
    # Default times if parsing fails
    default_stop = "22:00"
    default_start = "06:00"
    
    if not idle_hours:
        return default_stop, default_start
    
    # Find contiguous idle period
    sorted_hours = sorted(idle_hours)
    
    # Find the longest contiguous period
    if sorted_hours:
        # Simple approach: find first and last idle hour
        # Handle wrap-around (e.g., 22, 23, 0, 1, 2, 3, 4, 5)
        
        # Check if it wraps around midnight
        if 0 in sorted_hours and 23 in sorted_hours:
            # Night idle period
            night_hours = [h for h in sorted_hours if h >= 18 or h <= 8]
            if night_hours:
                stop_hour = min(h for h in night_hours if h >= 18) if any(h >= 18 for h in night_hours) else 22
                start_hour = max(h for h in night_hours if h <= 8) + 1 if any(h <= 8 for h in night_hours) else 6
                return f"{stop_hour:02d}:00", f"{start_hour:02d}:00"
        
        # Daytime idle period or simple contiguous
        stop_hour = sorted_hours[0]
        start_hour = (sorted_hours[-1] + 1) % 24
        return f"{stop_hour:02d}:00", f"{start_hour:02d}:00"
    
    return default_stop, default_start


def _create_schedule(aws_client: AWSClient, candidate: dict):
    """Create EventBridge rules for stop/start schedule."""
    inst = candidate["instance"]
    inst_id = inst["instance_id"]
    region = inst["region"]
    stop_time = candidate["stop_time"]
    start_time = candidate["start_time"]
    
    events = aws_client.get_client("events", region)
    
    # Parse local times
    stop_hour, stop_min = map(int, stop_time.replace(":", " ").split())
    start_hour, start_min = map(int, start_time.replace(":", " ").split())
    
    # Convert local times to UTC for EventBridge
    offset = _get_timezone_offset(region)
    stop_utc_h, stop_utc_m = _local_to_utc(stop_hour, stop_min, offset)
    start_utc_h, start_utc_m = _local_to_utc(start_hour, start_min, offset)
    
    tz_name = "UTC" if offset == 0 else f"UTC{'+' if offset > 0 else ''}{offset:g}"
    
    # Create stop rule (using UTC time for EventBridge)
    stop_rule_name = f"cost-sleuth-stop-{inst_id}"
    stop_cron = f"cron({stop_utc_m} {stop_utc_h} * * ? *)"
    
    try:
        events.put_rule(
            Name=stop_rule_name,
            ScheduleExpression=stop_cron,
            State="ENABLED",
            Description=f"Stop EC2 instance {inst_id} at {stop_time} {tz_name} (created by cloud-cost-slayer)",
        )
        
        # Add target to stop instance
        events.put_targets(
            Rule=stop_rule_name,
            Targets=[{
                "Id": f"stop-{inst_id}",
                "Arn": f"arn:aws:ssm:{region}::automation-definition/AWS-StopEC2Instance",
                "RoleArn": _get_or_create_scheduler_role(aws_client, region),
                "Input": f'{{"InstanceId": ["{inst_id}"]}}',
            }]
        )
        
        print_success(f"Created stop rule: {stop_rule_name} (at {stop_time})")
        
    except Exception as e:
        # Fallback: Create rule without automation (just documents intent)
        error_msg = str(e)
        if "AccessDenied" in error_msg or "not authorized" in error_msg:
            console.print(f"[yellow]Note: Limited permissions - creating rule without automation target[/yellow]")
            console.print(f"[dim]To auto-stop, run: aws ec2 stop-instances --instance-ids {inst_id}[/dim]")
        else:
            print_error(f"Failed to create stop rule: {e}")
            return
    
    # Create start rule (using UTC time for EventBridge)
    start_rule_name = f"cost-sleuth-start-{inst_id}"
    start_cron = f"cron({start_utc_m} {start_utc_h} * * ? *)"
    
    try:
        events.put_rule(
            Name=start_rule_name,
            ScheduleExpression=start_cron,
            State="ENABLED",
            Description=f"Start EC2 instance {inst_id} at {start_time} {tz_name} (created by cloud-cost-slayer)",
        )
        
        events.put_targets(
            Rule=start_rule_name,
            Targets=[{
                "Id": f"start-{inst_id}",
                "Arn": f"arn:aws:ssm:{region}::automation-definition/AWS-StartEC2Instance",
                "RoleArn": _get_or_create_scheduler_role(aws_client, region),
                "Input": f'{{"InstanceId": ["{inst_id}"]}}',
            }]
        )
        
        print_success(f"Created start rule: {start_rule_name} (at {start_time})")
        
    except Exception as e:
        error_msg = str(e)
        if "AccessDenied" in error_msg or "not authorized" in error_msg:
            console.print(f"[dim]To auto-start, run: aws ec2 start-instances --instance-ids {inst_id}[/dim]")
        else:
            print_error(f"Failed to create start rule: {e}")


def _get_or_create_scheduler_role(aws_client: AWSClient, region: str) -> str:
    """Get or create IAM role for EventBridge to invoke SSM Automation."""
    iam = aws_client.get_client("iam", region)
    role_name = "CostSleuthSchedulerRole"
    
    try:
        response = iam.get_role(RoleName=role_name)
        return response["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        pass
    except Exception:
        # If we can't check/create role, return a placeholder
        # The put_targets will fail but we handle that
        sts = aws_client.get_client("sts", region)
        account_id = sts.get_caller_identity()["Account"]
        return f"arn:aws:iam::{account_id}:role/{role_name}"
    
    # Create the role
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "events.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }
    
    try:
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=str(trust_policy).replace("'", '"'),
            Description="Role for Cloud Cost Slayer instance scheduler",
        )
        
        # Attach policy for SSM automation
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonSSMAutomationRole"
        )
        
        return response["Role"]["Arn"]
        
    except Exception as e:
        logger.warning(f"Could not create scheduler role: {e}")
        sts = aws_client.get_client("sts", region)
        account_id = sts.get_caller_identity()["Account"]
        return f"arn:aws:iam::{account_id}:role/{role_name}"


def _remove_schedules(aws_client: AWSClient, instances: list, dry_run: bool):
    """Remove existing cost-sleuth schedules."""
    console.print()
    console.print("[bold]🗑️ Removing Schedules:[/bold]")
    console.print()
    
    removed = 0
    
    for inst in instances:
        inst_id = inst["instance_id"]
        region = inst["region"]
        
        events = aws_client.get_client("events", region)
        
        for action in ["stop", "start"]:
            rule_name = f"cost-sleuth-{action}-{inst_id}"
            
            try:
                # Check if rule exists
                events.describe_rule(Name=rule_name)
                
                if dry_run:
                    console.print(f"  Would remove: {rule_name}")
                    removed += 1
                else:
                    # Remove targets first
                    try:
                        events.remove_targets(Rule=rule_name, Ids=[f"{action}-{inst_id}"])
                    except Exception:
                        pass
                    
                    # Delete rule
                    events.delete_rule(Name=rule_name)
                    print_success(f"Removed: {rule_name}")
                    removed += 1
                    
            except events.exceptions.ResourceNotFoundException:
                pass
            except Exception as e:
                logger.debug(f"Could not remove {rule_name}: {e}")
    
    if removed == 0:
        print_info("No cost-sleuth schedules found to remove")
    elif dry_run:
        console.print()
        print_warning(f"Would remove {removed} schedule(s) - dry run mode")
    else:
        console.print()
        print_success(f"Removed {removed} schedule(s)")
