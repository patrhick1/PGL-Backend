# Campaign API Schema Update Summary

## Overview
Updated the campaign API schemas and database queries to include all fields from the database schema, particularly fields needed for Instantly.ai integration and Google Docs keyword analysis.

## Fields Added to Campaign Schemas

### 1. `instantly_campaign_id` (Optional[str])
- **Purpose**: Stores the Instantly.ai campaign ID for integration
- **Database Type**: TEXT
- **Usage**: Links PostgreSQL campaigns to Instantly.ai campaigns for pitch sending

### 2. `gdoc_keywords` (Optional[List[str]])
- **Purpose**: Stores keywords extracted from Google Docs analysis
- **Database Type**: TEXT[]
- **Usage**: Additional keywords from analyzing client's Google Docs content

## Updated Files

### 1. `/podcast_outreach/api/schemas/campaign_schemas.py`
- Added `instantly_campaign_id` and `gdoc_keywords` to `CampaignBase`
- Added same fields to `CampaignUpdate` for update operations
- These fields will now be included in API responses via `CampaignInDB`

### 2. `/podcast_outreach/database/queries/campaigns.py`
- Updated `create_campaign_in_db()` to include new fields in INSERT statement
- Added proper parameter handling for the new fields
- Added list parsing for `gdoc_keywords` in update function (similar to other keyword fields)

## API Endpoints Affected

### GET /campaigns/
- Will now return `instantly_campaign_id` and `gdoc_keywords` in response

### GET /campaigns/{campaign_id}
- Will now return `instantly_campaign_id` and `gdoc_keywords` in response

### POST /campaigns/
- Can now accept `instantly_campaign_id` and `gdoc_keywords` when creating campaigns

### PUT /campaigns/{campaign_id} (Admin only)
- Can update `instantly_campaign_id` and `gdoc_keywords`

### PATCH /campaigns/me/{campaign_id} (Client accessible)
- Clients CAN update `instantly_campaign_id` (not restricted)
- Clients CAN update `gdoc_keywords` (not restricted)
- Restricted fields remain: `person_id`, `attio_client_id`

## Example Usage

### Creating a Campaign with Instantly ID
```json
POST /campaigns/
{
  "campaign_id": "550e8400-e29b-41d4-a716-446655440000",
  "person_id": 123,
  "campaign_name": "Q1 2024 Podcast Tour",
  "campaign_type": "podcast_outreach",
  "instantly_campaign_id": "inst_camp_xyz123",
  "gdoc_keywords": ["business", "entrepreneurship", "startups"],
  "ideal_podcast_description": "Business podcasts focusing on entrepreneurship"
}
```

### Updating Instantly Campaign ID
```json
PATCH /campaigns/me/550e8400-e29b-41d4-a716-446655440000
{
  "instantly_campaign_id": "inst_camp_abc456"
}
```

## Integration Notes

1. **Instantly.ai Integration**: The `instantly_campaign_id` field enables linking between PGL campaigns and Instantly.ai campaigns, necessary for the pitch sending workflow.

2. **Keyword Management**: Three keyword fields are now available:
   - `campaign_keywords`: Manual keywords set by user
   - `questionnaire_keywords`: AI-generated from questionnaire responses
   - `gdoc_keywords`: Extracted from Google Docs analysis

3. **Backward Compatibility**: All new fields are optional, ensuring backward compatibility with existing code.

## Next Steps

1. Frontend should be updated to display/edit `instantly_campaign_id` where appropriate
2. Instantly.ai integration scripts should use this field to link campaigns
3. Consider adding validation for `instantly_campaign_id` format if Instantly has specific requirements