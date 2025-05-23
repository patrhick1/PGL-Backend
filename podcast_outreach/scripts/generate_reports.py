# podcast_outreach/scripts/generate_reports.py

import os
import sys
import json
import argparse
import datetime
from pathlib import Path
from tabulate import tabulate
from typing import Optional, Dict, Any, List
import asyncio
from collections import Counter, defaultdict
from datetime import date, timedelta

# Import the tracker from the new location
from podcast_outreach.services.ai.tracker import tracker
from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import init_db_pool, close_db_pool # <--- UPDATED IMPORT

# Import new DB query functions for campaign status
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import placements as placement_queries # Now exists
from podcast_outreach.database.queries import people as people_queries # Now exists

logger = get_logger(__name__)

# --- AI Usage Report Functions ---

def format_as_text(report: Dict[str, Any]) -> str:
    """Format the report as human-readable text."""
    text_output = []
    
    # Header
    text_output.append("=" * 60)
    text_output.append("AI USAGE REPORT")
    text_output.append("=" * 60)
    
    # Special handling for pitch_gen_id-specific reports
    if "pitch_gen_id" in report:
        text_output.append(f"Pitch Generation ID: {report['pitch_gen_id']}")
        text_output.append("-" * 60)
        text_output.append(f"Total API calls: {report['total_calls']}")
        text_output.append(f"Total tokens: {report['total_tokens']:,}")
        text_output.append(f"Total cost: ${report['total_cost']:.4f}")
        text_output.append("-" * 60)
        
        # Workflow stages breakdown
        text_output.append("\nBreakdown by workflow stage:")
        text_output.append("-" * 60)
        
        table_data = []
        for stage, stats in report['workflow_stages'].items():
            table_data.append([
                stage, 
                stats['calls'],
                f"{stats['total_tokens']:,}",
                f"${stats['cost']:.4f}"
            ])
        
        headers = ["Workflow Stage", "Calls", "Tokens", "Cost"]
        text_output.append(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Timeline of operations
        text_output.append("\nTimeline of operations:")
        text_output.append("-" * 60)
        
        timeline_data = []
        for entry in report['timeline']:
            timeline_data.append([
                entry['timestamp'],
                entry['workflow'],
                entry['model'],
                f"{entry['total_tokens']:,}",
                f"${entry['cost']:.4f}"
            ])
        
        timeline_headers = ["Timestamp", "Workflow", "Model", "Tokens", "Cost"]
        text_output.append(tabulate(timeline_data, headers=timeline_headers, tablefmt="grid"))
        
        return "\n".join(text_output)
    
    # Standard report format
    date_range = f"Date range: "
    if report.get("start_date"):
        date_range += f"From {report['start_date']} "
    if report.get("end_date"):
        date_range += f"To {report['end_date']} "
    if not report.get("start_date") and not report.get("end_date"):
        date_range += "All time"
    text_output.append(date_range)
    
    # Summary stats
    text_output.append("-" * 60)
    text_output.append(f"Total API calls: {report['total_entries']}")
    text_output.append(f"Total tokens: {report['total_tokens']:,}")
    text_output.append(f"Total cost: ${report['total_cost']:.2f}")
    text_output.append("-" * 60)
    
    # Group details
    text_output.append(f"\nBreakdown by {report['grouped_by']}:")
    text_output.append("-" * 60)
    
    table_data = []
    for group_name, stats in report['groups'].items():
        table_data.append([
            group_name, 
            stats['calls'],
            f"{stats['tokens_in']:,}",
            f"{stats['tokens_out']:,}",
            f"{stats['total_tokens']:,}",
            f"${stats['cost']:.2f}",
            f"{stats['avg_time']:.2f} sec"
        ])
    
    headers = ["Name", "Calls", "Input Tokens", "Output Tokens", "Total Tokens", "Cost", "Avg Time"]
    text_output.append(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    return "\n".join(text_output)


def format_as_csv(report: Dict[str, Any]) -> str:
    """Format the report as CSV."""
    csv_output = []
    
    # Special handling for pitch_gen_id-specific reports
    if "pitch_gen_id" in report:
        csv_output.append("Pitch Generation ID,Workflow Stage,Calls,Tokens,Cost")
        
        for stage, stats in report['workflow_stages'].items():
            csv_output.append(
                f"{report['pitch_gen_id']},{stage},{stats['calls']}," +
                f"{stats['total_tokens']},{stats['cost']:.6f}"
            )
        
        csv_output.append(f"{report['pitch_gen_id']},TOTAL,{report['total_calls']}," +
                         f"{report['total_tokens']},{report['total_cost']:.6f}")
        
        return "\n".join(csv_output)
    
    # Standard report format
    csv_output.append(f"{report['grouped_by']},Calls,Input Tokens,Output Tokens,Total Tokens,Cost,Avg Time (sec)")
    
    for group_name, stats in report['groups'].items():
        csv_output.append(
            f"{group_name},{stats['calls']},{stats['tokens_in']},{stats['tokens_out']}," +
            f"{stats['total_tokens']},{stats['cost']:.6f},{stats['avg_time']:.3f}"
        )
    
    csv_output.append(f"TOTAL,{report['total_entries']},,," +
                     f"{report['total_tokens']},{report['total_cost']:.6f},")
    
    return "\n".join(csv_output)


# --- Campaign Status Reporter (New Class) ---

class CampaignStatusReporter:
    """
    Generates status reports for campaigns, fetching data from PostgreSQL.
    """
    def __init__(self):
        # GoogleSheetsService is still needed for writing reports
        from src.google_sheets_service import GoogleSheetsService # Assuming this path is correct
        self.sheets_service = GoogleSheetsService()

        # Google Drive/Sheets Config (from original campaign_status_tracker.py)
        self.CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID = os.getenv('CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID')
        if not self.CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID:
            logger.error("CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID environment variable not set.")
            raise ValueError("CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID is required.")
        
        # Initialize Google Drive service for finding/moving spreadsheets
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        SHEETS_API_SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file'
        ]
        if not SERVICE_ACCOUNT_FILE:
            logger.error("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS is required for Google Drive access.")
        
        try:
            drive_credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SHEETS_API_SCOPES)
            self.drive_service = build('drive', 'v3', credentials=drive_credentials)
            logger.info("CampaignStatusReporter initialized with Sheets and Drive services.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive/Sheets credentials: {e}")
            raise

    async def _find_spreadsheet_in_folder(self, name: str, folder_id: str) -> Optional[str]:
        """Finds a spreadsheet by name within a specific Google Drive folder."""
        safe_name = name.replace("'", "\\'")
        query = f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and '{folder_id}' in parents and trashed = false"
        try:
            # Use asyncio.to_thread for blocking API calls
            response = await asyncio.to_thread(self.drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute)
            files = response.get('files', [])
            if files:
                logger.info(f"Found spreadsheet '{name}' with ID {files[0]['id']} in folder '{folder_id}'.")
                return files[0]['id']
            return None
        except Exception as e:
            logger.error(f"Error finding spreadsheet '{name}' in folder '{folder_id}': {e}")
            return None

    async def _get_or_create_spreadsheet_for_client(self, client_name: str) -> Optional[str]:
        """Gets existing or creates new spreadsheet for the client."""
        spreadsheet_title = f"{client_name} - Campaign Status Tracker"
        spreadsheet_id = await self._find_spreadsheet_in_folder(spreadsheet_title, self.CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID)

        if spreadsheet_id:
            return spreadsheet_id
        else:
            logger.info(f"Creating new spreadsheet titled '{spreadsheet_title}'...")
            new_sheet_id = await asyncio.to_thread(self.sheets_service.create_spreadsheet, title=spreadsheet_title)
            if new_sheet_id:
                logger.info(f"Spreadsheet created with ID: {new_sheet_id}. Moving to folder {self.CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID}...")
                try:
                    file_metadata = await asyncio.to_thread(self.drive_service.files().get, fileId=new_sheet_id, fields='parents')
                    file_metadata = file_metadata.execute()
                    previous_parents = ",".join(file_metadata.get('parents', []))
                    await asyncio.to_thread(self.drive_service.files().update,
                        fileId=new_sheet_id,
                        addParents=self.CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID,
                        removeParents=previous_parents if previous_parents else None,
                        fields='id, parents'
                    )
                    return new_sheet_id
                except Exception as e:
                    logger.error(f"Error moving spreadsheet {new_sheet_id} to folder {self.CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID}: {e}")
                    return None
            else:
                logger.error(f"Failed to create spreadsheet for {client_name} via GoogleSheetsService.")
                return None

    def _get_week_date_ranges(self, num_weeks: int) -> List[Dict[str, date]]:
        """Generates date ranges (Monday to Sunday) for the last num_weeks."""
        today = date.today()
        start_of_current_week = today - timedelta(days=today.weekday())
        
        date_ranges = []
        for i in range(num_weeks):
            week_start = start_of_current_week - timedelta(weeks=i)
            week_end = week_start + timedelta(days=6)
            date_ranges.append({"start": week_start, "end": week_end})
        
        return date_ranges[::-1] # Return in chronological order (oldest first)

    async def _calculate_weekly_metrics(self, client_campaigns: List[Dict[str, Any]], weekly_ranges: List[Dict[str, date]]) -> List[Dict[str, Any]]:
        """
        Calculates status counts for each week for a specific client based on PostgreSQL data.
        """
        weekly_data = []

        # Fetch all pitches and placements related to these campaigns
        all_pitches = []
        all_placements = []
        for campaign in client_campaigns:
            campaign_id = campaign['campaign_id']
            # Assuming these queries exist and return lists of dicts
            pitches_for_campaign = await pitch_queries.get_pitches_for_campaign(campaign_id)
            placements_for_campaign = await placement_queries.get_placements_for_campaign(campaign_id)
            all_pitches.extend(pitches_for_campaign)
            all_placements.extend(placements_for_campaign)

        # Define the statuses to track and how they map from DB fields
        STATUS_MAPPING = {
            "Messages sent": {"table": "pitches", "field": "send_ts", "status_field": "pitch_state", "status_value": "sent"},
            "Total replies": {"table": "pitches", "field": "reply_ts", "status_field": "reply_bool", "status_value": True},
            "Positive replies": {"table": "pitches", "field": "reply_ts", "status_field": "pitch_state", "status_value": "replied_interested"}, # Example custom status
            "Form Submitted": {"table": "placements", "field": "created_at", "status_field": "current_status", "status_value": "form_submitted"}, # Example
            "Meetings booked": {"table": "placements", "field": "meeting_date", "status_field": "current_status", "status_value": "meeting_booked"},
            "Lost": {"table": "pitches", "field": "send_ts", "status_field": "pitch_state", "status_value": "lost"}, # Example
        }
        
        for week in weekly_ranges:
            week_start = week["start"]
            week_end = week["end"]
            
            status_counts = Counter()
            total_pitches_sent_in_week = 0
            
            # Count pitches
            for pitch in all_pitches:
                pitch_send_date = pitch.get('send_ts')
                if pitch_send_date and isinstance(pitch_send_date, datetime):
                    pitch_send_date = pitch_send_date.date()
                    if week_start <= pitch_send_date <= week_end:
                        # Count total pitches sent
                        total_pitches_sent_in_week += 1
                        
                        # Count specific statuses
                        for display_name, mapping in STATUS_MAPPING.items():
                            if mapping["table"] == "pitches":
                                if mapping["status_field"] == "pitch_state" and pitch.get("pitch_state") == mapping["status_value"]:
                                    status_counts[display_name] += 1
                                elif mapping["status_field"] == "reply_bool" and pitch.get("reply_bool") == mapping["status_value"]:
                                    status_counts[display_name] += 1
                                # Add more conditions for other pitch fields if needed

            # Count placements (e.g., for "Form Submitted", "Meetings booked")
            for placement in all_placements:
                placement_date = placement.get('status_ts') # Or specific date field like meeting_date
                if placement_date and isinstance(placement_date, datetime):
                    placement_date = placement_date.date()
                    if week_start <= placement_date <= week_end:
                        for display_name, mapping in STATUS_MAPPING.items():
                            if mapping["table"] == "placements":
                                if mapping["status_field"] == "current_status" and placement.get("current_status") == mapping["status_value"]:
                                    status_counts[display_name] += 1
                                # Add more conditions for other placement fields if needed

            weekly_data.append({
                "week_start": week_start,
                "week_end": week_end,
                "status_counts": status_counts,
                "total_records": total_pitches_sent_in_week # Using pitches sent as total for now
            })
            
        return weekly_data

    def _prepare_sheet_data(self, weekly_metric_data: List[Dict[str, Any]]) -> List[List[Any]]:
        """Formats the aggregated weekly data for writing to Google Sheets."""
        
        # Define the order and mapping for rows in the sheet
        REPORT_ROW_ORDER = [
            {"display_name": "Messages sent", "source_status": "Messages sent"},
            {"display_name": "Total replies", "source_status": "Total replies"},
            {"display_name": "Positive replies", "source_status": "Positive replies"},
            {"display_name": "Form Submitted", "source_status": "Form Submitted"},
            {"display_name": "Meetings booked", "source_status": "Meetings booked"},
            {"display_name": "Lost", "source_status": "Lost"},
        ]

        # Create headers
        headers = ["Metric / Status"] + [f"Week of {wd['week_start']:%m/%d/%y}" for wd in weekly_metric_data]
        data_rows = [headers]
        
        # Add rows for each metric/status defined in REPORT_ROW_ORDER
        for row_info in REPORT_ROW_ORDER:
            display_name = row_info["display_name"]
            source_status = row_info["source_status"] # This is the key in status_counts
            row_data = [display_name]
            for weekly_stats in weekly_metric_data:
                count = weekly_stats["status_counts"].get(source_status, 0)
                row_data.append(count)
            data_rows.append(row_data)
            
        # Add a gap for visual separation (optional)
        data_rows.append(["---"] * len(headers)) 
        
        # Add total row
        total_row = ["Total Pitches Sent This Week"] # Adjusted label
        for weekly_stats in weekly_metric_data:
            total_row.append(weekly_stats["total_records"])
        data_rows.append(total_row)
        
        return data_rows

    async def update_all_client_spreadsheets(self):
        """Main method to fetch records, group by client, calculate weekly metrics, and update sheets."""
        logger.info("Starting campaign status tracking update (Weekly Format)...")
        
        # Fetch all campaigns from PostgreSQL
        all_campaigns = await campaign_queries.get_all_campaigns_from_db()

        if not all_campaigns:
            logger.info("No campaigns found in PostgreSQL. Exiting.")
            return

        logger.info(f"Found {len(all_campaigns)} total campaigns. Grouping by client name...")

        # Group campaigns by client (person_id)
        campaigns_by_client: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for campaign in all_campaigns:
            person_id = campaign.get('person_id')
            if person_id:
                campaigns_by_client[person_id].append(campaign)
            else:
                logger.warning(f"Skipping campaign {campaign.get('campaign_id')} due to missing person_id.")

        if not campaigns_by_client:
            logger.warning("No campaigns with valid client links found after grouping. Exiting.")
            return

        logger.info(f"Processing {len(campaigns_by_client)} distinct clients.")

        # Get date ranges for the weeks to report
        WEEKS_TO_REPORT = 5 # Current week + previous 4 weeks
        weekly_ranges = self._get_week_date_ranges(WEEKS_TO_REPORT)
        logger.info(f"Reporting for weeks starting: {[r['start'] for r in weekly_ranges]}")

        # Iterate through each client group and update/create spreadsheet
        for person_id, client_campaigns in campaigns_by_client.items():
            # Fetch client name from the person_id
            person_data = await people_queries.get_person_by_id_from_db(person_id)
            client_name = person_data.get('full_name') if person_data else f"Client {person_id}"

            logger.info(f"\nProcessing client: {client_name} (Person ID: {person_id})")

            spreadsheet_id = await self._get_or_create_spreadsheet_for_client(client_name)
            if not spreadsheet_id:
                logger.error(f"Could not get or create spreadsheet for {client_name}. Skipping.")
                continue

            logger.info(f"Calculating weekly metrics for {len(client_campaigns)} campaigns for {client_name}.")
            weekly_metric_data = await self._calculate_weekly_metrics(client_campaigns, weekly_ranges)

            if not weekly_metric_data:
                 logger.info(f"No weekly data calculated for {client_name}. Skipping sheet update.")
                 continue

            sheet_data = self._prepare_sheet_data(weekly_metric_data)

            logger.info(f"Writing data to spreadsheet for {client_name} (Sheet ID: {spreadsheet_id})")
            try:
                await asyncio.to_thread(self.sheets_service.write_sheet, spreadsheet_id, "Sheet1!A1", sheet_data)
                logger.info(f"Successfully updated spreadsheet for {client_name}.")
            except Exception as e:
                logger.error(f"Error writing to spreadsheet for {client_name} (ID: {spreadsheet_id}): {e}")

        logger.info("\nCampaign status tracking update finished.")


