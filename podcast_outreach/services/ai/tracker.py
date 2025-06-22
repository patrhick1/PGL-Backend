# podcast_outreach/services/ai/tracker.py

import os
import csv
import json
import time
import logging
import datetime
import platform
import shutil
from typing import Dict, Any, Optional, List
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv
import uuid # For UUID types

# Import new DB query functions
from podcast_outreach.database.queries import ai_usage as ai_usage_queries
from podcast_outreach.logging_config import get_logger

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

# Constants for cost calculations
COST_RATES = {
    # OpenAI models
    'gpt-4o-2024-08-06': {
        'input': 0.0025,  # Per 1K input tokens
        'output': 0.010  # Per 1K output tokens
    },
    # Anthropic models
    'claude-3-5-haiku-20241022': {
        'input': 0.00025,  # Per 1K input tokens
        'output': 0.00125  # Per 1K output tokens
    },
    'claude-3-5-sonnet-20241022': {
        'input': 0.003,  # Per 1K input tokens
        'output': 0.015  # Per 1K output tokens
    },
    # Google models
    'gemini-2.0-flash': {
        'input': 0.0001,  # Per 1K input tokens
        'output': 0.0004  # Per 1K output tokens
    },
    'gemini-1.5-flash': {
        'input': 0.000075,  # Per 1K input tokens
        'output': 0.0003  # Per 1K output tokens
    },
    'o3-mini': {
        'input': 0.0011,  # Per 1K input tokens
        'output': 0.0044  # Per 1K output tokens
    },
    # Default fallback
    'default': {
        'input': 0.001,
        'output': 0.003
    }
}


