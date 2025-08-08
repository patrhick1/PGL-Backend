# podcast_outreach/config/email_providers.py

"""
Configuration management for email providers (Nylas and Instantly).
Provides settings, validation, and provider selection logic.
"""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EmailProvider(Enum):
    """Supported email providers."""
    INSTANTLY = "instantly"
    NYLAS = "nylas"


@dataclass
class NylasConfig:
    """Nylas configuration settings."""
    api_key: str
    api_uri: str = "https://api.us.nylas.com"
    webhook_secret: Optional[str] = None
    grant_id: Optional[str] = None  # Default grant ID
    
    @classmethod
    def from_env(cls) -> "NylasConfig":
        """Create config from environment variables."""
        return cls(
            api_key=os.getenv("NYLAS_API_KEY", ""),
            api_uri=os.getenv("NYLAS_API_URI", "https://api.us.nylas.com"),
            webhook_secret=os.getenv("NYLAS_WEBHOOK_SECRET"),
            grant_id=os.getenv("NYLAS_GRANT_ID")
        )
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if not self.api_key:
            errors.append("NYLAS_API_KEY is required")
        if not self.api_uri:
            errors.append("NYLAS_API_URI is required")
        return errors


@dataclass
class InstantlyConfig:
    """Instantly configuration settings."""
    api_key: str
    base_url: str = "https://api.instantly.ai/api/v2"
    
    @classmethod
    def from_env(cls) -> "InstantlyConfig":
        """Create config from environment variables."""
        return cls(
            api_key=os.getenv("INSTANTLY_API_KEY", ""),
            base_url=os.getenv("INSTANTLY_BASE_URL", "https://api.instantly.ai/api/v2")
        )
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if not self.api_key:
            errors.append("INSTANTLY_API_KEY is required")
        return errors


@dataclass
class EmailProviderConfig:
    """Combined email provider configuration."""
    default_provider: EmailProvider = EmailProvider.INSTANTLY
    nylas: Optional[NylasConfig] = None
    instantly: Optional[InstantlyConfig] = None
    enable_dual_mode: bool = False  # Allow using both providers
    
    @classmethod
    def from_env(cls) -> "EmailProviderConfig":
        """Create config from environment variables."""
        default_provider_str = os.getenv("DEFAULT_EMAIL_PROVIDER", "instantly").lower()
        try:
            default_provider = EmailProvider(default_provider_str)
        except ValueError:
            logger.warning(f"Invalid DEFAULT_EMAIL_PROVIDER: {default_provider_str}, using 'instantly'")
            default_provider = EmailProvider.INSTANTLY
        
        return cls(
            default_provider=default_provider,
            nylas=NylasConfig.from_env() if os.getenv("NYLAS_API_KEY") else None,
            instantly=InstantlyConfig.from_env() if os.getenv("INSTANTLY_API_KEY") else None,
            enable_dual_mode=os.getenv("ENABLE_DUAL_EMAIL_MODE", "false").lower() == "true"
        )
    
    def validate(self) -> Dict[str, List[str]]:
        """Validate all configurations and return errors by provider."""
        errors = {}
        
        if self.nylas:
            nylas_errors = self.nylas.validate()
            if nylas_errors:
                errors["nylas"] = nylas_errors
        
        if self.instantly:
            instantly_errors = self.instantly.validate()
            if instantly_errors:
                errors["instantly"] = instantly_errors
        
        # Check if default provider is configured
        if self.default_provider == EmailProvider.NYLAS and not self.nylas:
            errors["config"] = ["Default provider is Nylas but Nylas is not configured"]
        elif self.default_provider == EmailProvider.INSTANTLY and not self.instantly:
            errors["config"] = ["Default provider is Instantly but Instantly is not configured"]
        
        return errors
    
    def is_provider_available(self, provider: EmailProvider) -> bool:
        """Check if a specific provider is configured and available."""
        if provider == EmailProvider.NYLAS:
            return self.nylas is not None and not self.nylas.validate()
        elif provider == EmailProvider.INSTANTLY:
            return self.instantly is not None and not self.instantly.validate()
        return False
    
    def get_available_providers(self) -> List[EmailProvider]:
        """Get list of available providers."""
        providers = []
        if self.is_provider_available(EmailProvider.INSTANTLY):
            providers.append(EmailProvider.INSTANTLY)
        if self.is_provider_available(EmailProvider.NYLAS):
            providers.append(EmailProvider.NYLAS)
        return providers