# --- Main Execution Block for Script ---
async def main_reports_async():
    """Main entry point for running reports from the command line."""
    parser = argparse.ArgumentParser(description="Generate various reports for Podcast Outreach.")
    parser.add_argument("report_type", choices=["ai_usage", "campaign_status"], help="Type of report to generate.")
    
    # Add common arguments for AI usage report
    parser.add_argument(
        "--start-date", type=str, help="Start date for AI usage report (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date", type=str, help="End date for AI usage report (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--group-by", type=str, default="model", 
        choices=["model", "workflow", "endpoint", "related_pitch_gen_id", "related_campaign_id", "related_media_id"],
        help="Group AI usage results by this field"
    )
    parser.add_argument(
        "--format", type=str, default="text", choices=["text", "json", "csv"],
        help="Output format for AI usage report"
    )
    parser.add_argument(
        "--output", type=str, help="File to write AI usage report to (default: stdout)"
    )
    parser.add_argument(
        "--pitch-gen-id", type=int, help="Pitch Generation ID for AI usage report"
    )

    args = parser.parse_args()

    await init_db_pool() # Initialize DB pool once for all reports

    try:
        if args.report_type == "ai_usage":
            report_args = argparse.Namespace(
                start_date=args.start_date,
                end_date=args.end_date,
                group_by=args.group_by,
                format=args.format,
                output=args.output,
                pitch_gen_id=args.pitch_gen_id
            )
            
            if report_args.pitch_gen_id:
                report = await tracker.get_record_cost_report(report_args.pitch_gen_id)
            else:
                report = await tracker.generate_report(
                    start_date=report_args.start_date,
                    end_date=report_args.end_date,
                    group_by=report_args.group_by
                )
            
            if "error" in report:
                logger.error(f"Error generating AI usage report: {report['error']}")
                sys.exit(1)
            
            output_content = ""
            if report_args.format == "text":
                output_content = format_as_text(report)
            elif report_args.format == "json":
                output_content = json.dumps(report, indent=2)
            elif report_args.format == "csv":
                output_content = format_as_csv(report)
            
            if report_args.output:
                with open(report_args.output, "w") as f:
                    f.write(output_content)
                logger.info(f"AI usage report written to {report_args.output}")
            else:
                print(output_content)

        elif args.report_type == "campaign_status":
            reporter = CampaignStatusReporter()
            await reporter.update_all_client_spreadsheets()
            logger.info("Campaign status report generation completed.")

    finally:
        await close_db_pool() # Close DB pool after all reports are done

if __name__ == "__main__":
    asyncio.run(main_reports_async())
