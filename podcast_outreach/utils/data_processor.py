# podcast_outreach/utils/data_processor.py

import json
from email.utils import parsedate_to_datetime
from datetime import datetime, date, timezone as dt_timezone
import logging
import html
from typing import Optional, Any

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


def parse_date(date_string: Any) -> Optional[datetime]:
    """
    Parse various date string formats into datetime objects.
    Handles timezone information correctly, converting to UTC.
    Returns None if parsing fails.
    """
    if date_string is None:
        return None

    if isinstance(date_string, datetime):
        if date_string.tzinfo is None or date_string.tzinfo.utcoffset(date_string) is None:
            return date_string.replace(tzinfo=dt_timezone.utc)
        return date_string.astimezone(dt_timezone.utc)

    if isinstance(date_string, date):
        return datetime.combine(date_string, datetime.min.time()).replace(tzinfo=dt_timezone.utc)

    if isinstance(date_string, int):
        if len(str(date_string)) == 13:
            try:
                timestamp_sec = date_string / 1000
                dt_object = datetime.fromtimestamp(timestamp_sec, tz=dt_timezone.utc)
                return dt_object
            except ValueError:
                logger.warning(f"Could not parse 13-digit integer timestamp: {date_string}, will attempt as string.")
                s_date_string = str(date_string)
        else:
            logger.warning(f"Integer value {date_string} is not a 13-digit ms timestamp. Cannot parse as date.")
            return None
    elif isinstance(date_string, float):
        logger.warning(f"Float value {date_string} cannot be parsed as date.")
        return None
    else:
        s_date_string = str(date_string).strip()

    if not s_date_string:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            dt_object = datetime.strptime(s_date_string, fmt)
            if dt_object.tzinfo is None or dt_object.tzinfo.utcoffset(dt_object) is None:
                dt_object = dt_object.replace(tzinfo=dt_timezone.utc)
            else:
                dt_object = dt_object.astimezone(dt_timezone.utc)
            return dt_object
        except ValueError:
            continue
        except TypeError:
             logger.warning(f"TypeError during strptime for: {s_date_string} (original type: {type(date_string)}) with format {fmt}")
             return None

    logger.warning(f"Could not parse date string with any known format: '{s_date_string}' (original type: {type(date_string)})")
    return None
