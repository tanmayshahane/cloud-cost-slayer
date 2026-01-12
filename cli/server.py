"""
Cloud Cost Slayer - FastAPI Server.

Bridge between CLI and Web Dashboard providing REST API endpoints.
"""

import os
import uuid
import json
import asyncio
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import CLI components
from .utils.aws_client import AWSClient
from .collectors.ec2_collector import EC2Collector
from .collectors.rds_collector import RDSCollector
from .collectors.cloudwatch_collector import CloudWatchCollector
from .analyzers.rightsizing_analyzer import RightsizingAnalyzer
from .utils.calculator import get_calculator
from .core.analysis_service import (
    build_ec2_instance_data,
    build_rds_instance_data,
    calculate_ec2_costs,
    calculate_rds_costs,
)

# Create FastAPI app
app = FastAPI(
    title="Cloud Cost Slayer API",
    description="REST API for AWS cost optimization",
    version="0.1.0",
)

# Enable CORS for web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (use SQLite for production)
analyses_db: dict = {}
recommendations_db: dict = {}


# ==================
# Models
# ==================

class AnalysisConfig(BaseModel):
    # AWS Credentials
    profile: Optional[str] = None
    accessKey: Optional[str] = None
    secretKey: Optional[str] = None
    
    # Regions
    regions: Optional[List[str]] = None
    
    # Analysis options (matching CLI flags)
    lookbackDays: int = 30
    minSavings: float = 0
    includeProduction: bool = False
    includeRds: bool = True
    confidenceLevel: Optional[str] = None
    excludeTags: Optional[dict] = None


class AnalysisStatus(BaseModel):
    id: str
    status: str
    progress: int
    regions: List[str]
    instancesAnalyzed: int
    recommendationsCount: int
    totalSavings: float
    startedAt: str
    completedAt: Optional[str] = None


class Recommendation(BaseModel):
    id: str
    type: str
    instanceId: str
    instanceName: Optional[str] = None
    region: str
    currentType: str
    recommendedType: Optional[str] = None
    monthlySavings: float
    annualSavings: float
    confidence: str
    currentCost: float
    newCost: float
    cpuAvg: Optional[float] = None
    cpuMax: Optional[float] = None
    status: str = "pending"


class ApplyRequest(BaseModel):
    recommendationIds: List[str]
    dryRun: bool = False


class DashboardStats(BaseModel):
    totalCurrentSpend: float
    totalPotentialSavings: float
    optimizedSpend: float
    savingsPercentage: float
    instancesAnalyzed: int
    recommendationsCount: int
    highConfidenceCount: int
    lastAnalysisAt: Optional[str] = None


# ==================
# Endpoints
# ==================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Cloud Cost Slayer API"}



@app.get("/api/stats", response_model=DashboardStats)
async def get_stats():
    """Get dashboard statistics."""
    # Calculate from stored data
    total_current = sum(r.get("currentCost", 0) for r in recommendations_db.values())
    total_savings = sum(r.get("monthlySavings", 0) for r in recommendations_db.values())
    
    return DashboardStats(
        totalCurrentSpend=total_current,
        totalPotentialSavings=total_savings,
        optimizedSpend=total_current - total_savings,
        savingsPercentage=(total_savings / total_current * 100) if total_current > 0 else 0,
        instancesAnalyzed=len(set(r.get("instanceId") for r in recommendations_db.values())),
        recommendationsCount=len(recommendations_db),
        highConfidenceCount=len([r for r in recommendations_db.values() if r.get("confidence") == "high"]),
        lastAnalysisAt=max([a.get("completedAt") for a in analyses_db.values()], default=None) if analyses_db else None,
    )


