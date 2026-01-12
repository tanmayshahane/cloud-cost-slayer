"""
Analyze command - Run cost optimization analysis.

Scans EC2 instances, collects metrics, and generates recommendations.
"""

import click
from typing import Optional

from ..utils.logger import (
    get_logger,
    print_header,
    print_success,
    print_error,
    print_info,
    print_warning,
    print_savings_summary,
    print_recommendations_table,
    console,
)
from ..utils.aws_client import AWSClient, AWSClientError
from ..utils.calculator import CostCalculator
from ..utils.validators import parse_regions, parse_tag_filters
from ..collectors.ec2_collector import EC2Collector
from ..collectors.cloudwatch_collector import CloudWatchCollector
from ..collectors.rds_collector import RDSCollector
from ..analyzers.rightsizing_analyzer import RightsizingAnalyzer
from ..analyzers.pattern_detector import PatternDetector
from ..generators.terraform_generator import TerraformGenerator
from ..generators.report_generator import ReportGenerator

logger = get_logger(__name__)


@click.command("analyze")
@click.option(
    "--region", "-r",
    multiple=True,
    help="AWS region(s) to analyze. Can specify multiple times. Default: all regions."
)
@click.option(
    "--exclude-tag", "-e",
    multiple=True,
    help="Exclude instances with this tag (format: Key=Value). Can specify multiple."
)
@click.option(
    "--include-running-only/--include-all",
    default=True,
    help="Include only running instances (default) or all."
)
@click.option(
    "--exclude-production/--include-production",
    default=True,
    help="Exclude production instances (default: exclude)."
)
@click.option(
    "--days", "-d",
    default=30,
    type=int,
    help="Number of days of metrics to analyze (default: 30)."
)
@click.option(
    "--min-savings",
    default=5.0,
    type=float,
    help="Minimum monthly savings to report (default: $5)."
)
@click.option(
    "--terraform",
    is_flag=True,
    help="Generate Terraform files for recommendations."
)
@click.option(
    "--output-dir", "-o",
    default="./cost-sleuth-output",
    help="Output directory for generated files."
)
@click.pass_context
def analyze(
    ctx,
    region: tuple,
    exclude_tag: tuple,
    include_running_only: bool,
    exclude_production: bool,
    days: int,
    min_savings: float,
    terraform: bool,
    output_dir: str,
):
    """
    Analyze AWS EC2 instances for cost optimization opportunities.
    
    Scans instances, collects CloudWatch metrics, and generates
    rightsizing recommendations with confidence scores.
    
    Examples:
    
      cloud-cost-slayer analyze
    
      cloud-cost-slayer analyze --region us-east-1 --region us-west-2
    
      cloud-cost-slayer analyze --exclude-tag Environment=production
    
      cloud-cost-slayer analyze --terraform --output-dir ./terraform
    """
    # Get global options from context
    profile = ctx.obj.get("profile")
    verbose = ctx.obj.get("verbose", False)
    dry_run = ctx.obj.get("dry_run", False)
    
    print_header(
        "Cloud Cost Slayer Analysis",
        f"Analyzing EC2 instances for optimization opportunities"
    )
    
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
        regions = list(region) if region else None
        if regions:
            print_info(f"Regions: {', '.join(regions)}")
        else:
            print_info("Scanning all available regions...")
        
        # Parse exclude tags
        exclude_tags = []
        for tag in exclude_tag:
            try:
                key, value = tag.split("=", 1)
                exclude_tags.append((key, value))
            except ValueError:
                print_warning(f"Invalid tag format: {tag} (expected Key=Value)")
        
        # Collect EC2 instances
        ec2_collector = EC2Collector(aws_client)
        states = ["running"] if include_running_only else ["running", "stopped"]
        
        instances = ec2_collector.collect_all_instances(
            regions=regions,
            exclude_tags=exclude_tags,
            states=states,
            show_progress=True,
        )
        
        if not instances:
            print_warning("No EC2 instances found matching the criteria")
        else:
            print_success(f"Found {len(instances)} EC2 instances")
        
        # Collect CloudWatch metrics for EC2
        cw_collector = CloudWatchCollector(aws_client)
        metrics = {}
        if instances:
            metrics = cw_collector.collect_batch_metrics(
                instances,
                days=days,
                show_progress=True,
            )
        
        # Collect RDS instances
        rds_collector = RDSCollector(aws_client)
        rds_instances = rds_collector.collect_all_instances(
            regions=regions,
            states=["available", "backing-up", "modifying"],
            show_progress=True,
        )
        
        if rds_instances:
            print_success(f"Found {len(rds_instances)} RDS databases")
        
        # Collect CloudWatch metrics for RDS
        rds_metrics = {}
        if rds_instances:
            rds_metrics = cw_collector.collect_batch_rds_metrics(
                rds_instances,
                days=days,
                show_progress=True,
            )
        
        # Run rightsizing analysis
        analyzer = RightsizingAnalyzer(
            exclude_production=exclude_production,
            exclude_databases=True,
            min_savings=min_savings,
        )
        
        recommendations = analyzer.analyze_batch(instances, metrics)
        
        # Always show instance analysis with beginner-friendly explanations
        if not recommendations:
            from datetime import datetime
            from ..utils.calculator import get_calculator
            
            calc = get_calculator()
            console.print()
            console.print("[bold cyan]📊 Your EC2 Instances Analysis[/bold cyan]")
            console.print("[dim]Here's what we found about your running servers:[/dim]")
            console.print()
            
            monitoring_issues = []
            idle_instances = []
            storage_recommendations = []
            
            for inst in instances:
                inst_id = inst["instance_id"]
                inst_type = inst["instance_type"]
                inst_name = inst.get("name", "Unnamed")
                inst_metrics = metrics.get(inst_id, {})
                cpu = inst_metrics.get("CPUUtilization", {})
                monitoring = inst.get("monitoring_enabled", False)
                running_days = inst.get("running_days", 0)
                running_hours = inst.get("running_hours", 0)
                region = inst.get("region", "us-east-1")
                
                # Calculate costs - use hours elapsed THIS MONTH only
                hourly_rate = calc.get_instance_pricing(inst_type, region)
                now = datetime.now()
                
                # Hours elapsed in current month (day * 24 + current hour)
                hours_this_month = (now.day - 1) * 24 + now.hour
                
                # If instance was created this month, use running_hours if smaller
                launch_time = inst.get("launch_time")
                if launch_time and hasattr(launch_time, "month"):
                    if launch_time.month == now.month and launch_time.year == now.year:
                        hours_this_month = min(hours_this_month, running_hours)
                
                current_month_cost = hours_this_month * hourly_rate
                
                # Project remaining cost for month
                days_in_month = 31
                remaining_days = days_in_month - now.day
                remaining_hours = remaining_days * 24 + (24 - now.hour)
                projected_additional = remaining_hours * hourly_rate
                projected_month_total = current_month_cost + projected_additional
                
                # CPU stats
                cpu_avg = cpu.get("average", 0)
                cpu_max = cpu.get("maximum", cpu.get("average_max", 0))
                cpu_p95 = cpu.get("p95", cpu_avg)
                
                # Instance header with name
                console.print(f"[bold]🖥️  {inst_name}[/bold]")
                console.print(f"[dim]   ID: {inst_id} | Type: {inst_type} | Region: {region}[/dim]")
                console.print()
                
                # Cost breakdown - beginner friendly
                console.print(f"   [bold yellow]💰 Cost Breakdown[/bold yellow]")
                console.print(f"   This server costs [cyan]${hourly_rate:.4f} per hour[/cyan] to run.")
                console.print(f"   So far this month: [yellow]${current_month_cost:.2f}[/yellow] ({hours_this_month} hours)")
                console.print(f"   If it runs 24/7: ~[yellow]${projected_month_total:.2f}[/yellow] by month end")
                
                # Storage info
                ebs_volumes = inst.get("ebs_volumes", [])
                total_storage_cost = 0
                if ebs_volumes:
                    volume_ids = [v["volume_id"] for v in ebs_volumes]
                    volume_details = ec2_collector.get_volume_details(volume_ids, region)
                    if volume_details:
                        total_storage_gb = sum(v["size_gb"] for v in volume_details)
                        total_storage_cost = sum(v["monthly_cost"] for v in volume_details)
                        console.print()
                        console.print(f"   [bold yellow]💾 Storage (Hard Drives)[/bold yellow]")
                        console.print(f"   Your server has [cyan]{total_storage_gb} GB[/cyan] of disk space")
                        console.print(f"   Storage costs [yellow]${total_storage_cost:.2f}/month[/yellow] (separate from computing)")
                        
                        # Get IOPS metrics for each volume
                        for vol in volume_details:
                            vol_metrics = cw_collector.collect_volume_metrics(vol["volume_id"], region, days=7)
                            total_iops = vol_metrics.get("read_iops_avg", 0) + vol_metrics.get("write_iops_avg", 0)
                            max_iops = vol_metrics.get("iops_max", 0)
                            
                            # Calculate IOPS utilization
                            if vol["volume_type"] == "gp3":
                                baseline_iops = max(3000, vol.get("iops", 3000))
                            elif vol["volume_type"] == "gp2":
                                baseline_iops = min(vol["size_gb"] * 3, 16000)
                            else:
                                baseline_iops = vol.get("iops", 3000)
                            
                            iops_util = (max_iops / baseline_iops * 100) if baseline_iops > 0 else 0
                            
                            # Beginner-friendly disk usage explanation
                            if iops_util < 10:
                                usage_desc = "barely used"
                            elif iops_util < 30:
                                usage_desc = "lightly used"
                            elif iops_util < 60:
                                usage_desc = "moderately used"
                            else:
                                usage_desc = "actively used"
                            
                            console.print(f"   └─ {vol['size_gb']} GB disk ({vol['volume_type']}) - [dim]{usage_desc} ({iops_util:.0f}% of capacity)[/dim]")
                            
                            # Storage recommendations
                            if vol["volume_type"] == "gp3" and max_iops < 100:
                                gp2_cost = vol["size_gb"] * 0.10
                                savings = vol["monthly_cost"] - gp2_cost
                                if savings > 0:
                                    storage_recommendations.append({
                                        "volume_id": vol["volume_id"],
                                        "current_type": "gp3",
                                        "recommended_type": "gp2",
                                        "reason": "This disk is barely used",
                                        "savings": savings,
                                    })
                            
                            if vol["volume_type"] == "gp3" and iops_util < 25 and vol["size_gb"] > 8:
                                suggested_size = max(8, vol["size_gb"] // 2)
                                new_cost = suggested_size * 0.08
                                savings = vol["monthly_cost"] - new_cost
                                if savings > 0.50:
                                    storage_recommendations.append({
                                        "volume_id": vol["volume_id"],
                                        "current_size": vol["size_gb"],
                                        "recommended_size": suggested_size,
                                        "reason": "You might not need this much storage",
                                        "savings": savings,
                                    })
                
                # Total cost summary
                total_monthly_cost = projected_month_total + total_storage_cost
                console.print()
                console.print(f"   [bold]📊 Total Monthly Cost: [cyan]${total_monthly_cost:.2f}[/cyan][/bold]")
                console.print(f"   [dim](Server: ${projected_month_total:.2f} + Storage: ${total_storage_cost:.2f})[/dim]")
                
                # CPU Usage analysis - beginner friendly
                datapoints = cpu.get("datapoint_count", 0)
                if datapoints > 0:
                    console.print()
                    console.print(f"   [bold yellow]⚡ How Hard Is It Working?[/bold yellow]")
                    
                    # Translate CPU usage to plain English
                    if cpu_avg < 5:
                        usage_explanation = "Almost idle - this server is barely doing anything"
                        emoji = "😴"
                    elif cpu_avg < 15:
                        usage_explanation = "Light usage - handling minimal workload"
                        emoji = "🌙"
                    elif cpu_avg < 40:
                        usage_explanation = "Moderate usage - healthy workload"
                        emoji = "✅"
                    elif cpu_avg < 70:
                        usage_explanation = "Active - working fairly hard"
                        emoji = "💪"
                    else:
                        usage_explanation = "Heavy usage - working very hard"
                        emoji = "🔥"
                    
                    console.print(f"   {emoji} {usage_explanation}")
                    console.print(f"   [dim]Average: {cpu_avg:.1f}% | Peak: {cpu_max:.1f}%[/dim]")
                    
                    # Detect patterns for scheduling
                    pattern_detector = PatternDetector(idle_threshold=8.0, low_usage_threshold=20.0)
                    pattern = pattern_detector.detect_patterns(inst, inst_metrics)
                    
                    # Show scheduling opportunity
                    if pattern.can_schedule and pattern.weekly_idle_hours > 20:
                        idle_hours_per_week = pattern.weekly_idle_hours
                        hours_per_month = idle_hours_per_week * 4.3
                        potential_savings = hours_per_month * hourly_rate
                        
                        console.print()
                        console.print(f"   [bold green]💡 Money-Saving Opportunity![/bold green]")
                        console.print(f"   This server is idle for about [cyan]{idle_hours_per_week} hours/week[/cyan].")
                        console.print(f"   You could save [green]${potential_savings:.2f}/month[/green] by turning it off during quiet times.")
                        if pattern.suggested_schedule:
                            console.print(f"   Suggestion: {pattern.suggested_schedule}")
                        console.print(f"   [dim]Use: cloud-cost-slayer schedule -i {inst_id} --region {region}[/dim]")
                    
                    # Check if completely idle
                    if cpu_avg < 2 and cpu_max < 10:
                        console.print()
                        console.print(f"   [bold red]⚠️  This Server Looks Unused![/bold red]")
                        console.print(f"   CPU is almost at 0%. You might be paying for a server that's doing nothing.")
                        console.print(f"   Consider stopping it to save [green]${projected_month_total:.2f}/month[/green]")
                        idle_instances.append({
                            "id": inst_id,
                            "region": region,
                            "monthly_cost": projected_month_total,
                            "cpu_avg": cpu_avg,
                            "cpu_max": cpu_max,
                        })
                else:
                    console.print()
                    console.print(f"   [yellow]⏳ Waiting for Data[/yellow]")
                    console.print(f"   We need at least 7 days of data to analyze usage patterns.")
                    if running_days >= 7:
                        console.print(f"   [red]⚠️ No data found despite running {running_days} days.[/red]")
                        console.print(f"   This might be a permissions issue. Check your AWS credentials.")
                        monitoring_issues.append(inst_id)
                    else:
                        console.print(f"   [dim]This server has been running for {running_days} days. Check back later.[/dim]")
                
                console.print()
                console.print("─" * 60)
                console.print()
            
            # Recommendations section
            if idle_instances or storage_recommendations:
                console.print("[bold cyan]💡 Recommendations to Save Money[/bold cyan]")
                console.print()
            
            # Recommend turning off idle instances
            if idle_instances:
                total_idle_cost = sum(i["monthly_cost"] for i in idle_instances)
                console.print(f"[bold red]🔴 Stop Unused Servers[/bold red]")
                console.print(f"   Found {len(idle_instances)} server(s) that appear to be doing nothing.")
                console.print(f"   Potential savings: [bold green]${total_idle_cost:.2f}/month[/bold green]")
                console.print()
                console.print("   To stop them, run:")
                for idle in idle_instances:
                    console.print(f"   aws ec2 stop-instances --instance-ids {idle['id']} --region {idle['region']}")
                console.print()
            
            # Storage recommendations
            if storage_recommendations:
                total_storage_savings = sum(r["savings"] for r in storage_recommendations)
                console.print(f"[bold yellow]💾 Reduce Storage Costs[/bold yellow]")
                console.print(f"   Potential savings: [bold green]${total_storage_savings:.2f}/month[/bold green]")
                console.print()
                for rec in storage_recommendations:
                    if "recommended_type" in rec:
                        console.print(f"   • {rec['reason']}. Switch disk type to save ${rec['savings']:.2f}/mo")
                    elif "recommended_size" in rec:
                        console.print(f"   • {rec['reason']}. Reduce from {rec['current_size']}GB to {rec['recommended_size']}GB to save ${rec['savings']:.2f}/mo")
                console.print()
                console.print("   [dim]⚠️ Before resizing: Check actual disk usage with 'df -h' on the server[/dim]")
                console.print()
            
            if not idle_instances and not storage_recommendations and instances:
                console.print("[bold green]✅ Your EC2 instances look well-configured![/bold green]")
                console.print("   No major cost-saving opportunities found.")
                console.print()
        
        # ======================
        # RDS ANALYSIS SECTION
        # ======================
        if rds_instances:
            console.print()
            console.print("[bold cyan]🗄️  Your RDS Databases Analysis[/bold cyan]")
            console.print("[dim]Here's what we found about your databases:[/dim]")
            console.print()
            
            idle_databases = []
            rds_recommendations = []
            
            for db in rds_instances:
                db_id = db["db_instance_id"]
                db_name = db.get("name", db_id)
                engine = db.get("engine", "unknown")
                engine_version = db.get("engine_version", "")
                instance_class = db.get("instance_class", "db.t3.micro")
                multi_az = db.get("multi_az", False)
                storage_gb = db.get("allocated_storage_gb", 0)
                storage_type = db.get("storage_type", "gp2")
                storage_cost = db.get("storage_monthly_cost", 0)
                hourly_rate = db.get("hourly_rate", 0)
                region = db.get("region", "us-east-1")
                running_days = db.get("running_days", 0)
                running_hours = db.get("running_hours", 0)
                
                # Get metrics
                db_metrics = rds_metrics.get(db_id, {})
                cpu_avg = db_metrics.get("cpu_avg", 0)
                cpu_max = db_metrics.get("cpu_max", 0)
                memory_free_avg = db_metrics.get("memory_free_avg", 0)
                connections_avg = db_metrics.get("connections_avg", 0)
                connections_max = db_metrics.get("connections_max", 0)
                storage_free_gb = db_metrics.get("storage_free_gb", 0)
                
                # Calculate costs - use hours elapsed THIS MONTH, not total running hours
                from datetime import datetime
                now = datetime.now()
                
                # Hours elapsed in current month (day * 24 + current hour)
                hours_this_month = (now.day - 1) * 24 + now.hour
                
                # If instance was created this month, use running_hours if smaller
                create_time = db.get("create_time")
                if create_time and hasattr(create_time, "month"):
                    if create_time.month == now.month and create_time.year == now.year:
                        hours_this_month = min(hours_this_month, running_hours)
                
                current_month_cost = hours_this_month * hourly_rate
                
                # Project to end of month
                days_in_month = 31
                remaining_days = days_in_month - now.day
                remaining_hours = remaining_days * 24 + (24 - now.hour)
                projected_additional = remaining_hours * hourly_rate
                projected_db_cost = current_month_cost + projected_additional
                total_db_monthly = projected_db_cost + storage_cost
                
                # Database header
                engine_display = f"{engine.upper()} {engine_version[:3] if engine_version else ''}"
                multi_az_badge = " [yellow](Multi-AZ)[/yellow]" if multi_az else ""
                console.print(f"[bold]🗄️  {db_name}[/bold]{multi_az_badge}")
                console.print(f"[dim]   ID: {db_id} | Engine: {engine_display} | Class: {instance_class}[/dim]")
                console.print()
                
                # Cost breakdown
                console.print(f"   [bold yellow]💰 Cost Breakdown[/bold yellow]")
                console.print(f"   This database costs [cyan]${hourly_rate:.4f} per hour[/cyan] to run.")
                if multi_az:
                    console.print(f"   [dim](Multi-AZ doubles the cost for high availability)[/dim]")
                console.print(f"   So far this month: [yellow]${current_month_cost:.2f}[/yellow]")
                console.print(f"   Storage: {storage_gb} GB ({storage_type}) - [yellow]${storage_cost:.2f}/month[/yellow]")
                console.print()
                console.print(f"   [bold]📊 Total Monthly Cost: [cyan]${total_db_monthly:.2f}[/cyan][/bold]")
                console.print(f"   [dim](Database: ${projected_db_cost:.2f} + Storage: ${storage_cost:.2f})[/dim]")
                
                # Usage analysis
                datapoints = db_metrics.get("datapoint_count", 0)
                if datapoints > 0:
                    console.print()
                    console.print(f"   [bold yellow]⚡ How Hard Is It Working?[/bold yellow]")
                    
                    # CPU explanation
                    if cpu_avg < 5:
                        usage_explanation = "Almost idle - database is barely used"
                        emoji = "😴"
                    elif cpu_avg < 15:
                        usage_explanation = "Light usage - handling minimal queries"
                        emoji = "🌙"
                    elif cpu_avg < 40:
                        usage_explanation = "Moderate usage - healthy query load"
                        emoji = "✅"
                    elif cpu_avg < 70:
                        usage_explanation = "Active - processing many queries"
                        emoji = "💪"
                    else:
                        usage_explanation = "Heavy usage - working very hard"
                        emoji = "🔥"
                    
                    console.print(f"   {emoji} {usage_explanation}")
                    console.print(f"   [dim]CPU: avg {cpu_avg:.1f}%, peak {cpu_max:.1f}%[/dim]")
                    
                    # Connections
                    if connections_max > 0:
                        console.print(f"   [dim]Connections: avg {connections_avg:.0f}, peak {connections_max:.0f}[/dim]")
                    
                    # Memory (if available)
                    if memory_free_avg > 0:
                        console.print(f"   [dim]Free Memory: {memory_free_avg:.1f} GB[/dim]")
                    
                    # Storage space
                    if storage_free_gb > 0:
                        used_gb = storage_gb - storage_free_gb
                        usage_pct = (used_gb / storage_gb * 100) if storage_gb > 0 else 0
                        console.print(f"   [dim]Storage Used: {used_gb:.1f} GB of {storage_gb} GB ({usage_pct:.0f}%)[/dim]")
                    
                    # Check if idle (low CPU and few connections)
                    if cpu_avg < 5 and connections_max < 10:
                        console.print()
                        console.print(f"   [bold red]⚠️  This Database Looks Underused![/bold red]")
                        console.print(f"   Very low CPU ({cpu_avg:.1f}%) with few connections.")
                        console.print(f"   Consider stopping it to save [green]${total_db_monthly:.2f}/month[/green]")
                        idle_databases.append({
                            "id": db_id,
                            "name": db_name,
                            "region": region,
                            "monthly_cost": total_db_monthly,
                        })
                    
                    # Check if oversized (can downsize)
                    elif cpu_avg < 20 or connections_avg < 20:
                        # Suggest smaller instance
                        smaller_map = {
                            # M5 family
                            "db.m5.large": "db.t3.medium",
                            "db.m5.xlarge": "db.m5.large",
                            "db.m5.2xlarge": "db.m5.xlarge",
                            # M6g family (Graviton)
                            "db.m6g.large": "db.t4g.medium",
                            "db.m6g.xlarge": "db.m6g.large",
                            # R5 family (memory)
                            "db.r5.large": "db.m5.large",
                            "db.r5.xlarge": "db.r5.large",
                            # T3 family (burstable)
                            "db.t3.medium": "db.t3.small",
                            "db.t3.large": "db.t3.medium",
                            "db.t3.xlarge": "db.t3.large",
                            "db.t3.small": "db.t3.micro",
                            # T4g family (Graviton burstable)
                            "db.t4g.medium": "db.t4g.small",
                            "db.t4g.large": "db.t4g.medium",
                            "db.t4g.small": "db.t4g.micro",
                        }
                        from ..collectors.rds_collector import RDS_PRICING
                        
                        if instance_class in smaller_map:
                            smaller = smaller_map[instance_class]
                            smaller_rate = RDS_PRICING.get(smaller, hourly_rate * 0.5)
                            if multi_az:
                                smaller_rate *= 2
                            potential_save = (hourly_rate - smaller_rate) * 720  # 720 hours in month
                            if potential_save > 1:  # Lower threshold to $1
                                console.print()
                                console.print(f"   [bold green]💡 Consider Downsizing![/bold green]")
                                console.print(f"   This database is lightly used (avg {cpu_avg:.1f}% CPU).")
                                console.print(f"   Consider switching from {instance_class} → {smaller}")
                                console.print(f"   Potential savings: [green]${potential_save:.2f}/month[/green]")
                                rds_recommendations.append({
                                    "id": db_id,
                                    "name": db_name,
                                    "current": instance_class,
                                    "recommended": smaller,
                                    "savings": potential_save,
                                })
                        else:
                            # No smaller instance available, but still show it's underused
                            console.print()
                            console.print(f"   [yellow]💡 Lightly Used Database[/yellow]")
                            console.print(f"   Average CPU is only {cpu_avg:.1f}% - this may be oversized.")
                            console.print(f"   [dim]Already on smallest recommended instance class.[/dim]")
                
                else:
                    console.print()
                    console.print(f"   [yellow]⏳ Waiting for Data[/yellow]")
                    console.print(f"   Need more metrics data to analyze usage patterns.")
                
                console.print()
                console.print("─" * 60)
                console.print()
            
            # RDS Recommendations summary
            if idle_databases:
                total_idle_cost = sum(d["monthly_cost"] for d in idle_databases)
                console.print(f"[bold red]🔴 Stop Unused Databases[/bold red]")
                console.print(f"   Found {len(idle_databases)} database(s) that appear to be doing nothing.")
                console.print(f"   Potential savings: [bold green]${total_idle_cost:.2f}/month[/bold green]")
                console.print()
                console.print("   To stop them, run:")
                for db in idle_databases:
                    console.print(f"   aws rds stop-db-instance --db-instance-identifier {db['id']} --region {db['region']}")
                console.print()
            
            # RDS Downsizing summary
            if rds_recommendations:
                total_rds_savings = sum(r["savings"] for r in rds_recommendations)
                console.print(f"[bold green]📉 Downsize Underused Databases[/bold green]")
                console.print(f"   Found {len(rds_recommendations)} database(s) that could use smaller instances.")
                console.print(f"   Potential savings: [bold green]${total_rds_savings:.2f}/month[/bold green]")
                console.print()
                for rec in rds_recommendations:
                    console.print(f"   • {rec['name']}: {rec['current']} → {rec['recommended']} (save ${rec['savings']:.2f}/mo)")
                console.print()
        
        # Calculate total RDS savings
        total_rds_savings = 0
        if rds_instances:
            if 'idle_databases' in dir() and idle_databases:
                total_rds_savings += sum(d["monthly_cost"] for d in idle_databases)
            if 'rds_recommendations' in dir() and rds_recommendations:
                total_rds_savings += sum(r["savings"] for r in rds_recommendations)
        
        if not instances and not rds_instances:
            print_warning("No EC2 instances or RDS databases found")
            return
        
        # If no EC2 recommendations but we have RDS data, show RDS summary only
        if not recommendations and rds_instances:
            console.print()
            console.print("[bold cyan]💰 Savings Summary[/bold cyan]")
            console.print()
            if total_rds_savings > 0:
                console.print(f"   Total potential RDS savings: [bold green]${total_rds_savings:.2f}/month[/bold green]")
                console.print(f"   Annual savings: [bold green]${total_rds_savings * 12:.2f}/year[/bold green]")
            else:
                console.print("   [green]✅ Your databases are well-sized for their usage![/green]")
            console.print()
            return
        
        # EC2 recommendations exist
        if not recommendations:
            return
        
        # Get summary
        summary = analyzer.get_summary(recommendations)
        
        # Print results - include RDS savings
        console.print()
        total_monthly = summary["total_monthly_savings"] + total_rds_savings
        total_annual = summary["total_annual_savings"] + (total_rds_savings * 12)
        print_savings_summary(
            current_cost=sum(r.current_monthly_cost for r in recommendations),
            optimized_cost=sum(r.recommended_monthly_cost for r in recommendations),
            monthly_savings=total_monthly,
            annual_savings=total_annual,
        )
        
        console.print()
        print_recommendations_table([r.to_dict() for r in recommendations[:20]])
        
        if len(recommendations) > 20:
            print_info(f"... and {len(recommendations) - 20} more recommendations")
        
        # Generate output files
        if terraform or output_dir != "./cost-sleuth-output":
            from pathlib import Path
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Generate report
            report_gen = ReportGenerator()
            
            # HTML report
            html_report = report_gen.generate_report(
                recommendations,
                instances_analyzed=len(instances),
                format_type="html",
                output_path=str(output_path / "report.html"),
            )
            print_success(f"Report saved to {output_path / 'report.html'}")
            
            # JSON data
            json_report = report_gen.generate_report(
                recommendations,
                instances_analyzed=len(instances),
                format_type="json",
                output_path=str(output_path / "analysis.json"),
            )
            print_success(f"Data saved to {output_path / 'analysis.json'}")
            
            # Terraform files
            if terraform:
                tf_gen = TerraformGenerator()
                tf_path = tf_gen.generate_and_write(
                    recommendations,
                    output_dir=str(output_path / "terraform"),
                    region=list(region)[0] if region else "us-east-1",
                    profile=profile or "default",
                )
                print_success(f"Terraform files saved to {tf_path}")
        
        # Summary
        console.print()
        print_success(
            f"Analysis complete! Found ${summary['total_monthly_savings']:,.2f}/month "
            f"(${summary['total_annual_savings']:,.2f}/year) in potential savings"
        )
        
    except AWSClientError as e:
        print_error(f"AWS Error: {e.message}")
        raise click.Abort()
    except Exception as e:
        logger.exception("Analysis failed")
        print_error(f"Analysis failed: {str(e)}")
        raise click.Abort()
