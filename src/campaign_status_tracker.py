# src/campaign_status_tracker.py
import os
from datetime import datetime, timedelta, date
from collections import Counter, defaultdict

from google.oauth2 import service_account # For Drive API
from googleapiclient.discovery import build # For Drive API
from dotenv import load_dotenv

# Assuming these services are in the same src directory or an importable path
from airtable_service import PodcastService # To get client and campaign data
from google_sheets_service import GoogleSheetsService # To write to sheets

load_dotenv()

# --- Configuration ---
# Airtable Config
AIRTABLE_CAMPAIGN_MANAGER_TABLE = "Campaign Manager"
AIRTABLE_CM_CLIENT_NAME_FIELD = "Client Name" # Field containing the client's name
AIRTABLE_CM_STATUS_FIELD = "Status"         # Field for campaign status
AIRTABLE_CM_DATE_FIELD = "Last Modified"   # Date field to use for weekly grouping

# Google Drive/Sheets Config
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID = os.getenv('CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID')
SHEETS_API_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]

# --- Report Configuration ---
WEEKS_TO_REPORT = 5 # Current week + previous 4 weeks

# Statuses from Airtable needed for the report calculations
# Ensure "Positive" is mapped correctly (using "Interested" as per user)
# Ensure all statuses mentioned in metrics are included.
TRACKED_STATUSES = [
    "Outreached",       # For Messages sent
    "Responded",        # For Total replies
    "Interested",       # For Positive replies
    "Pending Intro Call Booking", # For Meetings booked
    "Lost",             # Other status
    "Form Submitted"    # Other status
    # Add any other specific statuses you have and want to see counts for
]

# Statuses to ignore when calculating "Total Records This Week"
STATUSES_TO_IGNORE_IN_TOTAL = [
    "Prospect",
    "OR Ready",
    "Fit",
    "Not a fit",
    "Episode and angles selected",
    "Pitch Done"
]

# Define the order and mapping for rows in the sheet
REPORT_ROW_ORDER = [
    {"display_name": "Messages sent", "source_status": "Outreached"},
    {"display_name": "Total replies", "source_status": "Responded"},
    {"display_name": "Positive replies", "source_status": "Interested"},
    {"display_name": "Form Submitted", "source_status": "Form Submitted"},
    {"display_name": "Meetings booked", "source_status": "Pending Intro Call Booking"},
    # -- Add other statuses directly --
    {"display_name": "Lost", "source_status": "Lost"},
    # Add more dicts here if you track other statuses explicitly
]