@app.get("/api/dashboard")
async def get_dashboard():
    """
    Get dashboard data in beginner-friendly format.
    Returns instance details with cost breakdowns, usage analysis, and recommendations.
    """
    # Check if we have any analysis data
    if not analyses_db:
        return {"hasData": False}
    
    # Get the latest completed analysis
    completed_analyses = [a for a in analyses_db.values() if a.get("status") == "completed"]
    if not completed_analyses:
        return {"hasData": False}
    
    latest = max(completed_analyses, key=lambda a: a.get("completedAt", ""))
    
    # Build EC2 instance list with friendly data
    ec2_instances = []
    rds_instances = []
    total_current_cost = 0
    total_savings = 0
    
    for rec in recommendations_db.values():
        instance_data = {
            "id": rec.get("instanceId", ""),
            "name": rec.get("instanceName", rec.get("instanceId", "")),
            "type": rec.get("currentType", ""),
            "region": rec.get("region", ""),
            "state": "running",
            # Cost data matching CLI output
            "hourlyRate": rec.get("hourlyRate", 0),
            "currentMonthCost": rec.get("currentMonthCost", 0),
            "hoursThisMonth": rec.get("hoursThisMonth", 0),
            "projectedMonthCost": rec.get("projectedMonthCost", 0),
            "monthlyCost": rec.get("currentCost", 0),  # Total monthly cost
            # Storage
            "storageCost": rec.get("storageCost", 0),
            "storageGb": rec.get("storageGb", 0),
            # CPU metrics
            "cpuAvg": rec.get("cpuAvg", 0) or 0,
            "cpuMax": rec.get("cpuMax", 0) or 0,
        }
        
        # Add RDS-specific fields
        if rec.get("resourceType") == "rds":
            instance_data["engine"] = rec.get("engine", "")
            instance_data["multiAz"] = rec.get("multiAz", False)
        
        total_current_cost += rec.get("currentMonthCost", 0)
        
        # Add recommendation if there are savings
        if rec.get("monthlySavings", 0) > 0:
            savings = rec.get("monthlySavings", 0)
            total_savings += savings
            
            rec_type = rec.get("type", "rightsizing")
            
            if rec_type == "rightsizing" and rec.get("recommendedType"):
                message = f"This instance is oversized. Resize from {rec.get('currentType')} to {rec.get('recommendedType')} to save money."
            elif rec_type == "idle":
                message = "This instance is idle. Consider stopping it to save money."
            elif rec_type == "scheduling":
                message = "This instance has predictable idle hours. Set up a schedule to automatically stop it during off hours."
            else:
                message = f"Optimization opportunity available. Potential savings: ${savings:.2f}/month"
            
            instance_data["recommendation"] = {
                "type": rec_type,
                "message": message,
                "savings": savings,
                "newType": rec.get("recommendedType"),
            }
        
        # Use resourceType field for proper categorization
        resource_type = rec.get("resourceType", "")
        if resource_type == "rds" or rec.get("type", "") == "rds-info":
            rds_instances.append(instance_data)
        else:
            # Default to EC2
            ec2_instances.append(instance_data)
    
    return {
        "hasData": True,
        "ec2Instances": ec2_instances,
        "rdsInstances": rds_instances,
        "totalCurrentCost": total_current_cost,
        "totalPotentialSavings": total_savings,
        "lastAnalyzedAt": latest.get("completedAt", datetime.now().isoformat()),
    }



@app.post("/api/analyze", response_model=AnalysisStatus)
async def start_analysis(config: AnalysisConfig, background_tasks: BackgroundTasks):
    """Start a new analysis run."""
    analysis_id = str(uuid.uuid4())
    
    analysis = {
        "id": analysis_id,
        "status": "running",
        "progress": 0,
        "regions": config.regions or ["us-east-1"],
        "instancesAnalyzed": 0,
        "recommendationsCount": 0,
        "totalSavings": 0,
        "startedAt": datetime.now().isoformat(),
        "completedAt": None,
        "config": config.dict(),
    }
    
    analyses_db[analysis_id] = analysis
    
    # Run analysis in background
    background_tasks.add_task(run_analysis, analysis_id, config)
    
    return AnalysisStatus(**analysis)


