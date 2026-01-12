"""
Cloud Cost Slayer CLI - Main Entry Point.

A CLI tool for analyzing AWS EC2 usage and generating
cost optimization recommendations.
"""

import click
import sys
from typing import Optional

from . import __version__
from .utils.logger import setup_logger, console
from .commands.analyze import analyze
from .commands.report import report
from .commands.config import config
from .commands.schedule import schedule
from .commands.apply import apply
from .commands.monitor import monitor


# ASCII art banner
BANNER = """
   ___ ____ ___       ____ ____ ____ ___    ____ _    ____ _  _ ___ _  _ 
  /_\\ \\ /__\\ | |___ \\  \\_  \\ | |___ / |  | |___ | | |_ |__]  ]| |__]|_]
 / _ \\__\\ \\  | |___  __\\ |  | |___  \\ |__|___||__|__|  ||__][__|  | |  
/_/ \\_\\__/___|___| |____| |___|____\\___|    |____|____|_|  |___|  |_|    
"""


class AliasedGroup(click.Group):
    """Custom Click group for command aliases."""
    
    def get_command(self, ctx, cmd_name):
        # Support common aliases
        aliases = {
            "analyse": "analyze",  # British spelling
            "scan": "analyze",
            "check": "analyze",
            "gen": "report",
            "sched": "schedule",
        }
        cmd_name = aliases.get(cmd_name, cmd_name)
        return super().get_command(ctx, cmd_name)


@click.group(cls=AliasedGroup)
@click.version_option(version=__version__, prog_name="cloud-cost-slayer")
@click.option(
    "--profile", "-p",
    envvar="AWS_PROFILE",
    help="AWS profile name to use."
)
@click.option(
    "--region", "-r",
    envvar="AWS_REGION",
    help="AWS region (default: all regions)."
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose/debug output."
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would happen without making changes."
)
@click.option(
    "--output", "-o",
    type=click.Choice(["json", "table", "yaml"]),
    default="table",
    help="Output format for results."
)
@click.pass_context
def cli(
    ctx: click.Context,
    profile: Optional[str],
    region: Optional[str],
    verbose: bool,
    dry_run: bool,
    output: str,
):
    """
    Cloud Cost Slayer - Analyze AWS costs and find optimization opportunities.
    
    A CLI tool that scans your AWS EC2 instances, analyzes usage patterns,
    and generates actionable recommendations to reduce costs.
    
    \b
    Quick Start:
      cloud-cost-slayer analyze                 # Analyze all regions
      cloud-cost-slayer analyze -r us-east-1    # Analyze specific region
      cloud-cost-slayer report -f html          # Generate HTML report
      cloud-cost-slayer config test             # Test AWS credentials
    
    \b
    Features:
      - Right-sizing recommendations for over-provisioned instances
      - Confidence scoring (high/medium/low)
      - Terraform and shell scripts for implementation
      - HTML, JSON, and Markdown reports
    
    For more information, visit: https://github.com/yourusername/cloud-cost-slayer
    """
    # Initialize context
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile
    ctx.obj["region"] = region
    ctx.obj["verbose"] = verbose
    ctx.obj["dry_run"] = dry_run
    ctx.obj["output"] = output
    
    # Setup logging
    setup_logger(verbose=verbose)
    
    # Show banner only for main commands (not for help/version)
    if ctx.invoked_subcommand and not verbose:
        # Skip banner for cleaner output
        pass


# Register commands
cli.add_command(analyze)
cli.add_command(report)
cli.add_command(config)
cli.add_command(schedule)
cli.add_command(apply)
cli.add_command(monitor)


# Add a simple summary command
@cli.command("summary")
@click.pass_context
def summary(ctx):
    """
    Show a quick summary of your AWS cost optimization status.
    
    Displays a brief overview of recent analysis results
    and potential savings opportunities.
    """
    from pathlib import Path
    import json
    
    console.print()
    console.print("[bold blue]Cloud Cost Slayer Summary[/bold blue]")
    console.print()
    
    # Check for recent analysis
    output_path = Path("./cost-sleuth-output/analysis.json")
    
    if output_path.exists():
        with open(output_path) as f:
            data = json.load(f)
        
        summary_data = data.get("summary", {})
        
        console.print(f"[green]✓[/green] Found recent analysis data")
        console.print()
        console.print(f"  Recommendations: {summary_data.get('total_recommendations', 0)}")
        console.print(f"  Monthly Savings: [bold green]${summary_data.get('total_monthly_savings', 0):,.2f}[/bold green]")
        console.print(f"  Annual Savings:  [bold green]${summary_data.get('total_annual_savings', 0):,.2f}[/bold green]")
        console.print()
        console.print(f"  High Confidence: {summary_data.get('high_confidence_count', 0)} recommendations")
        console.print(f"  Medium:          {summary_data.get('medium_confidence_count', 0)} recommendations")
        console.print(f"  Low:             {summary_data.get('low_confidence_count', 0)} recommendations")
    else:
        console.print("[yellow]No recent analysis found.[/yellow]")
        console.print()
        console.print("Run [bold]cloud-cost-slayer analyze[/bold] to scan your AWS accounts.")
    
    console.print()


def main():
    """Main entry point for the CLI."""
    try:
        cli(obj={})
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
