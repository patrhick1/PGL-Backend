| Column             | Type          | Key / Constraints | What it stores                     |
| ------------------ | ------------- | ----------------- | ---------------------------------- |
| `company_id`       | `UUID`        | **PK**            | Unique ID for the company          |
| `name`             | `TEXT`        | –                 | Legal or brand name                |
| `domain`           | `TEXT`        | –                 | Website domain (e.g. `acme.com`)   |
| `description`      | `TEXT`        | –                 | Short “about us” blurb             |
| `category`         | `TEXT`        | –                 | Industry or vertical               |
| `primary_location` | `TEXT`        | –                 | HQ city / country                  |
| `website_url`      | `TEXT`        | –                 | Full company URL                   |
| `logo_url`         | `TEXT`        | –                 | Link to logo image                 |
| `employee_range`   | `INTEGER`     | –                 | Head-count bracket (e.g. 1 = 1–10) |
| `est_arr`          | `NUMERIC`     | –                 | Estimated annual recurring revenue |
| `foundation_date`  | `DATE`        | –                 | Date company started               |
| `twitter_handle`   | `TEXT`        | –                 | Company Twitter/X handle           |
| `linkedin_url`     | `TEXT`        | –                 | Company LinkedIn page              |
| `created_at`       | `TIMESTAMPTZ` | default = `NOW()` | Row timestamp                      |
