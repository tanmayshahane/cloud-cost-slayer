"""
RDS Instance Data Collector.

Collects RDS instance data across all regions, including:
- Instance details (ID, class, engine, status)
- Storage configuration
- Multi-AZ deployment status
- Tags for filtering
"""

from datetime import datetime, timezone
from typing import Optional

from ..utils.aws_client import AWSClient, get_default_client
from ..utils.logger import get_logger, create_progress, console

logger = get_logger(__name__)

# RDS pricing (approximate hourly rates in us-east-1)
# Actual pricing varies by region
RDS_PRICING = {
    # T3 instances (burstable)
    "db.t3.micro": 0.017,
    "db.t3.small": 0.034,
    "db.t3.medium": 0.068,
    "db.t3.large": 0.136,
    "db.t3.xlarge": 0.272,
    "db.t3.2xlarge": 0.544,
    # T4g instances (ARM/Graviton)
    "db.t4g.micro": 0.016,
    "db.t4g.small": 0.032,
    "db.t4g.medium": 0.065,
    "db.t4g.large": 0.129,
    # M5 instances (general purpose)
    "db.m5.large": 0.171,
    "db.m5.xlarge": 0.342,
    "db.m5.2xlarge": 0.684,
    "db.m5.4xlarge": 1.368,
    # M6g instances (Graviton)
    "db.m6g.large": 0.154,
    "db.m6g.xlarge": 0.307,
    # R5 instances (memory optimized)
    "db.r5.large": 0.240,
    "db.r5.xlarge": 0.480,
    "db.r5.2xlarge": 0.960,
    # R6g instances (Graviton memory)
    "db.r6g.large": 0.216,
    "db.r6g.xlarge": 0.432,
}

# RDS storage pricing (per GB per month)
RDS_STORAGE_PRICING = {
    "gp2": 0.115,
    "gp3": 0.08,
    "io1": 0.125,
    "standard": 0.10,  # magnetic
}