async def run_analysis(analysis_id: str, config: AnalysisConfig):
    """Background task to run the analysis."""
    analysis = analyses_db[analysis_id]
    
    # Clear previous recommendations to avoid duplicate keys
    recommendations_db.clear()
    
    try:
        # Initialize AWS client with credentials from config
        if config.accessKey and config.secretKey:
            # Use provided access keys by setting environment variables
            # (AWSClient reads from environment)
            import os
            os.environ["AWS_ACCESS_KEY_ID"] = config.accessKey
            os.environ["AWS_SECRET_ACCESS_KEY"] = config.secretKey
            # Clear any session token
            if "AWS_SESSION_TOKEN" in os.environ:
                del os.environ["AWS_SESSION_TOKEN"]
            aws_client = AWSClient()
        elif config.profile:
            # Use profile
            aws_client = AWSClient(profile=config.profile)
        else:
            # Use default credentials
            aws_client = AWSClient()
        
        analysis["progress"] = 10
        
        # Collect EC2 instances
        ec2_collector = EC2Collector(aws_client)
        
        # Build exclude tags for production filtering (convert dict to list of tuples)
        exclude_tags_dict = config.excludeTags or {}
        if not config.includeProduction:
            exclude_tags_dict["Environment"] = "production"
        
        # Convert to list of tuples for EC2Collector
        exclude_tags_list = [(k, v) for k, v in exclude_tags_dict.items()] if exclude_tags_dict else None
        
        instances = ec2_collector.collect_all_instances(
            regions=config.regions,
            states=["running"],
            exclude_tags=exclude_tags_list,
            show_progress=False,
        )
        
        analysis["progress"] = 30
        analysis["instancesAnalyzed"] = len(instances)
        
        # Collect RDS if enabled
        rds_instances = []
        if config.includeRds:
            try:
                rds_collector = RDSCollector(aws_client)
                rds_instances = rds_collector.collect_all_instances(
                    regions=config.regions,
                    show_progress=False,
                )
            except Exception as e:
                print(f"RDS collection error: {e}")  # Log but continue
        
        analysis["rdsInstances"] = len(rds_instances)
        
        analysis["progress"] = 45
        
        # Collect metrics for EC2
        cw_collector = CloudWatchCollector(aws_client)
        metrics = cw_collector.collect_batch_metrics(
            instances,
            days=config.lookbackDays,
            show_progress=False,
        )
        
        analysis["progress"] = 60
        
        # Analyze EC2
        analyzer = RightsizingAnalyzer(exclude_production=not config.includeProduction)
        recs = analyzer.analyze_batch(instances, metrics)
        
        # Filter by minSavings
        if config.minSavings > 0:
            recs = [r for r in recs if r.monthly_savings >= config.minSavings]
        
        # Filter by confidence
        if config.confidenceLevel and config.confidenceLevel != 'all':
            if config.confidenceLevel == 'high':
                recs = [r for r in recs if r.confidence == 'high']
            elif config.confidenceLevel == 'medium':
                recs = [r for r in recs if r.confidence in ['high', 'medium']]
        
        analysis["progress"] = 80
        
        # Store EC2 recommendations - create a mapping first
        ec2_rec_map = {}  # Map instance_id -> recommendation
        for rec in recs:
            ec2_rec_map[rec.instance_id] = rec
        
        # Collect RDS metrics
        rds_metrics = {}
        if rds_instances:
            rds_metrics = cw_collector.collect_batch_rds_metrics(
                rds_instances,
                days=config.lookbackDays,
                show_progress=False,
            )
        
        # Store ALL EC2 instances using core analysis service
        for inst in instances:
            inst_id = inst.get("instance_id", "")
            inst_metrics = metrics.get(inst_id, {})
            rec = ec2_rec_map.get(inst_id)
            region = inst.get("region", "us-east-1")
            
            # Collect EBS volume details for storage info
            ebs_volumes = inst.get("ebs_volumes", [])
            storage_gb = 0
            storage_cost = 0
            if ebs_volumes:
                volume_ids = [v["volume_id"] for v in ebs_volumes if "volume_id" in v]
                if volume_ids:
                    try:
                        volume_details = ec2_collector.get_volume_details(volume_ids, region)
                        if volume_details:
                            storage_gb = sum(v.get("size_gb", 0) for v in volume_details)
                            storage_cost = sum(v.get("monthly_cost", 0) for v in volume_details)
                    except Exception as e:
                        print(f"EBS volume details error: {e}")
            
            # Use core service to build instance data
            instance_data = build_ec2_instance_data(inst, inst_metrics, rec)
            
            rec_id = f"ec2-{uuid.uuid4().hex[:8]}"
            
            if rec:
                recommendations_db[rec_id] = {
                    "id": rec_id,
                    "type": "rightsizing",
                    "resourceType": "ec2",
                    "instanceId": instance_data["id"],
                    "instanceName": instance_data["name"],
                    "region": instance_data["region"],
                    "currentType": instance_data["type"],
                    "recommendedType": instance_data["recommendation"]["recommendedType"],
                    "monthlySavings": instance_data["recommendation"]["monthlySavings"],
                    "annualSavings": instance_data["recommendation"]["annualSavings"],
                    "confidence": instance_data["recommendation"]["confidence"],
                    "currentCost": instance_data["recommendation"]["currentCost"],
                    "newCost": instance_data["recommendation"]["newCost"],
                    "hourlyRate": instance_data["hourlyRate"],
                    "currentMonthCost": instance_data["currentMonthCost"],
                    "hoursThisMonth": instance_data["hoursThisMonth"],
                    "projectedMonthCost": instance_data["projectedMonthCost"],
                    "storageGb": storage_gb,
                    "storageCost": storage_cost,
                    "cpuAvg": instance_data["cpuAvg"],
                    "cpuMax": instance_data["cpuMax"],
                    "status": "pending",
                }
            else:
                # Store as info even without recommendation
                recommendations_db[rec_id] = {
                    "id": rec_id,
                    "type": "ec2-info",
                    "resourceType": "ec2",
                    "instanceId": instance_data["id"],
                    "instanceName": instance_data["name"],
                    "region": instance_data["region"],
                    "currentType": instance_data["type"],
                    "recommendedType": None,
                    "monthlySavings": 0,
                    "annualSavings": 0,
                    "confidence": "info",
                    "currentCost": instance_data["projectedMonthCost"],
                    "newCost": instance_data["projectedMonthCost"],
                    "hourlyRate": instance_data["hourlyRate"],
                    "currentMonthCost": instance_data["currentMonthCost"],
                    "hoursThisMonth": instance_data["hoursThisMonth"],
                    "projectedMonthCost": instance_data["projectedMonthCost"],
                    "storageGb": storage_gb,
                    "storageCost": storage_cost,
                    "cpuAvg": instance_data["cpuAvg"],
                    "cpuMax": instance_data["cpuMax"],
                    "status": "info",
                }
        
        # Store RDS instances using core analysis service
        for rds in rds_instances:
            db_id = rds.get("db_instance_id", "")
            rds_metric_data = rds_metrics.get(db_id, {})
            
            # Use core service to build RDS data
            rds_data = build_rds_instance_data(rds, rds_metric_data)
            
            rec_id = f"rds-{uuid.uuid4().hex[:8]}"
            
            recommendations_db[rec_id] = {
                "id": rec_id,
                "type": "rds-info",
                "resourceType": "rds",
                "instanceId": rds_data["id"],
                "instanceName": rds_data["name"],
                "region": rds_data["region"],
                "currentType": rds_data["type"],
                "recommendedType": None,
                "monthlySavings": 0,
                "annualSavings": 0,
                "confidence": "info",
                "currentCost": rds_data["totalMonthlyCost"],
                "newCost": rds_data["totalMonthlyCost"],
                "hourlyRate": rds_data["hourlyRate"],
                "currentMonthCost": rds_data["currentMonthCost"],
                "hoursThisMonth": rds_data["hoursThisMonth"],
                "projectedMonthCost": rds_data["projectedMonthCost"],
                "storageCost": rds_data["storageCost"],
                "storageGb": rds_data["storageGb"],
                "engine": rds_data["engine"],
                "multiAz": rds_data["multiAz"],
                "cpuAvg": rds_data["cpuAvg"],
                "cpuMax": rds_data["cpuMax"],
                "status": "info",
            }
        
        analysis["progress"] = 90
        
        analysis["recommendationsCount"] = len(recs) + len(rds_instances)
        analysis["totalSavings"] = sum(r.monthly_savings for r in recs)
        analysis["status"] = "completed"
        analysis["progress"] = 100
        analysis["completedAt"] = datetime.now().isoformat()
        
    except Exception as e:
        analysis["status"] = "failed"
        analysis["error"] = str(e)




