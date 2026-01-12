"""
Input validation utilities for Cloud Cost Slayer.

Validates AWS regions, instance types, tags, and configuration options.
"""

import re
from typing import Optional

# Valid AWS regions pattern
AWS_REGION_PATTERN = re.compile(
    r"^(us|eu|ap|sa|ca|me|af)-(north|south|east|west|central|northeast|southeast|northwest|southwest)-[1-9]$"
)

# Valid EC2 instance type pattern
INSTANCE_TYPE_PATTERN = re.compile(
    r"^[a-z][0-9][a-z]?\.(nano|micro|small|medium|x?large|[0-9]+xlarge|metal)$"
)

# Common instance type prefixes
INSTANCE_FAMILIES = [
    "t2", "t3", "t3a", "t4g",
    "m4", "m5", "m5a", "m5n", "m5zn", "m6i", "m6a", "m6g", "m7i", "m7g",
    "c4", "c5", "c5a", "c5n", "c6i", "c6a", "c6g", "c7i", "c7g",
    "r4", "r5", "r5a", "r5n", "r6i", "r6a", "r6g", "r7i", "r7g",
    "x1", "x1e", "x2idn", "x2iedn", "x2iezn",
    "i3", "i3en", "i4i",
    "d2", "d3", "d3en",
    "h1", "hs1",
    "z1d",
    "p2", "p3", "p4d", "p5",
    "g3", "g4dn", "g4ad", "g5",
    "inf1", "inf2",
    "trn1",
    "f1",
    "mac1", "mac2",
    "hpc6a", "hpc7g",
]


class ValidationError(Exception):
    """Exception for validation errors with helpful messages."""
    pass


def validate_region(region: str) -> bool:
    """
    Validate an AWS region code.
    
    Args:
        region: AWS region code (e.g., 'us-east-1')
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If region is invalid
    """
    if not region:
        raise ValidationError("Region cannot be empty")
    
    if not AWS_REGION_PATTERN.match(region):
        raise ValidationError(
            f"Invalid AWS region: '{region}'. "
            f"Expected format like 'us-east-1', 'eu-west-2', 'ap-southeast-1'"
        )
    
    return True


def validate_instance_type(instance_type: str) -> bool:
    """
    Validate an EC2 instance type.
    
    Args:
        instance_type: Instance type (e.g., 't3.large')
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If instance type is invalid
    """
    if not instance_type:
        raise ValidationError("Instance type cannot be empty")
    
    # Check pattern
    if not INSTANCE_TYPE_PATTERN.match(instance_type):
        # Check if it might be valid but not matching our pattern
        parts = instance_type.split(".")
        if len(parts) != 2:
            raise ValidationError(
                f"Invalid instance type: '{instance_type}'. "
                f"Expected format like 't3.large', 'm5.xlarge'"
            )
        
        family = parts[0]
        if not any(family.startswith(f) for f in INSTANCE_FAMILIES):
            raise ValidationError(
                f"Unknown instance family: '{family}' in '{instance_type}'"
            )
    
    return True


def validate_tag_filter(tag_filter: str) -> tuple[str, str]:
    """
    Validate and parse a tag filter string.
    
    Args:
        tag_filter: Tag filter in format 'Key=Value' or 'Key:Value'
    
    Returns:
        Tuple of (key, value)
    
    Raises:
        ValidationError: If tag filter is invalid
    """
    if not tag_filter:
        raise ValidationError("Tag filter cannot be empty")
    
    # Support both = and : as separators
    if "=" in tag_filter:
        parts = tag_filter.split("=", 1)
    elif ":" in tag_filter:
        parts = tag_filter.split(":", 1)
    else:
        raise ValidationError(
            f"Invalid tag filter: '{tag_filter}'. "
            f"Expected format 'Key=Value' or 'Key:Value'"
        )
    
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValidationError(
            f"Invalid tag filter: '{tag_filter}'. "
            f"Both key and value are required"
        )
    
    return parts[0].strip(), parts[1].strip()


def validate_confidence_level(level: str) -> bool:
    """
    Validate a confidence level.
    
    Args:
        level: Confidence level ('high', 'medium', 'low')
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If level is invalid
    """
    valid_levels = ["high", "medium", "low"]
    if level.lower() not in valid_levels:
        raise ValidationError(
            f"Invalid confidence level: '{level}'. "
            f"Must be one of: {', '.join(valid_levels)}"
        )
    return True


def validate_output_format(format_type: str) -> bool:
    """
    Validate an output format type.
    
    Args:
        format_type: Output format ('json', 'table', 'yaml', 'html', 'csv')
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If format is invalid
    """
    valid_formats = ["json", "table", "yaml", "html", "csv", "markdown"]
    if format_type.lower() not in valid_formats:
        raise ValidationError(
            f"Invalid output format: '{format_type}'. "
            f"Must be one of: {', '.join(valid_formats)}"
        )
    return True


def validate_days(days: int) -> bool:
    """
    Validate lookback days parameter.
    
    Args:
        days: Number of days to look back
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If days is invalid
    """
    if days < 1:
        raise ValidationError("Days must be at least 1")
    if days > 365:
        raise ValidationError("Days cannot exceed 365")
    return True


def parse_regions(regions_input: Optional[str]) -> list[str]:
    """
    Parse a comma-separated list of regions.
    
    Args:
        regions_input: Comma-separated regions or None for all
    
    Returns:
        List of validated region codes
    """
    if not regions_input:
        return []
    
    regions = [r.strip() for r in regions_input.split(",") if r.strip()]
    
    for region in regions:
        validate_region(region)
    
    return regions


def parse_tag_filters(filters_input: Optional[str]) -> list[tuple[str, str]]:
    """
    Parse a comma-separated list of tag filters.
    
    Args:
        filters_input: Comma-separated tag filters
    
    Returns:
        List of (key, value) tuples
    """
    if not filters_input:
        return []
    
    filters = []
    for tag_filter in filters_input.split(","):
        if tag_filter.strip():
            filters.append(validate_tag_filter(tag_filter.strip()))
    
    return filters


def is_production_instance(tags: dict[str, str]) -> bool:
    """
    Check if instance tags indicate production environment.
    
    Args:
        tags: Dictionary of instance tags
    
    Returns:
        True if instance appears to be production
    """
    production_indicators = [
        ("Environment", ["production", "prod", "prd"]),
        ("Env", ["production", "prod", "prd"]),
        ("Stage", ["production", "prod", "prd"]),
        ("Name", ["prod", "production"]),  # Partial match
    ]
    
    for tag_key, values in production_indicators:
        if tag_key in tags:
            tag_value = tags[tag_key].lower()
            for prod_value in values:
                if prod_value in tag_value:
                    return True
    
    return False


def is_database_instance(tags: dict[str, str], instance_type: str) -> bool:
    """
    Check if instance appears to be a database.
    
    Args:
        tags: Dictionary of instance tags
        instance_type: EC2 instance type
    
    Returns:
        True if instance appears to be a database
    """
    # Check tags
    db_indicators = ["database", "db", "mysql", "postgres", "mongo", "redis", "sql"]
    for value in tags.values():
        if any(indicator in value.lower() for indicator in db_indicators):
            return True
    
    # Memory-optimized instances are often databases
    if instance_type.startswith(("r", "x")):
        return True
    
    return False
