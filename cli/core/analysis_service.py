"""
Core Analysis Service Module

This module provides shared analysis functions used by both CLI commands
and the web server API. It centralizes cost calculations, data formatting,
and analysis logic to ensure consistent output across all interfaces.
"""

from datetime import datetime
from typing import Optional
from ..utils.calculator import get_calculator


def calculate_month_hours(running_hours: int = 0, launch_time: Optional[datetime] = None) -> int:
    """
    Calculate hours elapsed in the current month.
    
    If the instance was created this month, uses the smaller of:
    - Hours elapsed in current month
    - Total running hours since launch
    
    Args:
        running_hours: Total hours the instance has been running
        launch_time: When the instance was launched (optional)
        
    Returns:
        Number of hours to use for current month cost calculation
    """
    now = datetime.now()
    hours_this_month = (now.day - 1) * 24 + now.hour
    
    # If instance was created this month, use running_hours if smaller
    if launch_time and hasattr(launch_time, "month"):
        if launch_time.month == now.month and launch_time.year == now.year:
            hours_this_month = min(hours_this_month, running_hours)
    
    return hours_this_month


def calculate_remaining_hours() -> int:
    """
    Calculate remaining hours until end of month.
    
    Returns:
        Number of hours remaining in the current month
    """
    now = datetime.now()
    # Assume 31 days in month for simplicity
    remaining_days = 31 - now.day
    remaining_hours = remaining_days * 24 + (24 - now.hour)
    return remaining_hours


def calculate_ec2_costs(
    instance_type: str,
    region: str,
    running_hours: int = 0,
    launch_time: Optional[datetime] = None
) -> dict:
    """
    Calculate EC2 instance costs matching CLI output format.
    
    Args:
        instance_type: EC2 instance type (e.g., 't3.micro')
        region: AWS region
        running_hours: Total running hours
        launch_time: Instance launch time
        
    Returns:
        Dictionary with cost breakdown:
        - hourly_rate: Cost per hour
        - hours_this_month: Hours billed this month
        - current_month_cost: Cost so far this month
        - projected_month_cost: Expected cost by month end
    """
    calc = get_calculator()
    hourly_rate = calc.get_instance_pricing(instance_type, region)
    
    hours_this_month = calculate_month_hours(running_hours, launch_time)
    current_month_cost = hours_this_month * hourly_rate
    
    remaining_hours = calculate_remaining_hours()
    projected_month_cost = current_month_cost + (remaining_hours * hourly_rate)
    
    return {
        "hourly_rate": hourly_rate,
        "hours_this_month": hours_this_month,
        "current_month_cost": current_month_cost,
        "projected_month_cost": projected_month_cost,
    }


def calculate_rds_costs(
    hourly_rate: float,
    storage_monthly_cost: float = 0,
    running_hours: int = 0,
    create_time: Optional[datetime] = None
) -> dict:
    """
    Calculate RDS instance costs matching CLI output format.
    
    Args:
        hourly_rate: RDS hourly rate (from RDS collector)
        storage_monthly_cost: Monthly storage cost
        running_hours: Total running hours
        create_time: Instance creation time
        
    Returns:
        Dictionary with cost breakdown:
        - hourly_rate: Cost per hour
        - hours_this_month: Hours billed this month
        - current_month_cost: Cost so far this month (compute only)
        - projected_month_cost: Expected compute cost by month end
        - storage_cost: Monthly storage cost
        - total_monthly_cost: Projected compute + storage
    """
    hours_this_month = calculate_month_hours(running_hours, create_time)
    current_month_cost = hours_this_month * hourly_rate
    
    remaining_hours = calculate_remaining_hours()
    projected_month_cost = current_month_cost + (remaining_hours * hourly_rate)
    total_monthly_cost = projected_month_cost + storage_monthly_cost
    
    return {
        "hourly_rate": hourly_rate,
        "hours_this_month": hours_this_month,
        "current_month_cost": current_month_cost,
        "projected_month_cost": projected_month_cost,
        "storage_cost": storage_monthly_cost,
        "total_monthly_cost": total_monthly_cost,
    }


def get_cpu_status(cpu_avg: float) -> dict:
    """
    Get beginner-friendly CPU status description.
    
    Translates CPU utilization percentage into plain English
    with emojis matching CLI output.
    
    Args:
        cpu_avg: Average CPU utilization percentage
        
    Returns:
        Dictionary with:
        - emoji: Visual indicator
        - label: Short status label
        - description: Beginner-friendly explanation
        - level: Status level ('idle', 'light', 'moderate', 'heavy')
    """
    if cpu_avg < 5:
        return {
            "emoji": "😴",
            "label": "Almost idle",
            "description": "This server is barely doing anything",
            "level": "idle",
        }
    elif cpu_avg < 15:
        return {
            "emoji": "🌙",
            "label": "Light usage",
            "description": "Handling minimal workload",
            "level": "light",
        }
    elif cpu_avg < 40:
        return {
            "emoji": "⚡",
            "label": "Moderate usage",
            "description": "Healthy workload",
            "level": "moderate",
        }
    elif cpu_avg < 70:
        return {
            "emoji": "💪",
            "label": "Active",
            "description": "Processing many requests",
            "level": "active",
        }
    else:
        return {
            "emoji": "🔥",
            "label": "Heavy usage",
            "description": "Working very hard",
            "level": "heavy",
        }