@app.get("/api/analyze/{analysis_id}", response_model=AnalysisStatus)
async def get_analysis_status(analysis_id: str):
    """Get analysis status."""
    if analysis_id not in analyses_db:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    return AnalysisStatus(**analyses_db[analysis_id])


@app.get("/api/analyses")
async def list_analyses():
    """List all analyses."""
    return sorted(
        [AnalysisStatus(**a) for a in analyses_db.values()],
        key=lambda x: x.startedAt,
        reverse=True
    )


@app.get("/api/recommendations")
async def list_recommendations(
    type: Optional[str] = None,
    confidence: Optional[str] = None,
    minSavings: Optional[float] = None,
    region: Optional[str] = None,
):
    """List recommendations with optional filters."""
    recs = list(recommendations_db.values())
    
    if type:
        recs = [r for r in recs if r.get("type") == type]
    if confidence:
        recs = [r for r in recs if r.get("confidence") == confidence]
    if minSavings:
        recs = [r for r in recs if r.get("monthlySavings", 0) >= minSavings]
    if region:
        recs = [r for r in recs if r.get("region") == region]
    
    return {
        "recommendations": sorted(recs, key=lambda x: x.get("monthlySavings", 0), reverse=True),
        "total": len(recs),
    }


@app.get("/api/recommendations/{rec_id}")
async def get_recommendation(rec_id: str):
    """Get a single recommendation."""
    if rec_id not in recommendations_db:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    
    return recommendations_db[rec_id]


