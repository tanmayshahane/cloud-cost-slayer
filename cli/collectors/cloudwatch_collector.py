"""
CloudWatch Metrics Collector.

Collects CloudWatch metrics for EC2 instances:
- CPU Utilization (average, max, percentiles)
- Network I/O
- Disk I/O
- Status checks
"""

from datetime import datetime, timedelta
from typing import Optional
import statistics

from ..utils.aws_client import AWSClient, get_default_client
from ..utils.logger import get_logger, create_progress, console

logger = get_logger(__name__)

# Default metric period (5 minutes)
DEFAULT_PERIOD = 300

# Metrics to collect for each instance
EC2_METRICS = [
    {
        "name": "CPUUtilization",
        "namespace": "AWS/EC2",
        "unit": "Percent",
        "statistics": ["Average", "Maximum"],
    },
    {
        "name": "NetworkIn",
        "namespace": "AWS/EC2",
        "unit": "Bytes",
        "statistics": ["Sum", "Average"],
    },
    {
        "name": "NetworkOut",
        "namespace": "AWS/EC2",
        "unit": "Bytes",
        "statistics": ["Sum", "Average"],
    },
    {
        "name": "DiskReadBytes",
        "namespace": "AWS/EC2",
        "unit": "Bytes",
        "statistics": ["Sum"],
    },
    {
        "name": "DiskWriteBytes",
        "namespace": "AWS/EC2",
        "unit": "Bytes",
        "statistics": ["Sum"],
    },
    {
        "name": "StatusCheckFailed",
        "namespace": "AWS/EC2",
        "unit": "Count",
        "statistics": ["Sum"],
    },
]


