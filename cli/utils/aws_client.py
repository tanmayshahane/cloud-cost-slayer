"""
AWS SDK wrapper with retry logic, caching, and error handling.

Provides centralized access to AWS services with:
- Automatic retry with exponential backoff
- Rate limit handling
- Multi-region support
- Credential management
- Client caching
"""

import os
import time
from functools import lru_cache
from typing import Optional, Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
    EndpointConnectionError,
)

from .logger import get_logger, print_error, print_warning

logger = get_logger(__name__)

# Default boto3 configuration with retry settings
DEFAULT_CONFIG = Config(
    retries={
        "max_attempts": 5,
        "mode": "adaptive",
    },
    connect_timeout=10,
    read_timeout=30,
)

# Cache for pricing data (1 hour TTL)
_pricing_cache: dict[str, tuple[float, dict]] = {}
PRICING_CACHE_TTL = 3600  # seconds


class AWSClientError(Exception):
    """Custom exception for AWS client errors with actionable messages."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class AWSClient:
    """
    Centralized AWS client wrapper with retry logic and caching.
    
    Attributes:
        profile: AWS profile name
        default_region: Default AWS region
    """
    
    def __init__(
        self,
        profile: Optional[str] = None,
        region: Optional[str] = None
    ):
        """
        Initialize AWS client wrapper.
        
        Args:
            profile: AWS profile name (uses AWS_PROFILE env var if not specified)
            region: Default region (uses AWS_REGION env var if not specified)
        """
        self.profile = profile or os.environ.get("AWS_PROFILE")
        self.default_region = region or os.environ.get("AWS_REGION", "us-east-1")
        self._session: Optional[boto3.Session] = None
        self._client_cache: dict[str, Any] = {}
        
    @property
    def session(self) -> boto3.Session:
        """Get or create boto3 session."""
        if self._session is None:
            try:
                # Check for explicit credentials in environment
                access_key = os.environ.get("AWS_ACCESS_KEY_ID")
                secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
                session_token = os.environ.get("AWS_SESSION_TOKEN")
                
                if self.profile:
                    # Use named profile
                    self._session = boto3.Session(
                        profile_name=self.profile,
                        region_name=self.default_region,
                    )
                elif access_key and secret_key:
                    # Use explicit credentials from environment
                    self._session = boto3.Session(
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        aws_session_token=session_token,
                        region_name=self.default_region,
                    )
                else:
                    # Fall back to boto3 default credential chain
                    self._session = boto3.Session(
                        region_name=self.default_region,
                    )
            except Exception as e:
                raise AWSClientError(
                    f"Failed to create AWS session: {str(e)}. "
                    "Check your AWS credentials configuration.",
                    original_error=e
                )
        return self._session
    
    def get_client(self, service: str, region: Optional[str] = None) -> Any:
        """
        Get a boto3 client for a service, with caching.
        
        Args:
            service: AWS service name (e.g., 'ec2', 'cloudwatch')
            region: AWS region (uses default if not specified)
        
        Returns:
            Boto3 client for the service
        """
        region = region or self.default_region
        cache_key = f"{service}:{region}"
        
        if cache_key not in self._client_cache:
            try:
                self._client_cache[cache_key] = self.session.client(
                    service,
                    region_name=region,
                    config=DEFAULT_CONFIG,
                )
            except Exception as e:
                raise AWSClientError(
                    f"Failed to create {service} client in {region}: {str(e)}",
                    original_error=e
                )
        
        return self._client_cache[cache_key]
    
    def get_ec2_client(self, region: Optional[str] = None) -> Any:
        """Get EC2 client for a region."""
        return self.get_client("ec2", region)
    
    def get_cloudwatch_client(self, region: Optional[str] = None) -> Any:
        """Get CloudWatch client for a region."""
        return self.get_client("cloudwatch", region)
    
    def get_pricing_client(self) -> Any:
        """
        Get Pricing API client (always in us-east-1).
        
        Note: AWS Pricing API is only available in us-east-1 and ap-south-1.
        """
        return self.get_client("pricing", "us-east-1")
    
    def get_cost_explorer_client(self) -> Any:
        """
        Get Cost Explorer client.
        
        Note: Cost Explorer is a global service, uses us-east-1.
        """
        return self.get_client("ce", "us-east-1")
    
    def get_all_regions(self) -> list[str]:
        """
        Get list of all available EC2 regions.
        
        Returns:
            List of region names
        """
        try:
            ec2 = self.get_ec2_client()
            response = ec2.describe_regions()
            regions = [r["RegionName"] for r in response.get("Regions", [])]
            logger.debug(f"Found {len(regions)} AWS regions")
            return sorted(regions)
        except ClientError as e:
            logger.error(f"Failed to list regions: {e}")
            # Return common regions as fallback
            return [
                "us-east-1", "us-east-2", "us-west-1", "us-west-2",
                "eu-west-1", "eu-west-2", "eu-central-1",
                "ap-south-1", "ap-southeast-1", "ap-northeast-1",
            ]
    
    def test_credentials(self) -> tuple[bool, str]:
        """
        Test if AWS credentials are valid.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            sts = self.get_client("sts")
            identity = sts.get_caller_identity()
            account_id = identity.get("Account", "unknown")
            arn = identity.get("Arn", "unknown")
            return True, f"Authenticated as {arn} (Account: {account_id})"
        except NoCredentialsError:
            return False, "No AWS credentials found. Configure with 'aws configure' or set environment variables."
        except PartialCredentialsError:
            return False, "Incomplete AWS credentials. Check AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            return False, f"Authentication failed: {error_code}"
        except Exception as e:
            return False, f"Credential test failed: {str(e)}"


def with_retry(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
):
    """
    Decorator for retrying AWS API calls with exponential backoff.
    
    Args:
        func: Function to wrap
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff
    
    Returns:
        Wrapped function with retry logic
    """
    def wrapper(*args, **kwargs):
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                
                # Don't retry certain error types
                if error_code in ["AccessDenied", "UnauthorizedAccess", "InvalidAction"]:
                    raise
                
                # Retry on throttling and transient errors
                if error_code in ["Throttling", "RequestLimitExceeded", "ServiceUnavailable"]:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base ** attempt), max_delay)
                        logger.warning(
                            f"Rate limited, retrying in {delay:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(delay)
                        continue
                raise
            except EndpointConnectionError as e:
                last_exception = e
                if attempt < max_retries:
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    logger.warning(
                        f"Connection error, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
                raise
        
        if last_exception:
            raise last_exception
    
    return wrapper


def paginate(client, method: str, key: str, **kwargs) -> list:
    """
    Paginate through AWS API responses.
    
    Args:
        client: Boto3 client
        method: Method name to call
        key: Response key containing the items
        **kwargs: Arguments to pass to the method
    
    Returns:
        List of all items from all pages
    """
    items = []
    paginator = client.get_paginator(method)
    
    for page in paginator.paginate(**kwargs):
        items.extend(page.get(key, []))
    
    return items


# Convenience function for getting a pre-configured client
@lru_cache(maxsize=1)
def get_default_client() -> AWSClient:
    """Get the default AWS client instance (cached)."""
    return AWSClient()