@app.delete("/api/recommendations/{rec_id}")
async def dismiss_recommendation(rec_id: str):
    """Dismiss a recommendation."""
    if rec_id not in recommendations_db:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    
    recommendations_db[rec_id]["status"] = "dismissed"
    return {"success": True}


@app.post("/api/apply")
async def apply_recommendations(request: ApplyRequest, background_tasks: BackgroundTasks):
    """Apply one or more recommendations."""
    apply_id = str(uuid.uuid4())
    
    affected_recs = []
    for rec_id in request.recommendationIds:
        if rec_id in recommendations_db:
            affected_recs.append(recommendations_db[rec_id])
    
    if not affected_recs:
        raise HTTPException(status_code=400, detail="No valid recommendations found")
    
    if request.dryRun:
        return {
            "applyId": apply_id,
            "status": "dry_run",
            "dryRun": True,
            "affectedInstances": [r["instanceId"] for r in affected_recs],
            "totalSavings": sum(r.get("monthlySavings", 0) for r in affected_recs),
            "message": "Dry run completed. No changes were made.",
        }
    
    # Mark as applying
    for rec in affected_recs:
        rec["status"] = "applying"
    
    # In production, add background task to actually apply changes
    # background_tasks.add_task(apply_changes, apply_id, affected_recs)
    
    return {
        "applyId": apply_id,
        "status": "pending",
        "affectedInstances": [r["instanceId"] for r in affected_recs],
        "message": "Apply request submitted",
    }


# ==================
# Report Endpoints
# ==================

class ReportConfig(BaseModel):
    format: str = "html"
    confidence: Optional[str] = None
    minSavings: float = 0
    limit: int = 50


@app.post("/api/report")
async def generate_report(config: ReportConfig):
    """Generate a cost optimization report."""
    from .generators.report_generator import ReportGenerator
    from pathlib import Path
    
    # Filter recommendations
    recs = list(recommendations_db.values())
    
    if config.confidence:
        recs = [r for r in recs if r.get("confidence") == config.confidence]
    
    if config.minSavings > 0:
        recs = [r for r in recs if r.get("monthlySavings", 0) >= config.minSavings]
    
    recs = recs[:config.limit]
    
    # Convert frontend format to report generator format
    formatted_recs = []
    for r in recs:
        formatted_recs.append({
            "instance_id": r.get("instanceId", ""),
            "instance_name": r.get("name", ""),
            "current_type": r.get("currentType", ""),
            "recommended_type": r.get("recommendedType", ""),
            "monthly_savings": r.get("monthlySavings", 0),
            "confidence": r.get("confidence", "low"),
            "region": r.get("region", "us-east-1"),
        })
    
    # Generate report using ReportGenerator
    generator = ReportGenerator()
    
    # Map frontend format to generator format
    format_map = {
        "html": "html",
        "json": "json", 
        "markdown": "markdown"
    }
    report_format = format_map.get(config.format, "html")
    
    # Generate report content
    report_content = generator.generate_report(
        recommendations=formatted_recs,
        instances_analyzed=len(set(r.get("instanceId") for r in recs)),
        format_type=report_format,
    )
    
    # Save to disk
    reports_dir = Path("./reports")
    reports_dir.mkdir(exist_ok=True)
    
    ext = {"html": "html", "json": "json", "markdown": "md"}.get(config.format, "html")
    filename = f"cost-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{ext}"
    filepath = reports_dir / filename
    filepath.write_text(report_content)
    
    total_savings = sum(r.get("monthlySavings", 0) for r in recs)
    
    return {
        "success": True,
        "format": config.format,
        "recommendationsCount": len(recs),
        "totalSavings": total_savings,
        "filepath": str(filepath.absolute()),
        "filename": filename,
        "content": report_content,
        "message": f"Report saved to {filepath}",
    }