class CampaignStatusTracker:
    def __init__(self):
        self.airtable_service = PodcastService()
        self.sheets_service = GoogleSheetsService()

        if not GOOGLE_APPLICATION_CREDENTIALS:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")
        if not CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID:
            raise ValueError("CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID environment variable not set.")

        drive_credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_APPLICATION_CREDENTIALS, scopes=SHEETS_API_SCOPES)
        self.drive_service = build('drive', 'v3', credentials=drive_credentials)
        print("CampaignStatusTracker initialized with Airtable, Sheets, and Drive services.")

    def _find_spreadsheet_in_folder(self, name, folder_id):
        """Finds a spreadsheet by name within a specific Google Drive folder."""
        # Escape single quotes for the Drive API query
        safe_name = name.replace("'", "\\'")
        query = f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and '{folder_id}' in parents and trashed = false"
        try:
            response = self.drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            files = response.get('files', [])
            if files:
                print(f"Found spreadsheet '{name}' with ID {files[0]['id']} in folder '{folder_id}'.")
                return files[0]['id']
            return None
        except Exception as e:
            print(f"Error finding spreadsheet '{name}' in folder '{folder_id}': {e}")
            return None

    def _get_or_create_spreadsheet_for_client(self, client_name):
        """Gets existing or creates new spreadsheet for the client."""
        spreadsheet_title = f"{client_name} - Campaign Status Tracker"
        spreadsheet_id = self._find_spreadsheet_in_folder(spreadsheet_title, CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID)

        if spreadsheet_id:
            return spreadsheet_id
        else:
            print(f"Creating new spreadsheet titled '{spreadsheet_title}'...")
            new_sheet_id = self.sheets_service.create_spreadsheet(title=spreadsheet_title)
            if new_sheet_id:
                print(f"Spreadsheet created with ID: {new_sheet_id}. Moving to folder {CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID}...")
                try:
                    file_metadata = self.drive_service.files().get(fileId=new_sheet_id, fields='parents').execute()
                    previous_parents = ",".join(file_metadata.get('parents', []))
                    self.drive_service.files().update(
                        fileId=new_sheet_id,
                        addParents=CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID,
                        removeParents=previous_parents if previous_parents else None,
                        fields='id, parents'
                    ).execute()
                    print(f"Successfully moved spreadsheet {new_sheet_id} to folder {CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID}.")
                    return new_sheet_id
                except Exception as e:
                    print(f"Error moving spreadsheet {new_sheet_id} to folder {CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID}: {e}")
                    return None
            else:
                print(f"Failed to create spreadsheet for {client_name} via GoogleSheetsService.")
                return None

    def _parse_airtable_datetime(self, datetime_str):
        """Parses Airtable datetime string to datetime.date object."""
        if not datetime_str: return None
        try:
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00')).date()
        except ValueError:
            print(f"Warning: Could not parse datetime string: {datetime_str}")
            return None

    def _get_week_date_ranges(self, num_weeks):
        """Generates date ranges (Monday to Sunday) for the last num_weeks."""
        today = date.today()
        # Find the start of the current week (Monday)
        start_of_current_week = today - timedelta(days=today.weekday())
        
        date_ranges = []
        for i in range(num_weeks):
            week_start = start_of_current_week - timedelta(weeks=i)
            week_end = week_start + timedelta(days=6)
            date_ranges.append({"start": week_start, "end": week_end})
        
        return date_ranges[::-1] # Return in chronological order (oldest first)

    def _calculate_weekly_metrics(self, client_records, weekly_ranges):
        """Calculates status counts for each week for a specific client."""
        weekly_data = []

        for week in weekly_ranges:
            week_start = week["start"]
            week_end = week["end"]
            
            status_counts = Counter()
            records_in_week = 0
            
            for record in client_records:
                fields = record.get('fields', {})
                record_date_str = fields.get(AIRTABLE_CM_DATE_FIELD)
                status = fields.get(AIRTABLE_CM_STATUS_FIELD)
                
                if not record_date_str or not status: continue

                record_date = self._parse_airtable_datetime(record_date_str)
                if not record_date: continue

                # Check if the record's date falls within the current week range
                if week_start <= record_date <= week_end:
                    # Only count towards total if status is not in the ignore list
                    if status not in STATUSES_TO_IGNORE_IN_TOTAL:
                        records_in_week += 1
                    
                    # Count for individual tracked statuses (this logic remains the same)
                    if status in TRACKED_STATUSES:
                        status_counts[status] += 1
                        
            # Store counts for this week
            weekly_data.append({
                "week_start": week_start,
                "week_end": week_end,
                "status_counts": status_counts,
                "total_records": records_in_week
            })
            
        return weekly_data # List of dicts, one per week

    def _prepare_sheet_data(self, weekly_metric_data):
        """Formats the aggregated weekly data for writing to Google Sheets."""
        
        # Create headers
        headers = ["Metric / Status"] + [f"Week of {wd['week_start']:%m/%d/%y}" for wd in weekly_metric_data]
        data_rows = [headers]
        
        # Add rows for each metric/status defined in REPORT_ROW_ORDER
        for row_info in REPORT_ROW_ORDER:
            display_name = row_info["display_name"]
            source_status = row_info["source_status"]
            row_data = [display_name]
            for weekly_stats in weekly_metric_data:
                count = weekly_stats["status_counts"].get(source_status, 0)
                row_data.append(count)
            data_rows.append(row_data)
            
        # Add a gap for visual separation (optional)
        data_rows.append(["---"] * len(headers)) 
        
        # Add total row
        total_row = ["Total Records This Week"]
        for weekly_stats in weekly_metric_data:
            total_row.append(weekly_stats["total_records"])
        data_rows.append(total_row)
        
        return data_rows

    def update_all_client_spreadsheets(self):
        """Main method to fetch records, group by client, calculate weekly metrics, and update sheets."""
        print("Starting campaign status tracking update (Weekly Format)...")
        
        print(f"Fetching all records from Airtable table '{AIRTABLE_CAMPAIGN_MANAGER_TABLE}'...")
        all_campaign_records = self.airtable_service.search_records(
            table_name=AIRTABLE_CAMPAIGN_MANAGER_TABLE
        )

        if not all_campaign_records:
            print(f"No records found in Airtable table '{AIRTABLE_CAMPAIGN_MANAGER_TABLE}'. Exiting.")
            return

        print(f"Found {len(all_campaign_records)} total records. Grouping by client name...")

        # Group records by Client Name
        records_by_client = defaultdict(list)
        for record in all_campaign_records:
            fields = record.get('fields', {})
            client_name_list = fields.get(AIRTABLE_CM_CLIENT_NAME_FIELD)
            client_name = None
            if isinstance(client_name_list, list) and client_name_list:
                potential_name = client_name_list[0]
                if isinstance(potential_name, str) and potential_name.strip():
                     client_name = potential_name.strip()
            if client_name:
                records_by_client[client_name].append(record)
            else:
                 print(f"Skipping record ID {record.get('id', 'N/A')} due to missing, invalid, or non-string client name in field '{AIRTABLE_CM_CLIENT_NAME_FIELD}'. Value: {client_name_list}")

        if not records_by_client:
            print("No records with valid client names found after grouping. Exiting.")
            return

        print(f"Processing {len(records_by_client)} clients found in campaign records.")

        # Get date ranges for the weeks to report
        weekly_ranges = self._get_week_date_ranges(WEEKS_TO_REPORT)
        print(f"Reporting for weeks starting: {[r['start'] for r in weekly_ranges]}")

        # Iterate through each client group and update/create spreadsheet
        for client_name, client_records in records_by_client.items():
            print(f"\nProcessing client: {client_name}")

            spreadsheet_id = self._get_or_create_spreadsheet_for_client(client_name)
            if not spreadsheet_id:
                print(f"Could not get or create spreadsheet for {client_name}. Skipping.")
                continue

            print(f"Calculating weekly metrics for {len(client_records)} records for {client_name}.")
            weekly_metric_data = self._calculate_weekly_metrics(client_records, weekly_ranges)

            if not weekly_metric_data:
                 print(f"No weekly data calculated for {client_name}. Skipping sheet update.")
                 continue

            sheet_data = self._prepare_sheet_data(weekly_metric_data)

            print(f"Writing data to spreadsheet for {client_name} (Sheet ID: {spreadsheet_id})")
            try:
                # Overwrite the sheet starting at A1
                self.sheets_service.write_sheet(spreadsheet_id, "Sheet1!A1", sheet_data)
                print(f"Successfully updated spreadsheet for {client_name}.")
            except Exception as e:
                print(f"Error writing to spreadsheet for {client_name} (ID: {spreadsheet_id}): {e}")

        print("\nCampaign status tracking update finished.")


if __name__ == "__main__":
    print("Running Campaign Status Tracker script (Weekly Format)...")
    try:
        tracker = CampaignStatusTracker()
        tracker.update_all_client_spreadsheets()
    except Exception as e:
        print(f"An unhandled error occurred in CampaignStatusTracker: {e}")
        import traceback
        traceback.print_exc() 