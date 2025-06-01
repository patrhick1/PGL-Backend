import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class EmailService:
    """Email service for sending password reset and other emails"""
    
    def __init__(self):
        # Configure these via environment variables
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        self.frontend_url = os.getenv('FRONTEND_ORIGIN', 'http://localhost:5173')
        
        # Debug logging
        logger.info(f"Email service initialized:")
        logger.info(f"  SMTP Server: {self.smtp_server}")
        logger.info(f"  SMTP Port: {self.smtp_port}")
        logger.info(f"  SMTP Username: {self.smtp_username}")
        logger.info(f"  From Email: {self.from_email}")
        logger.info(f"  Frontend URL: {self.frontend_url}")
        logger.info(f"  Has Password: {bool(self.smtp_password)}")
    
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
            msg['From'] = self.from_email
            msg['To'] = to_email
            
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
            
            logger.info(f"Password reset email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP error sending email to {to_email}: {e}")
            return False

# Global instance
email_service = EmailService() 