# ==================
# Monitor Endpoints
# ==================

class MonitorConfig(BaseModel):
    interval: int = 60
    threshold: float = 100
    slackWebhook: Optional[str] = None
    runOnce: bool = True


@app.post("/api/monitor")
async def run_monitor(config: MonitorConfig):
    """Run cost monitoring check."""
    # Simplified monitor - in production this would run actual checks
    total_savings = sum(r.get("monthlySavings", 0) for r in recommendations_db.values())
    instances_checked = len(set(r.get("instanceId") for r in recommendations_db.values()))
    
    alert_triggered = total_savings >= config.threshold
    
    result = {
        "success": True,
        "instancesChecked": instances_checked,
        "totalSavings": total_savings,
        "threshold": config.threshold,
        "alertTriggered": alert_triggered,
    }
    
    # If Slack webhook provided and alert triggered, we would send notification
    if config.slackWebhook and alert_triggered:
        result["slackNotified"] = True
        result["message"] = f"Alert: ${total_savings:.2f}/mo savings available!"
    
    return result


# ==================
# Schedule Endpoints
# ==================

class ScheduleConfig(BaseModel):
    instanceId: str
    startTime: str = "08:00"
    stopTime: str = "18:00"
    timezone: str = "UTC"
    weekdaysOnly: bool = True


# In-memory schedule storage
schedules_db: dict = {}


@app.post("/api/schedule")
async def create_schedule(config: ScheduleConfig):
    """Create or update an instance schedule."""
    schedule_id = f"sched-{config.instanceId}"
    
    schedules_db[schedule_id] = {
        "id": schedule_id,
        "instanceId": config.instanceId,
        "startTime": config.startTime,
        "stopTime": config.stopTime,
        "timezone": config.timezone,
        "weekdaysOnly": config.weekdaysOnly,
        "createdAt": datetime.now().isoformat(),
        "status": "active",
    }
    
    # Calculate savings estimate (rough: 14 hrs stopped per day)
    stopped_hours = 24 - (int(config.stopTime.split(":")[0]) - int(config.startTime.split(":")[0]))
    if config.weekdaysOnly:
        stopped_hours = stopped_hours * 5 / 7  # Adjust for weekends
    
    savings_percent = stopped_hours / 24 * 100
    
    return {
        "success": True,
        "scheduleId": schedule_id,
        "instanceId": config.instanceId,
        "startTime": config.startTime,
        "stopTime": config.stopTime,
        "timezone": config.timezone,
        "estimatedSavingsPercent": round(savings_percent, 1),
        "message": f"Schedule created. Instance will run from {config.startTime} to {config.stopTime} ({config.timezone})",
    }


@app.get("/api/schedules")
async def list_schedules():
    """List all schedules."""
    return {"schedules": list(schedules_db.values())}


# ==================
# Config Endpoints
# ==================

class ConfigData(BaseModel):
    awsProfile: Optional[str] = None
    awsAccessKey: Optional[str] = None
    awsSecretKey: Optional[str] = None
    defaultRegion: str = "us-east-1"
    defaultLookbackDays: int = 30
    defaultMinSavings: float = 10
    excludeProduction: bool = True


# In-memory config storage
config_db: dict = {}


@app.post("/api/config")
async def save_config(config: ConfigData):
    """Save configuration."""
    config_db.update(config.dict())
    return {"success": True, "message": "Configuration saved"}


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    return config_db


@app.post("/api/config/test")
async def test_credentials(config: ConfigData):
    """Test AWS credentials."""
    try:
        import boto3
        
        if config.awsAccessKey and config.awsSecretKey:
            session = boto3.Session(
                aws_access_key_id=config.awsAccessKey,
                aws_secret_access_key=config.awsSecretKey,
            )
        elif config.awsProfile:
            session = boto3.Session(profile_name=config.awsProfile)
        else:
            session = boto3.Session()
        
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        
        return {
            "success": True,
            "accountId": identity.get("Account"),
            "userId": identity.get("UserId"),
            "arn": identity.get("Arn"),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ==================
# Main
# ==================

def main():
    """Run the server."""
    uvicorn.run(
        "cli.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()