def get_rds_cpu_status(cpu_avg: float) -> dict:
    """
    Get beginner-friendly RDS CPU status description.
    
    Similar to EC2 but with database-specific descriptions.
    
    Args:
        cpu_avg: Average CPU utilization percentage
        
    Returns:
        Dictionary with emoji, label, description, and level
    """
    if cpu_avg < 5:
        return {
            "emoji": "😴",
            "label": "Almost idle",
            "description": "Database is barely used",
            "level": "idle",
        }
    elif cpu_avg < 15:
        return {
            "emoji": "🌙",
            "label": "Light usage",
            "description": "Handling minimal queries",
            "level": "light",
        }
    elif cpu_avg < 40:
        return {
            "emoji": "✅",
            "label": "Moderate usage",
            "description": "Healthy query load",
            "level": "moderate",
        }
    elif cpu_avg < 70:
        return {
            "emoji": "💪",
            "label": "Active",
            "description": "Processing many queries",
            "level": "active",
        }
    else:
        return {
            "emoji": "🔥",
            "label": "Heavy usage",
            "description": "Working very hard",
            "level": "heavy",
        }


def build_ec2_instance_data(
    instance: dict,
    metrics: dict,
    recommendation: Optional[dict] = None
) -> dict:
    """
    Build standardized EC2 instance data for output.
    
    Creates a consistent data structure used by both CLI and web UI,
    including cost calculations, CPU metrics, and recommendations.
    
    Args:
        instance: Raw EC2 instance data from collector
        metrics: CloudWatch metrics for this instance
        recommendation: Optional rightsizing recommendation
        
    Returns:
        Standardized instance data dictionary
    """
    inst_id = instance.get("instance_id", "")
    inst_type = instance.get("instance_type", "")
    inst_name = instance.get("name", inst_id)
    region = instance.get("region", "us-east-1")
    running_hours = instance.get("running_hours", 0)
    launch_time = instance.get("launch_time")
    
    # Get CPU metrics
    cpu_data = metrics.get("CPUUtilization", {})
    cpu_avg = cpu_data.get("average", 0) or 0
    cpu_max = cpu_data.get("maximum", cpu_data.get("average_max", 0)) or 0
    
    # Calculate costs
    costs = calculate_ec2_costs(inst_type, region, running_hours, launch_time)
    cpu_status = get_cpu_status(cpu_avg)
    
    data = {
        "id": inst_id,
        "name": inst_name,
        "type": inst_type,
        "region": region,
        "state": instance.get("state", "running"),
        # Cost data
        "hourlyRate": costs["hourly_rate"],
        "currentMonthCost": costs["current_month_cost"],
        "hoursThisMonth": costs["hours_this_month"],
        "projectedMonthCost": costs["projected_month_cost"],
        # CPU metrics
        "cpuAvg": cpu_avg,
        "cpuMax": cpu_max,
        "cpuStatus": cpu_status,
        # Flags
        "hasRecommendation": recommendation is not None,
    }
    
    if recommendation:
        data["recommendation"] = {
            "type": "rightsizing",
            "currentType": recommendation.current_type,
            "recommendedType": recommendation.recommended_type,
            "monthlySavings": recommendation.monthly_savings,
            "annualSavings": recommendation.monthly_savings * 12,
            "confidence": recommendation.confidence,
            "currentCost": recommendation.current_monthly_cost,
            "newCost": recommendation.recommended_monthly_cost,
        }
    
    return data


def build_rds_instance_data(
    rds_instance: dict,
    metrics: dict
) -> dict:
    """
    Build standardized RDS instance data for output.
    
    Creates a consistent data structure used by both CLI and web UI,
    including cost calculations, CPU metrics, and storage info.
    
    Args:
        rds_instance: Raw RDS instance data from collector
        metrics: CloudWatch metrics for this database
        
    Returns:
        Standardized RDS instance data dictionary
    """
    db_id = rds_instance.get("db_instance_id", "")
    db_name = rds_instance.get("name", db_id)
    db_class = rds_instance.get("instance_class", rds_instance.get("db_instance_class", "db.t3.micro"))
    region = rds_instance.get("region", "us-east-1")
    running_hours = rds_instance.get("running_hours", 0)
    create_time = rds_instance.get("create_time")
    
    # RDS-specific fields
    hourly_rate = rds_instance.get("hourly_rate", 0)
    storage_cost = rds_instance.get("storage_monthly_cost", 0)
    storage_gb = rds_instance.get("allocated_storage_gb", 0)
    engine = rds_instance.get("engine", "")
    engine_version = rds_instance.get("engine_version", "")
    multi_az = rds_instance.get("multi_az", False)
    
    # Get CPU metrics
    cpu_avg = metrics.get("cpu_avg", 0) or 0
    cpu_max = metrics.get("cpu_max", 0) or 0
    
    # Calculate costs
    costs = calculate_rds_costs(hourly_rate, storage_cost, running_hours, create_time)
    cpu_status = get_rds_cpu_status(cpu_avg)
    
    return {
        "id": db_id,
        "name": db_name,
        "type": db_class,
        "region": region,
        # Database info
        "engine": engine,
        "engineVersion": engine_version,
        "multiAz": multi_az,
        "storageGb": storage_gb,
        # Cost data
        "hourlyRate": costs["hourly_rate"],
        "currentMonthCost": costs["current_month_cost"],
        "hoursThisMonth": costs["hours_this_month"],
        "projectedMonthCost": costs["projected_month_cost"],
        "storageCost": costs["storage_cost"],
        "totalMonthlyCost": costs["total_monthly_cost"],
        # CPU metrics
        "cpuAvg": cpu_avg,
        "cpuMax": cpu_max,
        "cpuStatus": cpu_status,
    }
