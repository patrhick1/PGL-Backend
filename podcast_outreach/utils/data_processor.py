    # podcast_outreach/utils/data_processor.py

    import json
    from email.utils import parsedate_to_datetime
    from datetime import datetime, timedelta
    import logging
    import html

    logger = logging.getLogger(__name__)


    def extract_document_id(google_doc_link):
        """
        Extracts the Google Document ID from a given link.
        """
        try:
            parts = google_doc_link.split('/')
            index = parts.index('d')
            document_id = parts[index + 1]
            return document_id
        except (ValueError, IndexError):
            return None


    def parse_date(date_string):
        """
        Parse various date string formats into datetime objects.
        Handles timezone information correctly.
        Returns None if parsing fails.
        """
        if not date_string:
            return None

        # Handle milliseconds (common in ListenNotes)
        if isinstance(date_string, int) and len(str(date_string)) == 13: # Check if it looks like a Unix timestamp in ms
            try:
                # Convert milliseconds to seconds
                timestamp_sec = date_string / 1000
                dt_object = datetime.fromtimestamp(timestamp_sec) # Assumes local timezone, adjust if UTC needed
                # To make it timezone-aware (e.g., UTC):
                # from datetime import timezone
                # dt_object = datetime.fromtimestamp(timestamp_sec, tz=timezone.utc)
                return dt_object
            except ValueError:
                logger.warning(f"Could not parse timestamp integer: {date_string}")
                return None

        # Standard string formats
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",        # ISO 8601 UTC (Zulu)
            "%Y-%m-%dT%H:%M:%S%z",       # ISO 8601 with timezone offset
            "%Y-%m-%dT%H:%M:%S.%f%z",    # ISO 8601 with timezone offset and microseconds
            "%a, %d %b %Y %H:%M:%S %Z",  # RFC 5322 (e.g., Tue, 10 Oct 2023 14:30:00 GMT)
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 5322 with numeric timezone offset
            "%Y-%m-%d",                  # Simple date
            # Add other formats as needed
        ]

        for fmt in formats:
            try:
                # Attempt to parse with the current format
                dt_object = datetime.strptime(str(date_string), fmt)

                # If the format includes %z, the object is already timezone-aware
                # If it's a naive object (like from %Y-%m-%d), you might want to assign a default timezone
                # if dt_object.tzinfo is None:
                #     from datetime import timezone
                #     dt_object = dt_object.replace(tzinfo=timezone.utc) # Example: Assign UTC

                return dt_object
            except ValueError:
                continue # Try the next format
            except TypeError:
                 logger.warning(f"Type error parsing date string: {date_string} (type: {type(date_string)})")
                 return None # Cannot parse this type

        logger.warning(f"Could not parse date string with any known format: {date_string}")
        return None