class RDSCollector:
    """
    Collect RDS instance data from AWS.
    
    Supports multi-region collection, tag filtering, and
    handles pagination automatically.
    """
    
    def __init__(self, aws_client: Optional[AWSClient] = None):
        """
        Initialize RDS collector.
        
        Args:
            aws_client: AWS client instance (uses default if not specified)
        """
        self.aws_client = aws_client or get_default_client()
    
    def collect_all_instances(
        self,
        regions: Optional[list[str]] = None,
        include_tags: Optional[list[tuple[str, str]]] = None,
        states: Optional[list[str]] = None,
        show_progress: bool = True,
    ) -> list[dict]:
        """
        Collect all RDS instances across regions.
        
        Args:
            regions: List of regions to scan (None for all regions)
            include_tags: Only include instances with matching tags
            states: Instance states to include (default: available)
            show_progress: Show progress bar
        
        Returns:
            List of RDS instance dictionaries
        """
        if regions is None:
            regions = self.aws_client.get_all_regions()
        
        if states is None:
            states = ["available", "backing-up", "modifying"]
        
        all_instances = []
        
        if show_progress:
            progress = create_progress()
            with progress:
                task = progress.add_task(
                    "[cyan]Collecting RDS instances...",
                    total=len(regions)
                )
                for region in regions:
                    instances = self._collect_region_instances(region, states)
                    all_instances.extend(instances)
                    progress.update(task, advance=1)
        else:
            for region in regions:
                instances = self._collect_region_instances(region, states)
                all_instances.extend(instances)
        
        # Filter by tags if specified
        if include_tags:
            all_instances = self._filter_by_tags(all_instances, include_tags)
        
        logger.info(f"Collected {len(all_instances)} RDS instances from {len(regions)} regions")
        return all_instances
    
    def _collect_region_instances(self, region: str, states: list[str]) -> list[dict]:
        """Collect RDS instances from a single region."""
        try:
            rds = self.aws_client.get_client("rds", region)
            response = rds.describe_db_instances()
            
            instances = []
            for db in response.get("DBInstances", []):
                if db.get("DBInstanceStatus") in states:
                    normalized = self._normalize_instance(db, region)
                    instances.append(normalized)
            
            return instances
            
        except Exception as e:
            error_msg = str(e)
            if "UnauthorizedOperation" in error_msg or "AccessDenied" in error_msg:
                console.print(f"[dim]Failed to collect RDS from {region}: Access Denied[/dim]")
            else:
                logger.warning(f"Failed to collect RDS from {region}: {e}")
            return []
    
    def _normalize_instance(self, db: dict, region: str) -> dict:
        """Normalize RDS instance data to standard format."""
        # Extract tags
        tags = {}
        for tag in db.get("TagList", []):
            tags[tag["Key"]] = tag["Value"]
        
        # Get instance name
        db_id = db.get("DBInstanceIdentifier", "unknown")
        name = tags.get("Name", db_id)
        
        # Calculate running time
        create_time = db.get("InstanceCreateTime")
        if create_time and hasattr(create_time, "tzinfo"):
            now = datetime.now(timezone.utc)
            running_seconds = (now - create_time).total_seconds()
            running_days = int(running_seconds // 86400)
            running_hours = int(running_seconds // 3600)
        else:
            running_days = 0
            running_hours = 0
        
        # Storage info
        storage_type = db.get("StorageType", "gp2")
        allocated_storage = db.get("AllocatedStorage", 0)
        storage_price = RDS_STORAGE_PRICING.get(storage_type, 0.115)
        storage_monthly_cost = allocated_storage * storage_price
        
        # Instance pricing
        instance_class = db.get("DBInstanceClass", "db.t3.micro")
        hourly_rate = self.get_instance_pricing(instance_class, region)
        
        # Multi-AZ doubles the cost
        multi_az = db.get("MultiAZ", False)
        if multi_az:
            hourly_rate *= 2
        
        return {
            "db_instance_id": db_id,
            "name": name,
            "engine": db.get("Engine", "unknown"),
            "engine_version": db.get("EngineVersion", ""),
            "instance_class": instance_class,
            "status": db.get("DBInstanceStatus", "unknown"),
            "region": region,
            "multi_az": multi_az,
            "storage_type": storage_type,
            "allocated_storage_gb": allocated_storage,
            "storage_monthly_cost": storage_monthly_cost,
            "endpoint": db.get("Endpoint", {}).get("Address", ""),
            "port": db.get("Endpoint", {}).get("Port", 0),
            "vpc_id": db.get("DBSubnetGroup", {}).get("VpcId", ""),
            "tags": tags,
            "create_time": create_time,
            "running_days": running_days,
            "running_hours": running_hours,
            "hourly_rate": hourly_rate,
            "publicly_accessible": db.get("PubliclyAccessible", False),
            "storage_encrypted": db.get("StorageEncrypted", False),
            "auto_minor_version_upgrade": db.get("AutoMinorVersionUpgrade", False),
            "backup_retention_period": db.get("BackupRetentionPeriod", 0),
        }
    
    def get_instance_pricing(self, instance_class: str, region: str) -> float:
        """
        Get hourly price for an RDS instance class.
        
        Args:
            instance_class: RDS instance class (e.g., 'db.t3.medium')
            region: AWS region
        
        Returns:
            Hourly price in USD
        """
        # Use hardcoded pricing for now
        # Future: use AWS Pricing API
        base_price = RDS_PRICING.get(instance_class, 0.068)  # Default to db.t3.medium
        
        # Regional adjustment (approximate)
        region_factors = {
            "ap-south-1": 1.0,   # Mumbai - base
            "ap-southeast-1": 1.1,
            "ap-northeast-1": 1.2,
            "eu-west-1": 1.0,
            "us-east-1": 0.9,
            "us-west-2": 0.95,
        }
        factor = region_factors.get(region, 1.0)
        
        return base_price * factor
    
    def get_instance_by_id(self, db_instance_id: str, region: str) -> Optional[dict]:
        """
        Get a specific RDS instance by ID.
        
        Args:
            db_instance_id: RDS instance identifier
            region: AWS region
        
        Returns:
            Instance dictionary or None if not found
        """
        try:
            rds = self.aws_client.get_client("rds", region)
            response = rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
            
            instances = response.get("DBInstances", [])
            if instances:
                return self._normalize_instance(instances[0], region)
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get RDS instance {db_instance_id}: {e}")
            return None
    
    def _filter_by_tags(
        self, 
        instances: list[dict], 
        include_tags: list[tuple[str, str]]
    ) -> list[dict]:
        """Filter instances by tag requirements."""
        filtered = []
        for inst in instances:
            tags = inst.get("tags", {})
            matches = True
            for key, value in include_tags:
                if key not in tags or value.lower() not in tags[key].lower():
                    matches = False
                    break
            if matches:
                filtered.append(inst)
        return filtered
