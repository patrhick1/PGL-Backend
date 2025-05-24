# podcast_outreach/integrations/google_sheets.py

import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

class GoogleSheetsService:
    def __init__(self):
        """Initializes the Google Sheets service client."""
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        self.sheets_service = build('sheets', 'v4', credentials=credentials)

    def create_spreadsheet(self, title):
        """Creates a new Google Spreadsheet.

        Args:
            title (str): The title for the new spreadsheet.

        Returns:
            str: The ID of the newly created spreadsheet.
        """
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        spreadsheet = self.sheets_service.spreadsheets().create(body=spreadsheet,
                                                                fields='spreadsheetId').execute()
        print(f"Spreadsheet ID: {spreadsheet.get('spreadsheetId')}")
        return spreadsheet.get('spreadsheetId')

    def read_sheet(self, spreadsheet_id, range_name):
        """Reads data from a specific range in a spreadsheet.

        Args:
            spreadsheet_id (str): The ID of the spreadsheet.
            range_name (str): The A1 notation of the range to read (e.g., 'Sheet1!A1:B2').

        Returns:
            list: A list of lists containing the data read from the sheet.
        """
        result = self.sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        return values

    def write_sheet(self, spreadsheet_id, range_name, values):
        """Writes data to a specific range in a spreadsheet, overwriting existing data.

        Args:
            spreadsheet_id (str): The ID of the spreadsheet.
            range_name (str): The A1 notation of the range to write (e.g., 'Sheet1!A1').
            values (list): A list of lists containing the data to write.
        """
        body = {
            'values': values
        }
        result = self.sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_name,
            valueInputOption='USER_ENTERED', body=body).execute()
        print(f"{result.get('updatedCells')} cells updated.")
        return result

    def append_sheet(self, spreadsheet_id, range_name, values):
        """Appends data to a table within a sheet. Finds the first empty row.

        Args:
            spreadsheet_id (str): The ID of the spreadsheet.
            range_name (str): The A1 notation of the table range (e.g., 'Sheet1!A1').
                             The method appends after the last row of this table.
            values (list): A list of lists containing the data to append.
        """
        body = {
            'values': values
        }
        result = self.sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range=range_name,
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body=body).execute()
        print(f"Appended data to range: {result.get('updates').get('updatedRange')}")
        return result 
