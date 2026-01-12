"""
Report command - Generate cost optimization reports.

Generates reports from previous analysis results in various formats.
"""

import json
import click
from pathlib import Path

from ..utils.logger import (
    get_logger,
    print_header,
    print_success,
    print_error,
    print_info,
    console,
)
from ..generators.report_generator import ReportGenerator

logger = get_logger(__name__)


@click.command("report")
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["html", "json", "markdown", "table"]),
    default="table",
    help="Output format (default: table)."
)
@click.option(
    "--output", "-o",
    "output_path",
    type=click.Path(),
    help="Output file path. If not specified, prints to console."
)
@click.option(
    "--input", "-i",
    "input_path",
    type=click.Path(exists=True),
    help="Input JSON file from previous analysis."
)
@click.option(
    "--confidence",
    type=click.Choice(["high", "medium", "low", "all"]),
    default="all",
    help="Filter by confidence level."
)
@click.option(
    "--min-savings",
    default=0.0,
    type=float,
    help="Minimum monthly savings to include."
)
@click.option(
    "--limit",
    default=50,
    type=int,
    help="Maximum number of recommendations to include."
)
@click.pass_context
def report(
    ctx,
    output_format: str,
    output_path: str,
    input_path: str,
    confidence: str,
    min_savings: float,
    limit: int,
):
    """
    Generate cost optimization reports.
    
    Can generate reports from a previous analysis JSON file,
    or display the last analysis results.
    
    Examples:
    
      cloud-cost-slayer report
    
      cloud-cost-slayer report --format html --output report.html
    
      cloud-cost-slayer report --input analysis.json --format markdown
    
      cloud-cost-slayer report --confidence high --min-savings 50
    """
    print_header("Cloud Cost Slayer Report", "Generating cost optimization report")
    
    try:
        # Load data
        if input_path:
            with open(input_path) as f:
                data = json.load(f)
            recommendations = data.get("recommendations", [])
            instances_analyzed = data.get("summary", {}).get("instances_analyzed", 0)
            print_info(f"Loaded {len(recommendations)} recommendations from {input_path}")
        else:
            # Look for recent analysis file
            default_path = Path("./cost-sleuth-output/analysis.json")
            if default_path.exists():
                with open(default_path) as f:
                    data = json.load(f)
                recommendations = data.get("recommendations", [])
                instances_analyzed = data.get("summary", {}).get("instances_analyzed", 0)
                print_info(f"Loaded {len(recommendations)} recommendations from {default_path}")
            else:
                print_error(
                    "No analysis data found. Run 'cloud-cost-slayer analyze' first, "
                    "or specify an input file with --input."
                )
                raise click.Abort()
        
        if not recommendations:
            print_info("No recommendations to report")
            return
        
        # Filter by confidence
        if confidence != "all":
            recommendations = [
                r for r in recommendations
                if r.get("confidence", "").lower() == confidence
            ]
            print_info(f"Filtered to {len(recommendations)} {confidence}-confidence recommendations")
        
        # Filter by minimum savings
        if min_savings > 0:
            recommendations = [
                r for r in recommendations
                if r.get("monthly_savings", 0) >= min_savings
            ]
            print_info(f"Filtered to {len(recommendations)} with savings >= ${min_savings}")
        
        # Apply limit
        recommendations = recommendations[:limit]
        
        # Generate report
        generator = ReportGenerator()
        content = generator.generate_report(
            recommendations,
            instances_analyzed=instances_analyzed,
            format_type=output_format,
            output_path=output_path,
        )
        
        # Output
        if output_path:
            print_success(f"Report saved to {output_path}")
        else:
            if output_format == "table":
                console.print(content)
            elif output_format == "json":
                console.print_json(content)
            else:
                console.print(content)
        
    except Exception as e:
        logger.exception("Report generation failed")
        print_error(f"Report generation failed: {str(e)}")
        raise click.Abort()