class AIUsageTracker:
    """
    A utility class to track and log AI API usage across the application.
    Now logs to PostgreSQL database.
    """
    
    def __init__(self):
        """Initialize the tracker."""
        self.GOOGLE_FOLDER_ID = os.getenv('PGL_AI_DRIVE_FOLDER_ID')
        self.BACKUP_INTERVAL = 3600  # 1 hour in seconds
        self.last_backup_time = None
        self.drive_service = None # Initialize to None

        # No longer managing local CSV directly for primary logging, but keeping for compatibility/fallback
        self.log_file = 'ai_usage_logs_local_backup.csv' # This will be a local backup/debug file
        self.backup_file = 'ai_usage_logs_local_backup_archive.csv'
        self._init_google_drive()
        logger.info("AIUsageTracker initialized. Logging to PostgreSQL.")

    def _init_google_drive(self):
        """Initialize connection to Google Drive."""
        try:
            service_account_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'service-account-key.json')
            if os.path.exists(service_account_path):
                creds = ServiceAccountCredentials.from_service_account_file(
                    service_account_path,
                    scopes=['https://www.googleapis.com/auth/drive.file']
                )
                self.drive_service = build('drive', 'v3', credentials=creds)
                logger.info(f"Connected to Google Drive using service account from: {service_account_path}")
                return
            else:
                logger.warning(f"Service account file not found at: {service_account_path}. Trying OAuth.")

            creds = None
            if os.path.exists('token.json'):
                creds = Credentials.from_authorized_user_file('token.json', 
                    ['https://www.googleapis.com/auth/drive.file'])

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json',
                        ['https://www.googleapis.com/auth/drive.file']
                    )
                    creds = flow.run_local_server(port=0)
                
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())

            self.drive_service = build('drive', 'v3', credentials=creds)
            logger.info("Connected to Google Drive using OAuth")

        except Exception as e:
            logger.error(f"Failed to initialize Google Drive connection: {e}")
            self.drive_service = None

    def _backup_to_drive(self):
        """Backup the local CSV file to Google Drive if enough time has passed."""
        if not self.drive_service or not self.GOOGLE_FOLDER_ID:
            logger.warning("Skipping backup: Drive service or folder ID not available")
            return

        current_time = time.time()
        if (self.last_backup_time and 
            current_time - self.last_backup_time < self.BACKUP_INTERVAL):
            return

        try:
            if not os.path.exists(self.log_file) or os.path.getsize(self.log_file) == 0:
                logger.warning("Skipping backup: Local log file is empty or doesn't exist")
                return

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_metadata = {
                'name': f'ai_usage_logs_{timestamp}.csv',
                'parents': [self.GOOGLE_FOLDER_ID],
                'description': f'AI Usage Logs backup from {timestamp}'
            }

            media = MediaFileUpload(
                self.log_file,
                mimetype='text/csv',
                resumable=True
            )

            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name'
            ).execute()

            logger.info(f"Backed up local AI usage logs to Google Drive: {file.get('name')} (ID: {file.get('id')})")
            self.last_backup_time = current_time

        except Exception as e:
            logger.error(f"Failed to backup local CSV to Google Drive: {e}")

    def calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """
        Calculate the cost of an API call based on the model and token usage.
        """
        model_rates = COST_RATES.get(model, COST_RATES['default'])
        
        input_cost = (tokens_in / 1000) * model_rates['input']
        output_cost = (tokens_out / 1000) * model_rates['output']
        
        return input_cost + output_cost
    
    async def log_usage(self, 
                        workflow: str,
                        model: str, 
                        tokens_in: int, 
                        tokens_out: int, 
                        execution_time: float, 
                        endpoint: str = "unknown",
                        related_pitch_gen_id: Optional[int] = None, # New: Link to pitch generation
                        related_campaign_id: Optional[uuid.UUID] = None, # New: Link to campaign
                        related_media_id: Optional[int] = None # New: Link to media
                       ):
        """
        Log a single AI API usage event to the PostgreSQL database.
        Also maintains a local CSV backup for debugging/redundancy.
        """
        total_tokens = tokens_in + tokens_out
        cost = self.calculate_cost(model, tokens_in, tokens_out)
        timestamp = datetime.datetime.now() # Use datetime object for DB

        log_data = {
            'timestamp': timestamp,
            'workflow': workflow,
            'model': model,
            'tokens_in': tokens_in,
            'tokens_out': tokens_out,
            'total_tokens': total_tokens,
            'cost': cost,
            'execution_time_sec': execution_time,
            'endpoint': endpoint,
            'related_pitch_gen_id': related_pitch_gen_id,
            'related_campaign_id': related_campaign_id,
            'related_media_id': related_media_id
        }
        
        try:
            # Log to PostgreSQL (with retry mechanism)
            db_result = await ai_usage_queries.log_ai_usage_in_db(log_data)
            if db_result is None:
                logger.warning(f"Failed to log AI usage to database for workflow {workflow}, but continuing...")
            
            # Log to local CSV (for immediate local debugging/backup)
            with open(self.log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                # Write header if file is new/empty
                if f.tell() == 0:
                    writer.writerow([
                        'timestamp', 'workflow', 'model', 'tokens_in', 
                        'tokens_out', 'total_tokens', 'cost', 
                        'execution_time_sec', 'endpoint', 'related_pitch_gen_id',
                        'related_campaign_id', 'related_media_id'
                    ])
                writer.writerow([
                    timestamp.isoformat(), workflow, model, tokens_in, 
                    tokens_out, total_tokens, f"{cost:.6f}", 
                    f"{execution_time:.3f}", endpoint, related_pitch_gen_id,
                    str(related_campaign_id) if related_campaign_id else None, related_media_id
                ])
            
            # Attempt to backup to Google Drive (from local CSV)
            self._backup_to_drive()
            
            # Also log to console for immediate visibility
            related_info = f" | PitchGen: {related_pitch_gen_id}" if related_pitch_gen_id else ""
            related_info += f" | Campaign: {related_campaign_id}" if related_campaign_id else ""
            related_info += f" | Media: {related_media_id}" if related_media_id else ""

            logger.info(
                f"AI Usage: {workflow} | {model} | Tokens: {tokens_in}+{tokens_out}={total_tokens} | "
                f"Cost: ${cost:.6f} | Time: {execution_time:.3f}s{related_info}"
            )
            
            return {
                'timestamp': timestamp.isoformat(),
                'workflow': workflow,
                'model': model,
                'tokens_in': tokens_in,
                'tokens_out': tokens_out,
                'total_tokens': total_tokens,
                'cost': cost,
                'execution_time': execution_time,
                'endpoint': endpoint,
                'related_pitch_gen_id': related_pitch_gen_id,
                'related_campaign_id': related_campaign_id,
                'related_media_id': related_media_id
            }
        except Exception as e:
            logger.error(f"Error logging AI usage to CSV: {e}", exc_info=True)
            # Don't raise - allow the calling process to continue even if logging fails
    
    async def generate_report(self, 
                              start_date: Optional[str] = None, 
                              end_date: Optional[str] = None,
                              group_by: str = 'model') -> Dict[str, Any]:
        """
        Generate a summary report of AI usage from the database within a date range.
        """
        start_dt = datetime.datetime.fromisoformat(start_date).date() if start_date else None
        end_dt = datetime.datetime.fromisoformat(end_date).date() if end_date else None

        # Fetch grouped data
        grouped_data = await ai_usage_queries.get_ai_usage_logs(
            start_date=start_dt,
            end_date=end_dt,
            group_by_column=group_by
        )

        # Fetch total data
        total_data = await ai_usage_queries.get_total_ai_usage(
            start_date=start_dt,
            end_date=end_dt
        )
        
        # Format grouped data for report
        groups = {}
        for row in grouped_data:
            group_key = str(row[group_by]) if row[group_by] is not None else "N/A"
            groups[group_key] = {
                'calls': row['calls'],
                'tokens_in': row['tokens_in'],
                'tokens_out': row['tokens_out'],
                'total_tokens': row['total_tokens'],
                'cost': float(row['cost']),
                'avg_time': float(row['avg_execution_time_sec']) if row['avg_execution_time_sec'] is not None else 0.0
            }
        
        report = {
            "start_date": start_date,
            "end_date": end_date,
            "total_entries": total_data['total_calls'],
            "total_tokens": total_data['total_tokens'],
            "total_cost": float(total_data['total_cost']),
            "grouped_by": group_by,
            "groups": groups
        }
        
        return report
    
    async def get_record_cost_report(self, pitch_gen_id: int) -> Dict[str, Any]:
        """
        Generate a detailed cost report for a specific pitch generation ID.
        """
        # Fetch all logs related to this pitch_gen_id
        related_logs = await ai_usage_queries.get_ai_usage_logs(
            related_pitch_gen_id=pitch_gen_id
        )

        if not related_logs:
            return {
                "pitch_gen_id": pitch_gen_id,
                "status": "not_found",
                "message": f"No usage data found for pitch generation ID {pitch_gen_id}"
            }
        
        # Calculate totals
        total_cost = sum(float(entry['cost']) for entry in related_logs)
        total_tokens_in = sum(entry['tokens_in'] for entry in related_logs)
        total_tokens_out = sum(entry['tokens_out'] for entry in related_logs)
        total_tokens = sum(entry['total_tokens'] for entry in related_logs)
        total_calls = len(related_logs)
        
        # Group by workflow stage
        stages = {}
        for entry in related_logs:
            workflow = entry['workflow']
            if workflow not in stages:
                stages[workflow] = {
                    'calls': 0,
                    'tokens_in': 0,
                    'tokens_out': 0,
                    'total_tokens': 0,
                    'cost': 0.0
                }
            
            stages[workflow]['calls'] += 1
            stages[workflow]['tokens_in'] += entry['tokens_in']
            stages[workflow]['tokens_out'] += entry['tokens_out']
            stages[workflow]['total_tokens'] += entry['total_tokens']
            stages[workflow]['cost'] += float(entry['cost'])
        
        # Create timeline of operations
        timeline = []
        for entry in sorted(related_logs, key=lambda x: x['timestamp']):
            timeline.append({
                'timestamp': entry['timestamp'].isoformat(),
                'workflow': entry['workflow'],
                'model': entry['model'],
                'tokens_in': entry['tokens_in'],
                'tokens_out': entry['tokens_out'],
                'total_tokens': entry['total_tokens'],
                'cost': float(entry['cost'])
            })
        
        report = {
            "pitch_gen_id": pitch_gen_id,
            "total_cost": total_cost,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_tokens": total_tokens,
            "total_calls": total_calls,
            "workflow_stages": stages,
            "timeline": timeline
        }
        
        return report

# Create a global instance that can be imported throughout the application
tracker = AIUsageTracker()# Placeholder for AI usage tracker 
