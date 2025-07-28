import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class EmailService:
    """Email service for sending transactional emails"""
    
    def __init__(self):
        # Configure these via environment variables
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        self.from_name = os.getenv('EMAIL_FROM_NAME', 'PGL System')
        self.frontend_url = os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173')
        self.support_email = os.getenv('EMAIL_SUPPORT_ADDRESS', 'support@podcastguestlaunch.com')
        
        # Debug logging
        logger.info(f"Email service initialized for from_email: {self.from_email}")
    
    async def send_password_reset_email(self, to_email: str, reset_token: str) -> bool:
        """Send password reset email with reset link"""
        try:
            # Create reset URL
            reset_url = f"{self.frontend_url}/reset-password?token={reset_token}"
            
            # Email content
            subject = "Reset Your Password - PGL System"
            
            html_body = f"""
            <html>
            <body>
                <h2>Password Reset Request</h2>
                <p>Hello,</p>
                <p>We received a request to reset your password for your PGL System account.</p>
                <p>Click the link below to reset your password:</p>
                <p><a href="{reset_url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
                <p>Or copy and paste this link into your browser:</p>
                <p>{reset_url}</p>
                <p><strong>This link will expire in 30 minutes.</strong></p>
                <p>If you didn't request this password reset, please ignore this email or contact support if you have concerns.</p>
                <p>Best regards,<br>The PGL System Team</p>
            </body>
            </html>
            """
            
            text_body = f"""
            Password Reset Request
            
            Hello,
            
            We received a request to reset your password for your PGL System account.
            
            Visit this link to reset your password:
            {reset_url}
            
            This link will expire in 30 minutes.
            
            If you didn't request this password reset, please ignore this email.
            
            Best regards,
            The PGL System Team
            """
            
            return await self._send_email(to_email, subject, html_body, text_body)
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {to_email}: {e}")
            return False
    
    async def _send_email(self, to_email: str, subject: str, html_body: str, text_body: str) -> bool:
        """Send email using SMTP"""
        try:
            # Validate credentials
            if not self.smtp_username or not self.smtp_password:
                logger.error("SMTP credentials not configured properly")
                return False
                
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            # Format the From field with name and email
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            # Add Reply-To header
            msg['Reply-To'] = self.from_email
            
            # Add text and HTML parts
            text_part = MIMEText(text_body, 'plain')
            html_part = MIMEText(html_body, 'html')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP error sending email to {to_email}: {e}")
            return False
    
    async def send_verification_email(self, to_email: str, token: str, full_name: str) -> bool:
        """Send email verification email"""
        try:
            # Create verification URL
            verify_url = f"{self.frontend_url}/verify-email?token={token}"
            
            # Email content
            subject = "Verify your email - PGL System"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #007bff;">Verify Your Email Address</h2>
                    <p>Hi {full_name},</p>
                    <p>Thanks for signing up for Podcast Guest Launch! Please verify your email address to activate your account.</p>
                    <p style="margin: 30px 0;">
                        <a href="{verify_url}" style="background-color: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">Verify Email Address</a>
                    </p>
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #007bff;">{verify_url}</p>
                    <p><strong>This link will expire in 24 hours.</strong></p>
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    <p style="color: #666; font-size: 14px;">If you didn't create an account with PGL System, please ignore this email.</p>
                    <p style="color: #666; font-size: 14px;">Need help? Contact us at {self.support_email}</p>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            Verify Your Email Address
            
            Hi {full_name},
            
            Thanks for signing up for Podcast Guest Launch! Please verify your email address to activate your account.
            
            Visit this link to verify your email:
            {verify_url}
            
            This link will expire in 24 hours.
            
            If you didn't create an account with PGL System, please ignore this email.
            
            Need help? Contact us at {self.support_email}
            
            Best regards,
            The PGL Team
            """
            
            return await self._send_email(to_email, subject, html_body, text_body)
            
        except Exception as e:
            logger.error(f"Failed to send verification email to {to_email}: {e}")
            return False
    
    async def send_welcome_email(self, to_email: str, full_name: str, campaign_id: str, campaign_name: str) -> bool:
        """Send welcome/onboarding email after email verification"""
        try:
            # Email content
            subject = "Welcome to PGL! Let's get you started 🚀"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #007bff;">Welcome to Podcast Guest Launch!</h2>
                    <p>Hi {full_name},</p>
                    <p>Your email has been verified and your account is ready. Here's how to get started:</p>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">1. Complete Your Profile</h3>
                        <p>Set up your guest profile to help podcasters understand your expertise.</p>
                        <a href="{self.frontend_url}/profile" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Complete Profile</a>
                    </div>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">2. Start Your First Campaign</h3>
                        <p>Your first campaign "{campaign_name}" has been created for you.</p>
                        <a href="{self.frontend_url}/campaigns/{campaign_id}" style="background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">View Campaign</a>
                    </div>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">3. Discover Podcasts</h3>
                        <p>Find podcasts that match your expertise and audience.</p>
                        <a href="{self.frontend_url}/discovery" style="background-color: #17a2b8; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Start Discovery</a>
                    </div>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    
                    <p><strong>Need help?</strong> Check out our:</p>
                    <ul>
                        <li><a href="{self.frontend_url}/help/getting-started" style="color: #007bff;">Getting Started Guide</a></li>
                        <li><a href="{self.frontend_url}/help/video-tutorial" style="color: #007bff;">Video Tutorial</a></li>
                    </ul>
                    
                    <p>Questions? Reply to this email and we'll help you out.</p>
                    
                    <p style="color: #666; font-size: 14px;">Best regards,<br>The PGL Team</p>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            Welcome to Podcast Guest Launch!
            
            Hi {full_name},
            
            Your email has been verified and your account is ready. Here's how to get started:
            
            1. Complete Your Profile
               Set up your guest profile to help podcasters understand your expertise.
               Visit: {self.frontend_url}/profile
            
            2. Start Your First Campaign
               Your first campaign "{campaign_name}" has been created for you.
               Visit: {self.frontend_url}/campaigns/{campaign_id}
            
            3. Discover Podcasts
               Find podcasts that match your expertise and audience.
               Visit: {self.frontend_url}/discovery
            
            Need help? Check out our:
            - Getting Started Guide: {self.frontend_url}/help/getting-started
            - Video Tutorial: {self.frontend_url}/help/video-tutorial
            
            Questions? Reply to this email and we'll help you out.
            
            Best regards,
            The PGL Team
            """
            
            return await self._send_email(to_email, subject, html_body, text_body)
            
        except Exception as e:
            logger.error(f"Failed to send welcome email to {to_email}: {e}")
            return False
    
    async def send_campaign_created_email(self, to_email: str, full_name: str, campaign_id: str, campaign_name: str) -> bool:
        """Send campaign created notification (for OAuth users who skip email verification)"""
        try:
            # Email content
            subject = "Your campaign is ready! Next steps inside →"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #007bff;">Your Campaign is Ready!</h2>
                    <p>Hi {full_name},</p>
                    <p>Great news! We've created your first campaign: <strong>"{campaign_name}"</strong></p>
                    
                    <h3>What's next?</h3>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h4 style="margin-top: 0;">1. Set Your Campaign Goals</h4>
                        <p>Define what podcasts you're looking for.</p>
                        <a href="{self.frontend_url}/campaigns/{campaign_id}/settings" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Configure Campaign</a>
                    </div>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h4 style="margin-top: 0;">2. Start Discovery</h4>
                        <p>Find your first 10 podcasts (free plan limit).</p>
                        <a href="{self.frontend_url}/campaigns/{campaign_id}/discovery" style="background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Discover Podcasts</a>
                    </div>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h4 style="margin-top: 0;">3. Craft Your Pitch</h4>
                        <p>Create a compelling pitch template.</p>
                        <a href="{self.frontend_url}/campaigns/{campaign_id}/pitches" style="background-color: #17a2b8; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Create Pitch</a>
                    </div>
                    
                    <p style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
                        <strong>Pro tip:</strong> Complete your profile first to increase your chances of getting booked!
                    </p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    
                    <p style="color: #666; font-size: 14px;">Happy podcasting!<br>The PGL Team</p>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            Your Campaign is Ready!
            
            Hi {full_name},
            
            Great news! We've created your first campaign: "{campaign_name}"
            
            What's next?
            
            1. Set Your Campaign Goals
               Define what podcasts you're looking for.
               Visit: {self.frontend_url}/campaigns/{campaign_id}/settings
            
            2. Start Discovery
               Find your first 10 podcasts (free plan limit).
               Visit: {self.frontend_url}/campaigns/{campaign_id}/discovery
            
            3. Craft Your Pitch
               Create a compelling pitch template.
               Visit: {self.frontend_url}/campaigns/{campaign_id}/pitches
            
            Pro tip: Complete your profile first to increase your chances of getting booked!
            
            Happy podcasting!
            The PGL Team
            """
            
            return await self._send_email(to_email, subject, html_body, text_body)
            
        except Exception as e:
            logger.error(f"Failed to send campaign created email to {to_email}: {e}")
            return False
    
    async def send_onboarding_invitation_email(self, to_email: str, full_name: str, token: str, campaign_name: str, created_by: str = 'system') -> bool:
        """Send onboarding invitation email with secure token"""
        try:
            # Create onboarding URL
            onboarding_url = f"{self.frontend_url}/onboarding?token={token}"
            
            # Customize message based on who created it
            if created_by == 'admin':
                intro_text = "Great news! Your Podcast Guest Launch account has been set up by our team."
            else:
                intro_text = "Welcome to Podcast Guest Launch! Your account is ready and we're excited to help you get booked on podcasts."
            
            # Email content
            subject = "Welcome to PGL! Complete your onboarding to get started 🎙️"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #007bff;">Welcome to Podcast Guest Launch!</h2>
                    <p>Hi {full_name},</p>
                    <p>{intro_text}</p>
                    
                    <p>We've created your first campaign: <strong>"{campaign_name}"</strong></p>
                    
                    <div style="background-color: #f8f9fa; padding: 25px; border-radius: 8px; margin: 30px 0; text-align: center;">
                        <p style="margin-bottom: 20px; font-size: 18px;"><strong>Click below to complete your onboarding:</strong></p>
                        <a href="{onboarding_url}" style="background-color: #007bff; color: white; padding: 15px 40px; text-decoration: none; border-radius: 5px; display: inline-block; font-size: 16px; font-weight: bold;">Start Onboarding</a>
                    </div>
                    
                    <p>This personalized link will:</p>
                    <ul>
                        <li>✓ Automatically log you into your account</li>
                        <li>✓ Guide you through setting up your profile</li>
                        <li>✓ Help you configure your campaign for success</li>
                        <li>✓ Show you how to discover and pitch podcasts</li>
                    </ul>
                    
                    <p style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
                        <strong>Important:</strong> This link expires in 7 days for security reasons. If it expires, simply contact us for a new one.
                    </p>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #007bff; font-size: 14px;">{onboarding_url}</p>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    
                    <p><strong>What happens next?</strong></p>
                    <p>The onboarding process takes about 10-15 minutes and will help you:</p>
                    <ol>
                        <li>Complete your guest profile</li>
                        <li>Define your podcast goals</li>
                        <li>Set up your pitch templates</li>
                        <li>Learn how to use our discovery tools</li>
                    </ol>
                    
                    <p>Questions? Reply to this email or reach out to {self.support_email}</p>
                    
                    <p style="color: #666; font-size: 14px;">Looking forward to helping you get booked on amazing podcasts!</p>
                    <p style="color: #666; font-size: 14px;">The PGL Team</p>
                </div>
            </body>
            </html>
            """
            
            text_body = f"""
            Welcome to Podcast Guest Launch!
            
            Hi {full_name},
            
            {intro_text}
            
            We've created your first campaign: "{campaign_name}"
            
            Click here to complete your onboarding:
            {onboarding_url}
            
            This personalized link will:
            - Automatically log you into your account
            - Guide you through setting up your profile
            - Help you configure your campaign for success
            - Show you how to discover and pitch podcasts
            
            Important: This link expires in 7 days for security reasons. If it expires, simply contact us for a new one.
            
            What happens next?
            The onboarding process takes about 10-15 minutes and will help you:
            1. Complete your guest profile
            2. Define your podcast goals
            3. Set up your pitch templates
            4. Learn how to use our discovery tools
            
            Questions? Reply to this email or reach out to {self.support_email}
            
            Looking forward to helping you get booked on amazing podcasts!
            
            The PGL Team
            """
            
            return await self._send_email(to_email, subject, html_body, text_body)
            
        except Exception as e:
            logger.error(f"Failed to send onboarding invitation email to {to_email}: {e}")
            return False

# Global instance
email_service = EmailService() 