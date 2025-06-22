-- Fix vetting_criteria_met in campaign_media_discoveries table
-- Convert JSON strings to proper JSONB
UPDATE campaign_media_discoveries
SET vetting_criteria_met = vetting_criteria_met::text::jsonb
WHERE vetting_criteria_met IS NOT NULL
  AND jsonb_typeof(vetting_criteria_met) = 'string';

-- Fix vetting_checklist in match_suggestions table  
-- Convert JSON strings to proper JSONB
UPDATE match_suggestions
SET vetting_checklist = vetting_checklist::text::jsonb
WHERE vetting_checklist IS NOT NULL
  AND jsonb_typeof(vetting_checklist) = 'string';

-- Verify the fixes
SELECT 'campaign_media_discoveries' as table_name,
       COUNT(*) as total_records,
       COUNT(CASE WHEN jsonb_typeof(vetting_criteria_met) = 'string' THEN 1 END) as string_records,
       COUNT(CASE WHEN jsonb_typeof(vetting_criteria_met) = 'object' THEN 1 END) as object_records
FROM campaign_media_discoveries
WHERE vetting_criteria_met IS NOT NULL

UNION ALL

SELECT 'match_suggestions' as table_name,
       COUNT(*) as total_records,
       COUNT(CASE WHEN jsonb_typeof(vetting_checklist) = 'string' THEN 1 END) as string_records,
       COUNT(CASE WHEN jsonb_typeof(vetting_checklist) = 'object' THEN 1 END) as object_records
FROM match_suggestions
WHERE vetting_checklist IS NOT NULL;