class CloudWatchCollector:
    """
    Collect CloudWatch metrics for EC2 instances.
    
    Provides CPU, network, disk, and status metrics with
    aggregations including averages, maximums, and percentiles.
    """
    
    def __init__(self, aws_client: Optional[AWSClient] = None):
        """
        Initialize CloudWatch collector.
        
        Args:
            aws_client: AWS client instance
        """
        self.aws_client = aws_client or get_default_client()
    
    def collect_metrics(
        self,
        instance_id: str,
        region: str,
        days: int = 30,
        period: int = DEFAULT_PERIOD,
    ) -> dict:
        """
        Collect all metrics for a single instance.
        
        Args:
            instance_id: EC2 instance ID
            region: AWS region
            days: Number of days to look back
            period: Metric period in seconds
        
        Returns:
            Dictionary of metrics with statistics
        """
        cw = self.aws_client.get_cloudwatch_client(region)
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        # Calculate period to stay within CloudWatch 1440 datapoint limit
        # For 30 days, we need period >= 1800 seconds (30 min) to get ~1440 datapoints
        # For better accuracy with longer ranges, use hourly (3600s) for > 5 days
        if days > 5:
            period = 3600  # 1 hour
        elif days > 1:
            period = 900   # 15 minutes
        # else use the default period (5 min)
        
        metrics = {}
        
        for metric_config in EC2_METRICS:
            try:
                response = cw.get_metric_statistics(
                    Namespace=metric_config["namespace"],
                    MetricName=metric_config["name"],
                    Dimensions=[
                        {"Name": "InstanceId", "Value": instance_id}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=period,
                    Statistics=metric_config["statistics"],
                    Unit=metric_config["unit"],
                )
                
                datapoints = response.get("Datapoints", [])
                logger.debug(f"{metric_config['name']}: received {len(datapoints)} datapoints")
                metrics[metric_config["name"]] = self._process_datapoints(
                    datapoints,
                    metric_config["statistics"],
                )
                
            except Exception as e:
                # Print errors for visibility
                error_msg = str(e)
                if "AccessDenied" in error_msg or "not authorized" in error_msg:
                    console.print(f"[red]CloudWatch Error ({metric_config['name']}): {e}[/red]")
                metrics[metric_config["name"]] = self._empty_metric()
        
        # Calculate additional percentiles for CPU
        if "CPUUtilization" in metrics and metrics["CPUUtilization"].get("raw_values"):
            raw = metrics["CPUUtilization"]["raw_values"]
            if len(raw) > 0:
                sorted_values = sorted(raw)
                metrics["CPUUtilization"]["p50"] = self._percentile(sorted_values, 50)
                metrics["CPUUtilization"]["p95"] = self._percentile(sorted_values, 95)
                metrics["CPUUtilization"]["p99"] = self._percentile(sorted_values, 99)
        
        return metrics
    
    def collect_volume_metrics(
        self,
        volume_id: str,
        region: str,
        days: int = 7,
    ) -> dict:
        """
        Collect CloudWatch metrics for an EBS volume.
        
        Args:
            volume_id: EBS volume ID
            region: AWS region
            days: Number of days to look back
        
        Returns:
            Dictionary with IOPS and throughput metrics
        """
        cw = self.aws_client.get_cloudwatch_client(region)
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        # Use hourly period for volume metrics
        period = 3600
        
        volume_metrics = {
            "volume_id": volume_id,
            "read_iops_avg": 0,
            "write_iops_avg": 0,
            "read_bytes_total": 0,
            "write_bytes_total": 0,
            "iops_max": 0,
        }
        
        # EBS volume metrics to collect
        ebs_metrics = [
            ("VolumeReadOps", "read_ops"),
            ("VolumeWriteOps", "write_ops"),
            ("VolumeReadBytes", "read_bytes"),
            ("VolumeWriteBytes", "write_bytes"),
        ]
        
        for metric_name, key in ebs_metrics:
            try:
                response = cw.get_metric_statistics(
                    Namespace="AWS/EBS",
                    MetricName=metric_name,
                    Dimensions=[
                        {"Name": "VolumeId", "Value": volume_id}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=period,
                    Statistics=["Sum", "Average", "Maximum"],
                )
                
                datapoints = response.get("Datapoints", [])
                if datapoints:
                    if "Ops" in metric_name:
                        # Calculate IOPS (ops per second)
                        avg_ops = sum(d.get("Sum", 0) for d in datapoints) / len(datapoints)
                        iops_avg = avg_ops / period  # Convert to ops/second
                        max_iops = max(d.get("Sum", 0) / period for d in datapoints)
                        volume_metrics[f"{key.replace('ops', 'iops')}_avg"] = round(iops_avg, 2)
                        if max_iops > volume_metrics["iops_max"]:
                            volume_metrics["iops_max"] = round(max_iops, 2)
                    else:
                        # Bytes metrics
                        total_bytes = sum(d.get("Sum", 0) for d in datapoints)
                        volume_metrics[f"{key}_total"] = total_bytes
                        
            except Exception as e:
                logger.debug(f"Failed to get {metric_name} for {volume_id}: {e}")
        
        return volume_metrics
    
    def collect_rds_metrics(
        self,
        db_instance_id: str,
        region: str,
        days: int = 7,
    ) -> dict:
        """
        Collect CloudWatch metrics for an RDS instance.
        
        Args:
            db_instance_id: RDS instance identifier
            region: AWS region
            days: Number of days to look back
        
        Returns:
            Dictionary with RDS metrics
        """
        cw = self.aws_client.get_cloudwatch_client(region)
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        # Use hourly period for longer ranges
        period = 3600 if days > 5 else 300
        
        rds_metrics = {
            "cpu_avg": 0,
            "cpu_max": 0,
            "memory_free_avg": 0,
            "memory_free_min": 0,
            "connections_avg": 0,
            "connections_max": 0,
            "read_iops_avg": 0,
            "write_iops_avg": 0,
            "storage_free_gb": 0,
            "datapoint_count": 0,
        }
        
        # Define RDS-specific metrics
        rds_metric_configs = [
            {"name": "CPUUtilization", "stat": "Average", "key": "cpu_avg"},
            {"name": "CPUUtilization", "stat": "Maximum", "key": "cpu_max"},
            {"name": "FreeableMemory", "stat": "Average", "key": "memory_free_avg"},
            {"name": "FreeableMemory", "stat": "Minimum", "key": "memory_free_min"},
            {"name": "DatabaseConnections", "stat": "Average", "key": "connections_avg"},
            {"name": "DatabaseConnections", "stat": "Maximum", "key": "connections_max"},
            {"name": "ReadIOPS", "stat": "Average", "key": "read_iops_avg"},
            {"name": "WriteIOPS", "stat": "Average", "key": "write_iops_avg"},
            {"name": "FreeStorageSpace", "stat": "Average", "key": "storage_free_gb"},
        ]
        
        for config in rds_metric_configs:
            try:
                response = cw.get_metric_statistics(
                    Namespace="AWS/RDS",
                    MetricName=config["name"],
                    Dimensions=[
                        {"Name": "DBInstanceIdentifier", "Value": db_instance_id}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=period,
                    Statistics=[config["stat"]],
                )
                
                datapoints = response.get("Datapoints", [])
                if datapoints:
                    values = [dp[config["stat"]] for dp in datapoints]
                    
                    # Store the metric
                    if config["stat"] == "Average":
                        rds_metrics[config["key"]] = sum(values) / len(values)
                    elif config["stat"] == "Maximum":
                        rds_metrics[config["key"]] = max(values)
                    elif config["stat"] == "Minimum":
                        rds_metrics[config["key"]] = min(values)
                    
                    # Track datapoint count from CPU metric
                    if config["name"] == "CPUUtilization" and config["stat"] == "Average":
                        rds_metrics["datapoint_count"] = len(datapoints)
                        
            except Exception as e:
                logger.debug(f"Failed to get {config['name']} for RDS {db_instance_id}: {e}")
        
        # Convert memory from bytes to GB
        if rds_metrics["memory_free_avg"] > 0:
            rds_metrics["memory_free_avg"] = rds_metrics["memory_free_avg"] / (1024 ** 3)
            rds_metrics["memory_free_min"] = rds_metrics["memory_free_min"] / (1024 ** 3)
        
        # Convert storage from bytes to GB
        if rds_metrics["storage_free_gb"] > 0:
            rds_metrics["storage_free_gb"] = rds_metrics["storage_free_gb"] / (1024 ** 3)
        
        return rds_metrics
    
    def collect_batch_rds_metrics(
        self,
        instances: list[dict],
        days: int = 7,
        show_progress: bool = True,
    ) -> dict[str, dict]:
        """
        Collect metrics for multiple RDS instances.
        
        Args:
            instances: List of RDS instance dictionaries with 'db_instance_id' and 'region'
            days: Number of days to look back
            show_progress: Show progress bar
        
        Returns:
            Dictionary mapping db_instance_id to metrics
        """
        results = {}
        
        if show_progress:
            progress = create_progress()
            with progress:
                task = progress.add_task(
                    "[cyan]Collecting RDS metrics...",
                    total=len(instances)
                )
                for instance in instances:
                    db_id = instance["db_instance_id"]
                    region = instance["region"]
                    results[db_id] = self.collect_rds_metrics(db_id, region, days)
                    progress.update(task, advance=1)
        else:
            for instance in instances:
                db_id = instance["db_instance_id"]
                region = instance["region"]
                results[db_id] = self.collect_rds_metrics(db_id, region, days)
        
        logger.info(f"Collected metrics for {len(results)} RDS instances")
        return results
    
    def collect_batch_metrics(
        self,
        instances: list[dict],
        days: int = 30,
        show_progress: bool = True,
    ) -> dict[str, dict]:
        """
        Collect metrics for multiple instances.
        
        Args:
            instances: List of instance dictionaries with 'instance_id' and 'region'
            days: Number of days to look back
            show_progress: Show progress bar
        
        Returns:
            Dictionary mapping instance_id to metrics
        """
        results = {}
        
        if show_progress:
            progress = create_progress()
            with progress:
                task = progress.add_task(
                    "[cyan]Collecting CloudWatch metrics...",
                    total=len(instances)
                )
                for instance in instances:
                    instance_id = instance["instance_id"]
                    region = instance["region"]
                    results[instance_id] = self.collect_metrics(
                        instance_id, region, days
                    )
                    progress.update(task, advance=1)
        else:
            for instance in instances:
                instance_id = instance["instance_id"]
                region = instance["region"]
                results[instance_id] = self.collect_metrics(
                    instance_id, region, days
                )
        
        logger.info(f"Collected metrics for {len(results)} instances")
        return results
    
    def _process_datapoints(
        self,
        datapoints: list[dict],
        stats: list[str],
    ) -> dict:
        """
        Process raw CloudWatch datapoints into summary statistics.
        
        Args:
            datapoints: Raw CloudWatch datapoints
            stats: Statistics to extract
        
        Returns:
            Processed metric dictionary
        """
        if not datapoints:
            return self._empty_metric()
        
        # Sort by timestamp
        sorted_points = sorted(datapoints, key=lambda x: x["Timestamp"])
        
        result = {
            "datapoint_count": len(sorted_points),
            "start_time": sorted_points[0]["Timestamp"].isoformat(),
            "end_time": sorted_points[-1]["Timestamp"].isoformat(),
        }
        
        # Extract each statistic
        for stat in stats:
            values = [p.get(stat, 0) for p in sorted_points if stat in p]
            if values:
                result[f"{stat.lower()}"] = round(statistics.mean(values), 2)
                result[f"{stat.lower()}_max"] = round(max(values), 2)
                result[f"{stat.lower()}_min"] = round(min(values), 2)
        
        # Store raw values for percentile calculation (CPU only)
        if "Average" in stats:
            result["raw_values"] = [p.get("Average", 0) for p in sorted_points]
        
        return result
    
    def _empty_metric(self) -> dict:
        """Return an empty metric structure."""
        return {
            "datapoint_count": 0,
            "average": 0,
            "maximum": 0,
        }
    
    def _percentile(self, sorted_values: list[float], percentile: int) -> float:
        """
        Calculate percentile from sorted values.
        
        Args:
            sorted_values: Sorted list of values
            percentile: Percentile to calculate (0-100)
        
        Returns:
            Percentile value
        """
        if not sorted_values:
            return 0.0
        
        n = len(sorted_values)
        index = (percentile / 100) * (n - 1)
        lower = int(index)
        upper = min(lower + 1, n - 1)
        
        weight = index - lower
        value = sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight
        
        return round(value, 2)
    
    def detect_idle_hours(
        self,
        instance_id: str,
        region: str,
        cpu_threshold: float = 5.0,
        days: int = 30,
    ) -> list[dict]:
        """
        Detect periods of low CPU utilization (idle hours).
        
        Args:
            instance_id: EC2 instance ID
            region: AWS region
            cpu_threshold: CPU percentage threshold for "idle"
            days: Number of days to analyze
        
        Returns:
            List of idle periods with start/end hours
        """
        cw = self.aws_client.get_cloudwatch_client(region)
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        try:
            response = cw.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[
                    {"Name": "InstanceId", "Value": instance_id}
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # Hourly
                Statistics=["Average"],
                Unit="Percent",
            )
            
            datapoints = response.get("Datapoints", [])
            if not datapoints:
                return []
            
            # Group by hour of day
            hourly_usage = {}
            for point in datapoints:
                hour = point["Timestamp"].hour
                if hour not in hourly_usage:
                    hourly_usage[hour] = []
                hourly_usage[hour].append(point.get("Average", 0))
            
            # Find consistently idle hours
            idle_periods = []
            for hour in range(24):
                if hour in hourly_usage:
                    values = hourly_usage[hour]
                    avg = statistics.mean(values)
                    idle_ratio = sum(1 for v in values if v < cpu_threshold) / len(values)
                    
                    if avg < cpu_threshold and idle_ratio > 0.8:
                        idle_periods.append({
                            "hour": hour,
                            "average_cpu": round(avg, 2),
                            "idle_ratio": round(idle_ratio, 2),
                        })
            
            # Merge consecutive hours into windows
            return self._merge_idle_periods(idle_periods)
            
        except Exception as e:
            logger.warning(f"Failed to detect idle hours for {instance_id}: {e}")
            return []
    
    def _merge_idle_periods(self, idle_hours: list[dict]) -> list[dict]:
        """
        Merge consecutive idle hours into windows.
        
        Args:
            idle_hours: List of idle hour dictionaries
        
        Returns:
            List of merged idle window dictionaries
        """
        if not idle_hours:
            return []
        
        # Get just the hours for easier processing
        hours_set = set(h["hour"] for h in idle_hours)
        hour_data = {h["hour"]: h for h in idle_hours}
        
        # Find consecutive sequences (handling midnight wraparound)
        # Check if we have a midnight-spanning sequence (e.g., 22,23,0,1,2,3)
        has_midnight_wrap = 0 in hours_set and 23 in hours_set
        
        if has_midnight_wrap:
            # Reorder to handle midnight wraparound: start from first gap after midnight
            ordered_hours = []
            # Find the first hour NOT in the set (gap in sequence)
            start_hour = 0
            for h in range(24):
                if h not in hours_set:
                    start_hour = (h + 1) % 24
                    break
            
            # Build ordered list starting from first hour after gap
            for i in range(24):
                h = (start_hour + i) % 24
                if h in hours_set:
                    ordered_hours.append(hour_data[h])
        else:
            # Simple sort for non-wrapping case
            ordered_hours = sorted(idle_hours, key=lambda x: x["hour"])
        
        if not ordered_hours:
            return []
        
        windows = []
        current_window = {
            "start_hour": ordered_hours[0]["hour"],
            "end_hour": ordered_hours[0]["hour"],
            "duration_hours": 1,
            "avg_cpu": ordered_hours[0]["average_cpu"],
        }
        
        for i in range(1, len(ordered_hours)):
            hour = ordered_hours[i]["hour"]
            prev_hour = ordered_hours[i - 1]["hour"]
            
            # Check if consecutive (including wrap-around at midnight)
            is_consecutive = (hour == (prev_hour + 1) % 24)
            
            if is_consecutive:
                current_window["end_hour"] = hour
                current_window["duration_hours"] += 1
                current_window["avg_cpu"] = round(
                    (current_window["avg_cpu"] + ordered_hours[i]["average_cpu"]) / 2,
                    2
                )
            else:
                # Save current window if significant (4+ hours)
                if current_window["duration_hours"] >= 4:
                    windows.append(current_window)
                
                # Start new window
                current_window = {
                    "start_hour": hour,
                    "end_hour": hour,
                    "duration_hours": 1,
                    "avg_cpu": ordered_hours[i]["average_cpu"],
                }
        
        # Add final window
        if current_window["duration_hours"] >= 4:
            windows.append(current_window)
        
        return windows
    
    def get_usage_summary(self, metrics: dict) -> dict:
        """
        Get a human-readable usage summary from metrics.
        
        Args:
            metrics: Raw metrics dictionary
        
        Returns:
            Summary dictionary
        """
        cpu = metrics.get("CPUUtilization", {})
        
        return {
            "cpu_average": cpu.get("average", 0),
            "cpu_max": cpu.get("maximum", 0),
            "cpu_p95": cpu.get("p95", 0),
            "cpu_p99": cpu.get("p99", 0),
            "is_underutilized": cpu.get("p95", 0) < 40,
            "is_idle": cpu.get("average", 0) < 5,
            "datapoints_available": cpu.get("datapoint_count", 0),
        }
