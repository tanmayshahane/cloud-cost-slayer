#!/bin/bash
# Cloud Cost Slayer - Rollback Script
# Generated: {{ timestamp }}
#
# This script will restore instances to their original sizes
# Run with: bash rollback.sh

set -e

echo "=== Cloud Cost Slayer Rollback ==="
echo "This will restore instances to their original sizes."
echo ""

{% for rec in recommendations %}
echo "Restoring {{ rec.instance_id }} to {{ rec.current_type }}..."
aws ec2 stop-instances --instance-ids {{ rec.instance_id }} --region {{ rec.region }}
aws ec2 wait instance-stopped --instance-ids {{ rec.instance_id }} --region {{ rec.region }}
aws ec2 modify-instance-attribute --instance-id {{ rec.instance_id }} --instance-type {{ rec.current_type }} --region {{ rec.region }}
aws ec2 start-instances --instance-ids {{ rec.instance_id }} --region {{ rec.region }}
aws ec2 wait instance-running --instance-ids {{ rec.instance_id }} --region {{ rec.region }}
echo "✓ {{ rec.instance_id }} restored to {{ rec.current_type }}"
echo ""

{% endfor %}

echo "=== Rollback Complete ==="
echo "All instances have been restored to their original sizes."
