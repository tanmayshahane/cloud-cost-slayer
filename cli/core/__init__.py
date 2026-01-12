"""
Core analysis modules for Cloud Cost Slayer.

This package contains shared analysis logic used by CLI commands
and the web server API.
"""

from .analysis_service import (
    calculate_month_hours,
    calculate_remaining_hours,
    calculate_ec2_costs,
    calculate_rds_costs,
    get_cpu_status,
    get_rds_cpu_status,
    build_ec2_instance_data,
    build_rds_instance_data,
)

__all__ = [
    "calculate_month_hours",
    "calculate_remaining_hours",
    "calculate_ec2_costs",
    "calculate_rds_costs",
    "get_cpu_status",
    "get_rds_cpu_status",
    "build_ec2_instance_data",
    "build_rds_instance_data",
]