class EmailProviderManager:
    """Manager for email provider selection and configuration."""
    
    def __init__(self, config: Optional[EmailProviderConfig] = None):
        self.config = config or EmailProviderConfig.from_env()
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration on initialization."""
        errors = self.config.validate()
        if errors:
            logger.warning(f"Email provider configuration errors: {errors}")
            # Don't raise exception, allow graceful degradation
    
    def get_provider_for_campaign(self, campaign_data: Dict[str, Any]) -> EmailProvider:
        """
        Determine which email provider to use for a campaign.
        
        Args:
            campaign_data: Campaign dictionary with provider preferences
            
        Returns:
            EmailProvider enum value
        """
        # Check campaign-specific provider preference
        campaign_provider_str = campaign_data.get("email_provider")
        if campaign_provider_str:
            try:
                provider = EmailProvider(campaign_provider_str)
                if self.config.is_provider_available(provider):
                    return provider
                else:
                    logger.warning(
                        f"Campaign requested {provider.value} but it's not available, "
                        f"falling back to default"
                    )
            except ValueError:
                logger.warning(f"Invalid email provider in campaign: {campaign_provider_str}")
        
        # Check for legacy Instantly campaign
        if campaign_data.get("instantly_campaign_id") and not campaign_data.get("nylas_grant_id"):
            if self.config.is_provider_available(EmailProvider.INSTANTLY):
                return EmailProvider.INSTANTLY
        
        # Check for Nylas grant
        if campaign_data.get("nylas_grant_id"):
            if self.config.is_provider_available(EmailProvider.NYLAS):
                return EmailProvider.NYLAS
        
        # Use default provider
        return self.config.default_provider
    
    def can_migrate_campaign(self, campaign_data: Dict[str, Any]) -> bool:
        """
        Check if a campaign can be migrated from Instantly to Nylas.
        
        Args:
            campaign_data: Campaign dictionary
            
        Returns:
            bool: True if migration is possible
        """
        # Must have Instantly campaign ID
        if not campaign_data.get("instantly_campaign_id"):
            return False
        
        # Must not already have Nylas grant
        if campaign_data.get("nylas_grant_id"):
            return False
        
        # Both providers must be available
        return (
            self.config.is_provider_available(EmailProvider.INSTANTLY) and
            self.config.is_provider_available(EmailProvider.NYLAS)
        )
    
    def get_provider_config(self, provider: EmailProvider) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific provider."""
        if provider == EmailProvider.NYLAS and self.config.nylas:
            return {
                "api_key": self.config.nylas.api_key,
                "api_uri": self.config.nylas.api_uri,
                "webhook_secret": self.config.nylas.webhook_secret,
                "default_grant_id": self.config.nylas.grant_id
            }
        elif provider == EmailProvider.INSTANTLY and self.config.instantly:
            return {
                "api_key": self.config.instantly.api_key,
                "base_url": self.config.instantly.base_url
            }
        return None


# Global instance
email_provider_manager = EmailProviderManager()


# Utility functions for backward compatibility
def get_default_email_provider() -> str:
    """Get the default email provider name."""
    return email_provider_manager.config.default_provider.value


def is_nylas_configured() -> bool:
    """Check if Nylas is configured and available."""
    return email_provider_manager.config.is_provider_available(EmailProvider.NYLAS)


def is_instantly_configured() -> bool:
    """Check if Instantly is configured and available."""
    return email_provider_manager.config.is_provider_available(EmailProvider.INSTANTLY)


def get_email_provider_for_campaign(campaign_id: str) -> str:
    """Get email provider for a campaign (requires database lookup)."""
    # This is a placeholder - in actual use, you'd fetch campaign data first
    # from the database and then call email_provider_manager.get_provider_for_campaign
    return get_default_email_provider()