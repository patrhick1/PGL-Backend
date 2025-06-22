import logging
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
import os
from typing import Optional

from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

class StorageService:
    """Service for handling file storage operations with AWS S3."""

    def __init__(self):
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region_name = os.getenv("AWS_REGION")
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")

        # More robust check for missing or empty environment variables
        if not all([self.aws_access_key_id, self.aws_secret_access_key, self.region_name, self.bucket_name]):
            logger.warning("S3 storage service is not configured. One or more required AWS environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, AWS_S3_BUCKET_NAME) are missing or empty. Upload functionality will be disabled.")
            self.s3_client = None
            return

        # Recommended to specify signature version v4 for presigned URLs
        s3_config = Config(signature_version='s3v4')
        
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
            config=s3_config
        )
        logger.info(f"StorageService initialized for bucket '{self.bucket_name}' in region '{self.region_name}'.")

    def generate_presigned_upload_url(self, object_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL to upload a file to S3.

        Args:
            object_key: The key (path/filename) for the object in S3.
            expiration: Time in seconds for the presigned URL to remain valid.

        Returns:
            The presigned URL as a string, or None if an error occurred.
        """
        if not self.s3_client:
            logger.error("S3 client not configured. Cannot generate presigned URL.")
            return None
            
        try:
            response = self.s3_client.generate_presigned_url(
                'put_object',
                Params={'Bucket': self.bucket_name, 'Key': object_key},
                ExpiresIn=expiration
            )
            return response
        except ClientError as e:
            # Log the specific boto3 client error for easier debugging
            logger.error(f"Boto3 ClientError generating presigned URL for {object_key}: {e.response['Error']['Code']} - {e.response['Error']['Message']}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating presigned URL for {object_key}: {e}", exc_info=True)
            return None

    def get_object_url(self, object_key: str) -> str:
        """
        Constructs the public-access URL for an object in S3.
        Note: This requires the object to have public read access or for the bucket to be configured appropriately.
        For private buckets, you'd generate presigned GET URLs instead.
        """
        return f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{object_key}"

# Global instance
storage_service = StorageService()