# Cloud Cost Slayer 🔍💰

> Open-source CLI and Web Dashboard for AWS cost optimization with actionable recommendations and one-click implementation scripts.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 🔍 **Automated Analysis** - Scan EC2 and RDS instances across all regions
- 💰 **Right-Sizing** - Identify over-provisioned instances with confidence scores
- ⏰ **Scheduling** - Detect idle hours for shutdown opportunities
- 🎯 **Reserved Instances** - Find RI purchase opportunities
- 📊 **Executive Reports** - Generate HTML/Markdown/JSON reports
- 🚀 **One-Click Apply** - Generate Terraform scripts for safe implementation
- 🌐 **Web Dashboard** - Modern React dashboard for visual cost analysis

## Quick Start

### Option 1: Docker (Recommended) 🐳

The easiest way to run Cloud Cost Slayer is with Docker:

```bash
# Clone the repository
git clone https://github.com/yourusername/cloud-cost-slayer.git
cd cloud-cost-slayer

# Start both backend and frontend
docker-compose up --build

# Open http://localhost:3000 in your browser
```

**AWS Credentials with Docker:**
```bash
# Option A: Use environment variables
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
docker-compose up

# Option B: Mount your existing AWS credentials (automatic)
# Docker Compose automatically mounts ~/.aws for credential access
```

---

### Option 2: Manual Installation

#### Prerequisites

- Python 3.10 or higher
- Node.js 18+ (for web dashboard)

#### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/cloud-cost-slayer.git
cd cloud-cost-slayer

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install Python dependencies
pip install -r requirements.txt
```

#### Configure AWS Credentials

```bash
# Option 1: Use existing AWS CLI profile
export AWS_PROFILE=your-profile

# Option 2: Set environment variables
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
```

---

## Running the CLI

```bash
# Activate virtual environment first
source venv/bin/activate

# Analyze all regions
python -m cli.main analyze

# Analyze specific region
python -m cli.main analyze --region us-east-1

# Exclude production instances
python -m cli.main analyze --exclude-tag Environment=production

# Generate report
python -m cli.main report --format html --output report.html

# Test AWS configuration
python -m cli.main config test
```

---

## Running the Web Dashboard

The web dashboard provides a visual interface for analyzing AWS costs.

### Step 1: Start the Backend Server

```bash
# From project root, activate venv and start server
source venv/bin/activate
python3 -m cli.server

# Server runs at http://localhost:8000
```

### Step 2: Start the Web Frontend

```bash
# Open a new terminal, navigate to web folder
cd web

# Install dependencies (first time only)
npm install

# Start development server
npm run dev

# Dashboard runs at http://localhost:3000
```

### Using the Dashboard

1. Open http://localhost:3000 in your browser
2. Click **"Analyze"** to run a new cost analysis
3. Enter your AWS credentials or use a profile
4. View results with cost breakdowns and recommendations
5. Use the **floating cost summary hub** (bottom-right) for quick totals

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `analyze` | Scan EC2/RDS instances for optimization opportunities |
| `report` | Generate cost optimization reports (HTML, JSON, Markdown) |
| `apply` | Apply recommendations (resize, stop, start instances) |
| `schedule` | Configure automatic start/stop schedules |
| `monitor` | Continuous monitoring with Slack alerts |
| `config` | Manage AWS credentials and settings |

---

## Required AWS Permissions

### Read-Only (for analyze, report, monitor)
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ReadOnlyAnalysis",
            "Effect": "Allow",
            "Action": [
                "ec2:Describe*",
                "rds:Describe*",
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics",
                "pricing:GetProducts",
                "ce:GetCostAndUsage"
            ],
            "Resource": "*"
        }
    ]
}
```

### Full Access (includes apply and schedule commands)
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ReadOnlyAnalysis",
            "Effect": "Allow",
            "Action": [
                "ec2:Describe*",
                "rds:Describe*",
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics",
                "pricing:GetProducts",
                "ce:GetCostAndUsage"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ApplyRecommendations",
            "Effect": "Allow",
            "Action": [
                "ec2:StopInstances",
                "ec2:StartInstances",
                "ec2:ModifyInstanceAttribute"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ScheduleManagement",
            "Effect": "Allow",
            "Action": [
                "events:PutRule",
                "events:PutTargets",
                "events:DescribeRule",
                "events:RemoveTargets",
                "events:DeleteRule"
            ],
            "Resource": "*"
        },
        {
            "Sid": "ScheduleIAM",
            "Effect": "Allow",
            "Action": [
                "iam:GetRole",
                "iam:CreateRole",
                "iam:AttachRolePolicy",
                "iam:PassRole"
            ],
            "Resource": "arn:aws:iam::*:role/CloudCostSlayerScheduler*"
        }
    ]
}
```

---

## Safety Features

✅ **Dry-run mode by default** - No changes without explicit approval  
✅ **Confidence scoring** - High/Medium/Low ratings for recommendations  
✅ **Production exclusion** - Skip production-tagged instances by default  
✅ **Rollback scripts** - Auto-generated rollback for every change  
✅ **EBS storage tracking** - Full visibility into storage costs  

---

## Development

```bash
# Install development dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run the server in development mode (auto-reload)
python3 -m cli.server

# Run web in development mode
cd web && npm run dev
```

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](docs/contributing.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

Built with ❤️ for developers looking to slay cloud cost!
