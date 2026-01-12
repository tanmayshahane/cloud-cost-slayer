"""
Centralized logging configuration with Rich console integration.

Provides colorized output, progress bars, and formatted tables
for a beautiful CLI experience.
"""

import logging
import sys
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.panel import Panel
from rich.theme import Theme

# Custom theme for consistent branding
SLEUTH_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "savings": "bold green",
    "cost": "bold yellow",
    "instance": "blue",
    "region": "magenta",
})

# Global console instance with theme
console = Console(theme=SLEUTH_THEME)


def setup_logger(
    name: str = "cloud-cost-slayer",
    level: int = logging.INFO,
    verbose: bool = False
) -> logging.Logger:
    """
    Set up and return a configured logger with Rich handler.
    
    Args:
        name: Logger name
        level: Logging level (default: INFO)
        verbose: Enable debug logging if True
    
    Returns:
        Configured logger instance
    """
    if verbose:
        level = logging.DEBUG
    
    # Configure Rich handler
    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=verbose,
        rich_tracebacks=True,
        tracebacks_show_locals=verbose,
    )
    handler.setLevel(level)
    
    # Configure logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers = []  # Clear existing handlers
    logger.addHandler(handler)
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get an existing logger or create a new one.
    
    Args:
        name: Optional logger name (defaults to root)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name or "cloud-cost-slayer")


def create_progress() -> Progress:
    """
    Create a Rich progress bar for long-running operations.
    
    Returns:
        Configured Progress instance
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


def print_header(title: str, subtitle: Optional[str] = None) -> None:
    """
    Print a styled header with optional subtitle.
    
    Args:
        title: Main header text
        subtitle: Optional subtitle text
    """
    content = f"[bold]{title}[/bold]"
    if subtitle:
        content += f"\n[dim]{subtitle}[/dim]"
    
    console.print(Panel(content, border_style="blue", padding=(1, 2)))


def print_success(message: str) -> None:
    """Print a success message with checkmark."""
    console.print(f"[success]✓[/success] {message}")


def print_error(message: str) -> None:
    """Print an error message with X mark."""
    console.print(f"[error]✗[/error] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[warning]⚠[/warning] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[info]ℹ[/info] {message}")


def print_savings_summary(
    current_cost: float,
    optimized_cost: float,
    monthly_savings: float,
    annual_savings: float
) -> None:
    """
    Print a formatted savings summary.
    
    Args:
        current_cost: Current monthly cost
        optimized_cost: Optimized monthly cost
        monthly_savings: Potential monthly savings
        annual_savings: Potential annual savings
    """
    table = Table(title="💰 Savings Summary", border_style="green")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    table.add_row("Current Monthly Cost", f"${current_cost:,.2f}")
    table.add_row("Optimized Monthly Cost", f"${optimized_cost:,.2f}")
    table.add_row("Monthly Savings", f"[savings]${monthly_savings:,.2f}[/savings]")
    table.add_row("Annual Savings", f"[savings]${annual_savings:,.2f}[/savings]")
    
    percentage = (monthly_savings / current_cost * 100) if current_cost > 0 else 0
    table.add_row("Savings Percentage", f"[savings]{percentage:.1f}%[/savings]")
    
    console.print(table)


def print_recommendations_table(recommendations: list[dict]) -> None:
    """
    Print a formatted table of recommendations.
    
    Args:
        recommendations: List of recommendation dictionaries
    """
    if not recommendations:
        print_info("No recommendations found")
        return
    
    table = Table(title="📋 Recommendations", border_style="blue")
    table.add_column("Instance ID", style="instance")
    table.add_column("Current Type", style="yellow")
    table.add_column("Recommended", style="green")
    table.add_column("Monthly Savings", justify="right", style="savings")
    table.add_column("Confidence", justify="center")
    
    for rec in recommendations:
        confidence_style = {
            "high": "[bold green]HIGH[/bold green]",
            "medium": "[yellow]MEDIUM[/yellow]",
            "low": "[red]LOW[/red]"
        }.get(rec.get("confidence", "").lower(), rec.get("confidence", "N/A"))
        
        table.add_row(
            rec.get("instance_id", "N/A"),
            rec.get("current_type", "N/A"),
            rec.get("recommended_type", "N/A"),
            f"${rec.get('monthly_savings', 0):,.2f}",
            confidence_style,
        )
    
    console.print(table)


def print_instances_table(instances: list[dict]) -> None:
    """
    Print a formatted table of EC2 instances.
    
    Args:
        instances: List of instance dictionaries
    """
    if not instances:
        print_info("No instances found")
        return
    
    table = Table(title="🖥️ EC2 Instances", border_style="blue")
    table.add_column("Instance ID", style="instance")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="yellow")
    table.add_column("State", justify="center")
    table.add_column("Region", style="region")
    table.add_column("Monthly Cost", justify="right", style="cost")
    
    for instance in instances:
        state = instance.get("state", "unknown")
        state_style = "[green]running[/green]" if state == "running" else f"[dim]{state}[/dim]"
        
        table.add_row(
            instance.get("instance_id", "N/A"),
            instance.get("name", "N/A")[:30],
            instance.get("instance_type", "N/A"),
            state_style,
            instance.get("region", "N/A"),
            f"${instance.get('monthly_cost', 0):,.2f}",
        )
    
    console.print(table)
