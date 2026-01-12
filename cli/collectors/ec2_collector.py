"""
EC2 Instance Data Collector.

Collects EC2 instance data across all regions, including:
- Instance details (ID, type, state, launch time)
- Tags (Name, Environment, Team, etc.)
- VPC and networking configuration
- Reserved Instance associations
"""

from datetime import datetime
from typing import Optional, Any

from ..utils.aws_client import AWSClient, get_default_client, paginate
from ..utils.logger import get_logger, create_progress, console

logger = get_logger(__name__)


class EC2Collector:
    """
    Collect EC2 instance data from AWS.
    
    Supports multi-region collection, tag filtering, and
    handles pagination and rate limiting automatically.
    """
    
    def __init__(self, aws_client: Optional[AWSClient] = None):
        """
        Initialize EC2 collector.
        
        Args:
            aws_client: AWS client instance (uses default if not specified)
        """
        self.aws_client = aws_client or get_default_client()
    
    def collect_all_instances(
        self,
        regions: Optional[list[str]] = None,
        include_tags: Optional[list[tuple[str, str]]] = None,
        exclude_tags: Optional[list[tuple[str, str]]] = None,
        states: Optional[list[str]] = None,
        show_progress: bool = True,
    ) -> list[dict]:
        """
        Collect all EC2 instances across regions.
        
        Args:
            regions: List of regions to scan (None for all regions)
            include_tags: Only include instances with these tags
            exclude_tags: Exclude instances with these tags
            states: Instance states to include (default: running, stopped)
            show_progress: Show progress bar during collection
        
        Returns:
            List of instance dictionaries with normalized data
        """
        if regions is None:
            regions = self.aws_client.get_all_regions()
        
        if states is None:
            states = ["running", "stopped"]
        
        all_instances = []
        
        if show_progress:
            progress = create_progress()
            with progress:
                task = progress.add_task(
                    "[cyan]Collecting EC2 instances...",
                    total=len(regions)
                )
                for region in regions:
                    instances = self._collect_region_instances(
                        region, include_tags, exclude_tags, states
                    )
                    all_instances.extend(instances)
                    progress.update(task, advance=1)
        else:
            for region in regions:
                instances = self._collect_region_instances(
                    region, include_tags, exclude_tags, states
                )
                all_instances.extend(instances)
        
        logger.info(f"Collected {len(all_instances)} instances from {len(regions)} regions")
        return all_instances
    
    def _collect_region_instances(
        self,
        region: str,
        include_tags: Optional[list[tuple[str, str]]] = None,
        exclude_tags: Optional[list[tuple[str, str]]] = None,
        states: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Collect instances from a single region.
        
        Args:
            region: AWS region
            include_tags: Tag filters to include
            exclude_tags: Tag filters to exclude
            states: Instance states to include
        
        Returns:
            List of instance dictionaries
        """
        try:
            ec2 = self.aws_client.get_ec2_client(region)
            
            # Build filters
            filters = []
            if states:
                filters.append({
                    "Name": "instance-state-name",
                    "Values": states,
                })
            
            # Add include tag filters
            if include_tags:
                for key, value in include_tags:
                    filters.append({
                        "Name": f"tag:{key}",
                        "Values": [value],
                    })
            
            # Get instances with pagination
            instances = paginate(
                ec2, "describe_instances", "Reservations",
                Filters=filters if filters else None,
            )
            
            # Process and normalize instances
            result = []
            for reservation in instances:
                for instance in reservation.get("Instances", []):
                    normalized = self._normalize_instance(instance, region)
                    
                    # Apply exclude filters
                    if exclude_tags and self._matches_tags(normalized["tags"], exclude_tags):
                        continue
                    
                    result.append(normalized)
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to collect from {region}: {e}")
            return []
    
    def _normalize_instance(self, instance: dict, region: str) -> dict:
        """
        Normalize AWS instance data to a consistent format.
        
        Args:
            instance: Raw AWS instance data
            region: AWS region
        
        Returns:
            Normalized instance dictionary
        """
        # Extract tags into a dictionary
        tags = {}
        for tag in instance.get("Tags", []):
            tags[tag["Key"]] = tag["Value"]
        
        # Get instance name from tags
        name = tags.get("Name", "")
        
        # Calculate running time
        launch_time = instance.get("LaunchTime")
        running_days = 0
        running_hours = 0
        if launch_time:
            delta = datetime.now(launch_time.tzinfo) - launch_time
            running_days = delta.days
            running_hours = int(delta.total_seconds() / 3600)
        
        # Extract EBS volume info from block device mappings
        volumes = []
        for bdm in instance.get("BlockDeviceMappings", []):
            ebs = bdm.get("Ebs", {})
            if ebs.get("VolumeId"):
                volumes.append({
                    "volume_id": ebs.get("VolumeId"),
                    "device_name": bdm.get("DeviceName"),
                    "delete_on_termination": ebs.get("DeleteOnTermination", False),
                    "attach_time": ebs.get("AttachTime").isoformat() if ebs.get("AttachTime") else None,
                })
        
        return {
            "instance_id": instance.get("InstanceId"),
            "instance_type": instance.get("InstanceType"),
            "state": instance.get("State", {}).get("Name", "unknown"),
            "name": name,
            "region": region,
            "availability_zone": instance.get("Placement", {}).get("AvailabilityZone"),
            "launch_time": launch_time.isoformat() if launch_time else None,
            "running_days": running_days,
            "running_hours": running_hours,
            "vpc_id": instance.get("VpcId"),
            "subnet_id": instance.get("SubnetId"),
            "private_ip": instance.get("PrivateIpAddress"),
            "public_ip": instance.get("PublicIpAddress"),
            "security_groups": [
                sg.get("GroupId") for sg in instance.get("SecurityGroups", [])
            ],
            "iam_instance_profile": instance.get("IamInstanceProfile", {}).get("Arn"),
            "platform": instance.get("Platform", "linux"),
            "architecture": instance.get("Architecture"),
            "monitoring_enabled": instance.get("Monitoring", {}).get("State") == "enabled",
            "root_device_type": instance.get("RootDeviceType"),
            "root_device_name": instance.get("RootDeviceName"),
            "ebs_volumes": volumes,
            "tags": tags,
            # Placeholders for enrichment
            "monthly_cost": 0.0,
            "metrics": {},
            "storage": {},
        }
    
    def _matches_tags(
        self,
        instance_tags: dict[str, str],
        filter_tags: list[tuple[str, str]]
    ) -> bool:
        """
        Check if instance tags match any filter tags.
        
        Args:
            instance_tags: Instance tag dictionary
            filter_tags: List of (key, value) tuples to match
        
        Returns:
            True if any filter matches
        """
        for key, value in filter_tags:
            if key in instance_tags:
                tag_value = instance_tags[key].lower()
                filter_value = value.lower()
                # Support wildcard matching
                if filter_value == "*" or filter_value in tag_value:
                    return True
        return False
    
    def collect_by_region(self, region: str) -> list[dict]:
        """
        Collect instances from a specific region.
        
        Args:
            region: AWS region
        
        Returns:
            List of instances in the region
        """
        return self._collect_region_instances(region)
    
    def collect_by_tag(self, tag_key: str, tag_value: str) -> list[dict]:
        """
        Collect instances matching a specific tag.
        
        Args:
            tag_key: Tag key to match
            tag_value: Tag value to match
        
        Returns:
            List of matching instances
        """
        return self.collect_all_instances(
            include_tags=[(tag_key, tag_value)],
            show_progress=False,
        )
    
    def get_instance_by_id(self, instance_id: str, region: str) -> Optional[dict]:
        """
        Get a specific instance by ID.
        
        Args:
            instance_id: EC2 instance ID
            region: AWS region
        
        Returns:
            Instance dictionary or None if not found
        """
        try:
            ec2 = self.aws_client.get_ec2_client(region)
            response = ec2.describe_instances(InstanceIds=[instance_id])
            
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    return self._normalize_instance(instance, region)
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get instance {instance_id}: {e}")
            return None
    
    def get_reserved_instances(self, region: Optional[str] = None) -> list[dict]:
        """
        Get active Reserved Instances.
        
        Args:
            region: AWS region (None for current region)
        
        Returns:
            List of active reserved instances
        """
        try:
            ec2 = self.aws_client.get_ec2_client(region)
            response = ec2.describe_reserved_instances(
                Filters=[{"Name": "state", "Values": ["active"]}]
            )
            
            return [
                {
                    "reserved_instance_id": ri.get("ReservedInstancesId"),
                    "instance_type": ri.get("InstanceType"),
                    "instance_count": ri.get("InstanceCount"),
                    "availability_zone": ri.get("AvailabilityZone"),
                    "duration": ri.get("Duration"),
                    "start": ri.get("Start").isoformat() if ri.get("Start") else None,
                    "end": ri.get("End").isoformat() if ri.get("End") else None,
                    "offering_type": ri.get("OfferingType"),
                    "state": ri.get("State"),
                }
                for ri in response.get("ReservedInstances", [])
            ]
            
        except Exception as e:
            logger.warning(f"Failed to get reserved instances: {e}")
            return []
    
    def get_volume_details(self, volume_ids: list[str], region: str) -> list[dict]:
        """
        Get detailed information for EBS volumes.
        
        Args:
            volume_ids: List of EBS volume IDs
            region: AWS region
        
        Returns:
            List of volume details with type, size, IOPS, and cost
        """
        if not volume_ids:
            return []
        
        # EBS pricing per GB-month (approximate, us-east-1)
        EBS_PRICING = {
            "gp2": 0.10,      # General Purpose SSD
            "gp3": 0.08,      # General Purpose SSD (newer)
            "io1": 0.125,     # Provisioned IOPS SSD
            "io2": 0.125,     # Provisioned IOPS SSD
            "st1": 0.045,     # Throughput Optimized HDD
            "sc1": 0.025,     # Cold HDD
            "standard": 0.05, # Magnetic
        }
        
        try:
            ec2 = self.aws_client.get_ec2_client(region)
            response = ec2.describe_volumes(VolumeIds=volume_ids)
            
            volumes = []
            for vol in response.get("Volumes", []):
                vol_type = vol.get("VolumeType", "gp2")
                size_gb = vol.get("Size", 0)
                iops = vol.get("Iops", 0)
                throughput = vol.get("Throughput", 0)  # For gp3
                
                # Calculate monthly cost
                price_per_gb = EBS_PRICING.get(vol_type, 0.10)
                monthly_cost = size_gb * price_per_gb
                
                # Add IOPS cost for io1/io2 ($0.065 per IOPS-month)
                if vol_type in ["io1", "io2"] and iops > 0:
                    monthly_cost += iops * 0.065
                
                volumes.append({
                    "volume_id": vol.get("VolumeId"),
                    "volume_type": vol_type,
                    "size_gb": size_gb,
                    "iops": iops,
                    "throughput": throughput,
                    "state": vol.get("State"),
                    "encrypted": vol.get("Encrypted", False),
                    "monthly_cost": round(monthly_cost, 2),
                })
            
            return volumes
            
        except Exception as e:
            logger.warning(f"Failed to get volume details: {e}")
            return []
