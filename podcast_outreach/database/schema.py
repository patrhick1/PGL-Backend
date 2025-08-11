# podcast_outreach/database/schema.py
 
import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor
import os
from dotenv import load_dotenv
 
# Load environment variables from .env file at the start
load_dotenv()
 
# --- Database Connection ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("PGDATABASE"),
            user=os.environ.get("PGUSER"),
            password=os.environ.get("PGPASSWORD"),
            host=os.environ.get("PGHOST"),
            port=os.environ.get("PGPORT")
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        print("Please ensure PostgreSQL is running and connection details are correct.")
        print("Ensure environment variables are set: PGDATABASE, PGUSER, PGPASSWORD, PGHOST, PGPORT")
        return None
 
# --- Utility Functions ---
def execute_sql(conn, sql_statement, params=None):
    """Executes a given SQL statement."""
    try:
        with conn.cursor() as cur:
            cur.execute(sql_statement, params)
        conn.commit()
    except psycopg2.Error as e:
        print(f"Error executing SQL: {e}")
        if conn:
            conn.rollback()
        raise # Re-raise the exception to be handled by the caller
 
def create_timestamp_update_trigger_function(conn):
    """Creates or replaces a function to update a timestamp column to NOW()."""
    trigger_func_sql = """
    CREATE OR REPLACE FUNCTION update_modified_column()
    RETURNS TRIGGER AS $
    BEGIN
       NEW.updated_at = NOW();
       RETURN NEW;
     END;
    $ language 'plpgsql';
    """
    try:
        execute_sql(conn, trigger_func_sql)
        print("Timestamp update function 'update_modified_column' created/ensured.")
    except psycopg2.Error as e:
        print(f"Error creating timestamp update function: {e}")
        # Do not close connection here, let main handler do it
 
 
def apply_timestamp_update_trigger(conn, table_name):
    """Applies the timestamp update trigger to the specified table's updated_at column."""
    trigger_name = f"trigger_update_{table_name}_updated_at"
    apply_trigger_sql = sql.SQL("""
    DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};
    CREATE TRIGGER {trigger_name}
    BEFORE UPDATE ON {table_name}
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();
    """).format(
        trigger_name=sql.Identifier(trigger_name),
        table_name=sql.Identifier(table_name)
    )
    try:
        execute_sql(conn, apply_trigger_sql)
        print(f"Timestamp update trigger applied to table '{table_name}'.")
    except psycopg2.Error as e:
        print(f"Error applying trigger to {table_name}: {e}")
 
 
# --- Table Creation Functions ---
 
def create_companies_table(conn):
    sql_statement = """
    CREATE TABLE companies (
        company_id SERIAL PRIMARY KEY,
        name TEXT,
        domain TEXT,
        description TEXT,
        category TEXT,
        primary_location TEXT,
        website_url TEXT,
        logo_url TEXT,
        employee_range INTEGER,
        est_arr NUMERIC,
        foundation_date DATE,
        twitter_handle TEXT,
        linkedin_url TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """
    execute_sql(conn, sql_statement)
    print("Table COMPANIES created/ensured.")
 
def create_people_table(conn):
    sql_statement = """
    CREATE TABLE people (
        person_id                 SERIAL PRIMARY KEY,
        company_id                INTEGER    REFERENCES companies(company_id) ON DELETE SET NULL,
        full_name                 TEXT,
        email                     TEXT UNIQUE,
        linkedin_profile_url      TEXT,
        twitter_profile_url       TEXT,
        instagram_profile_url     TEXT,
        tiktok_profile_url        TEXT,
        dashboard_username        TEXT UNIQUE,
        dashboard_password_hash   TEXT,
        attio_contact_id          UUID,
        role                      VARCHAR(255),
        created_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        bio                       TEXT,
        website                   TEXT,
        location                  TEXT,
        timezone                  VARCHAR(100),
        profile_image_url         TEXT,
        profile_banner_url        TEXT,
        notification_settings     JSONB DEFAULT '{}'::jsonb,
        privacy_settings          JSONB DEFAULT '{}'::jsonb,
        stripe_customer_id        VARCHAR(255) UNIQUE,
        -- Nylas fields
        nylas_grant_id            VARCHAR(255),
        nylas_email_account       VARCHAR(255)
    );

    """
    execute_sql(conn, sql_statement)
    print("Table PEOPLE created/ensured.")
    apply_timestamp_update_trigger(conn, "people")
 
def create_client_profiles_table(conn):
    sql_statement = """
    CREATE TABLE client_profiles (
        client_profile_id         SERIAL PRIMARY KEY,
        person_id                 INTEGER NOT NULL UNIQUE REFERENCES people(person_id) ON DELETE CASCADE,
        plan_type                 VARCHAR(50) DEFAULT 'free' NOT NULL, -- 'free' or 'paid'
        
        -- UNIFIED MATCH TRACKING (for both free and paid users)
        weekly_match_allowance    INTEGER NOT NULL, -- 50 for free, 200 for paid
        current_weekly_matches    INTEGER DEFAULT 0,  -- Current week's quality match count (vetting_score >= 50)
        last_weekly_match_reset   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- When match count was last reset
        last_auto_discovery_reset TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- Kept for backward compatibility
        
        -- MATCH NOTIFICATION PREFERENCES
        match_notification_enabled BOOLEAN DEFAULT TRUE, -- Whether to send match notifications
        match_notification_threshold INTEGER DEFAULT 30, -- Number of matches to trigger notification
        last_match_notification_sent TIMESTAMPTZ, -- When last notification was sent
        
        -- SUBSCRIPTION TRACKING
        subscription_provider_id  VARCHAR(255), -- e.g., Stripe subscription ID
        subscription_status       VARCHAR(50),  -- e.g., 'active', 'canceled', 'past_due'
        subscription_ends_at      TIMESTAMPTZ,
        
        created_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_client_profiles_person_id ON client_profiles (person_id);
    CREATE INDEX IF NOT EXISTS idx_client_profiles_plan_type ON client_profiles (plan_type);
    
    -- Add comments for clarity
    COMMENT ON COLUMN client_profiles.current_weekly_matches IS 
        'Unified tracking for quality matches (vetting_score >= 50). Limit: 50/week for free, 200/week for paid.';
    COMMENT ON COLUMN client_profiles.weekly_match_allowance IS 
        'Weekly limit for quality matches. Set to 50 for free users, 200 for paid users.';
    """
    execute_sql(conn, sql_statement)
    print("Table CLIENT_PROFILES created/ensured.")
    apply_timestamp_update_trigger(conn, "client_profiles")

def create_media_table(conn):
    sql_statement = """
    CREATE TABLE IF NOT EXISTS media (
        media_id                  SERIAL PRIMARY KEY,
        company_id                INTEGER REFERENCES companies(company_id) ON DELETE SET NULL,
 
        -- existing core fields
        name                      TEXT,
        title                     TEXT,
        rss_url                   TEXT,
        rss_feed_url              TEXT,
        category                  TEXT,
        language                  VARCHAR(50),
        image_url                 TEXT,
        avg_downloads             INTEGER,
        contact_email             TEXT,
        fetched_episodes          BOOLEAN,
        description               TEXT,
        ai_description            TEXT,
        episode_summaries_compiled TEXT,
        embedding                 VECTOR(1536),
        created_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- NEW: Add updated_at
        last_fetched_at           TIMESTAMPTZ,
        latest_episode_date       DATE, -- This will be updated by enrichment
 
        -- new profile_data fields from EnrichedPodcastProfile
        source_api                TEXT,
        api_id                    TEXT UNIQUE, -- NEW: Make api_id unique for easier lookup
        website                   TEXT,
        podcast_spotify_id        TEXT,
        itunes_id                 TEXT,
        total_episodes            INTEGER,
        last_posted_at            TIMESTAMPTZ, -- This is likely redundant with latest_episode_date, consider removing one
        listen_score              REAL,
        listen_score_global_rank  INTEGER,
        audience_size             INTEGER,
        itunes_rating_average     REAL,
        itunes_rating_count       INTEGER,
        spotify_rating_average    REAL,
        spotify_rating_count      INTEGER,
        podcast_twitter_url       TEXT,
        podcast_linkedin_url      TEXT,
        podcast_instagram_url     TEXT,
        podcast_facebook_url      TEXT,
        podcast_youtube_url       TEXT,
        podcast_tiktok_url        TEXT,
        podcast_other_social_url  TEXT,
        
        -- NEW ENRICHMENT FIELDS
        host_names                TEXT[], -- List of strings
        rss_owner_name            TEXT,
        rss_owner_email           TEXT,
        rss_explicit              BOOLEAN,
        rss_categories            TEXT[], -- List of strings
        twitter_followers         INTEGER,
        twitter_following         INTEGER,
        is_twitter_verified       BOOLEAN,
        linkedin_connections      INTEGER, -- Can be followers or connections
        instagram_followers       INTEGER,
        tiktok_followers          INTEGER,
        facebook_likes            INTEGER,
        youtube_subscribers       INTEGER,
        publishing_frequency_days REAL,
        last_enriched_timestamp   TIMESTAMPTZ, -- When was this record last enriched
        -- NEW: Data Provenance & Confidence Fields
        website_source            TEXT, -- e.g., 'api_listennotes', 'llm_discovery', 'manual'
        website_confidence        NUMERIC(3, 2), -- e.g., 1.00 for manual, 0.90 for API, 0.60 for LLM
        contact_email_source      TEXT,
        contact_email_confidence  NUMERIC(3, 2),
        host_names_source         TEXT,
        host_names_confidence     NUMERIC(3, 2),
        -- (Add more source/confidence pairs for other volatile fields like social URLs if needed)

        -- NEW: Manual Override Tracking
        last_manual_update_ts     TIMESTAMPTZ,

        -- NEW: Selective Enrichment Tracking
        social_stats_last_fetched_at TIMESTAMPTZ,

        -- NEW: Granular Quality Score Metrics
        quality_score             NUMERIC,     -- The final, weighted score
        quality_score_recency     NUMERIC,     -- Component score for recency
        quality_score_frequency   NUMERIC,     -- Component score for frequency
        quality_score_audience    NUMERIC,     -- Component score for audience metrics
        quality_score_social      NUMERIC,     -- Component score for social presence
        quality_score_last_calculated TIMESTAMPTZ, -- When the score was last calculated
        
        -- NEW FIELDS FOR ENRICHMENT SUPPORT
        first_episode_date        DATE,         -- When the podcast first published an episode
        
        -- NEW: Host name confidence tracking
        host_names_discovery_sources JSONB DEFAULT '[]'::jsonb, -- JSON array of sources where host names were discovered
        host_names_discovery_confidence JSONB DEFAULT '{}'::jsonb, -- JSON object mapping each host name to its confidence score
        host_names_last_verified TIMESTAMPTZ -- Timestamp of last host name verification check
    );
 
    CREATE INDEX IF NOT EXISTS idx_media_company_id           ON media (company_id);
    CREATE INDEX IF NOT EXISTS idx_media_embedding_hnsw       ON media USING hnsw (embedding vector_cosine_ops);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_media_api_id        ON media (api_id);
    -- NEW INDEXES
    CREATE INDEX IF NOT EXISTS idx_media_last_enriched_ts     ON media (last_enriched_timestamp);
    CREATE INDEX IF NOT EXISTS idx_media_social_stats_fetched ON media (social_stats_last_fetched_at);
    CREATE INDEX IF NOT EXISTS idx_media_host_names_last_verified ON media (host_names_last_verified);
    """
    execute_sql(conn, sql_statement)
    print("Table MEDIA created/ensured with extended provenance and quality score columns.")
    apply_timestamp_update_trigger(conn, "media") # NEW: Apply trigger to media table
 
 
def create_media_people_table(conn):
    sql_statement = """
    CREATE TABLE media_people (
        media_id INTEGER REFERENCES media(media_id) ON DELETE CASCADE,
        person_id INTEGER REFERENCES people(person_id) ON DELETE CASCADE,
        show_role VARCHAR(255),
        host_confirmed BOOLEAN,
        linked_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (media_id, person_id)
    );
    """
    execute_sql(conn, sql_statement)
    print("Table MEDIA_PEOPLE created/ensured.")
 
def create_campaigns_table(conn):
    sql_statement = """
    CREATE TABLE IF NOT EXISTS campaigns (
        campaign_id UUID PRIMARY KEY,
        person_id INTEGER REFERENCES people(person_id) ON DELETE RESTRICT,
        attio_client_id UUID,
        campaign_name TEXT,
        campaign_type TEXT,
        campaign_bio TEXT,
        campaign_angles TEXT,
        campaign_keywords TEXT[],
        questionnaire_keywords TEXT[] NULL,
        gdoc_keywords TEXT[] NULL,
        compiled_social_posts TEXT,
        podcast_transcript_link TEXT,
        compiled_articles_link TEXT,
        mock_interview_transcript TEXT,
        embedding VECTOR(1536),
        start_date DATE,
        end_date DATE,
        goal_note TEXT,
        media_kit_url TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        instantly_campaign_id TEXT,
        questionnaire_responses JSONB,
        ideal_podcast_description TEXT,  -- *** NEW FIELD ***
        -- *** AUTO-DISCOVERY FIELDS ***
        auto_discovery_enabled BOOLEAN DEFAULT TRUE,
        auto_discovery_last_run TIMESTAMPTZ,
        auto_discovery_status VARCHAR(50) DEFAULT 'pending',
        -- *** RELIABILITY FIELDS FROM MIGRATION ***
        auto_discovery_last_heartbeat TIMESTAMPTZ,
        auto_discovery_progress JSONB DEFAULT '{}',
        auto_discovery_error TEXT,
        -- Nylas fields
        nylas_grant_id VARCHAR(255),
        email_account VARCHAR(255),
        email_provider VARCHAR(50) DEFAULT 'instantly'
    );
    CREATE INDEX IF NOT EXISTS idx_campaigns_person_id ON CAMPAIGNS (person_id);
    CREATE INDEX IF NOT EXISTS idx_campaigns_embedding_hnsw ON CAMPAIGNS USING hnsw (embedding vector_cosine_ops);
    -- AUTO-DISCOVERY INDEXES
    CREATE INDEX IF NOT EXISTS idx_campaigns_auto_discovery 
        ON campaigns(auto_discovery_enabled, auto_discovery_status) 
        WHERE auto_discovery_enabled = TRUE;
    CREATE INDEX IF NOT EXISTS idx_campaigns_ready_for_discovery 
        ON campaigns(ideal_podcast_description, auto_discovery_enabled) 
        WHERE ideal_podcast_description IS NOT NULL 
        AND ideal_podcast_description != ''
        AND auto_discovery_enabled = TRUE;
    -- RELIABILITY INDEX
    CREATE INDEX IF NOT EXISTS idx_campaigns_auto_discovery_status_heartbeat 
        ON campaigns(auto_discovery_status, auto_discovery_last_heartbeat) 
        WHERE auto_discovery_status = 'running';
    """
    execute_sql(conn, sql_statement)
    print("Table CAMPAIGNS created/ensured.")
 
def create_episodes_table(conn):
    sql_statement = """
    CREATE TABLE episodes (
        episode_id SERIAL PRIMARY KEY,
        media_id INTEGER REFERENCES media(media_id) ON DELETE CASCADE,
        title TEXT,
        publish_date DATE,
        duration_sec INTEGER,
        episode_summary TEXT,
        ai_episode_summary TEXT,
        episode_url TEXT,
        direct_audio_url TEXT,
        transcript TEXT,
        embedding VECTOR(1536),
        transcribe BOOLEAN,
        downloaded BOOLEAN,
        guest_names TEXT,
        host_names TEXT[],
        source_api TEXT,
        api_episode_id TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        -- NEW FIELDS FOR EPISODE ANALYSIS
        episode_themes TEXT[],
        episode_keywords TEXT[],
        ai_analysis_done BOOLEAN DEFAULT FALSE,
        
        -- NEW: Failed URL tracking and batch transcription
        audio_url_status VARCHAR(50) DEFAULT 'available' 
            CHECK (audio_url_status IN ('available', 'failed_404', 'failed_temp', 'expired', 'refreshed')),
        audio_url_last_checked TIMESTAMPTZ,
        audio_url_failure_count INTEGER DEFAULT 0,
        audio_url_last_error TEXT,
        transcription_batch_id UUID,
        transcription_batch_position INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_episodes_media_id ON episodes (media_id);
    CREATE INDEX IF NOT EXISTS idx_episodes_embedding_hnsw ON episodes USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_episodes_audio_url_status ON episodes (audio_url_status);
    CREATE INDEX IF NOT EXISTS idx_episodes_audio_url_last_checked ON episodes (audio_url_last_checked);
    CREATE INDEX IF NOT EXISTS idx_episodes_transcription_batch_id ON episodes (transcription_batch_id);
    """
    execute_sql(conn, sql_statement)
    print("Table EPISODES created/ensured.")
 
# In schema_creation_extended.py
def create_match_suggestions(conn):
    sql_statement = """
    CREATE TABLE IF NOT EXISTS match_suggestions (
        match_id SERIAL PRIMARY KEY,
        campaign_id UUID REFERENCES campaigns(campaign_id),
        media_id INTEGER REFERENCES media(media_id),
        match_score NUMERIC,
        matched_keywords TEXT[],
        ai_reasoning TEXT,
        client_approved BOOLEAN DEFAULT FALSE, 
        approved_at TIMESTAMPTZ,
        status VARCHAR(50) DEFAULT 'pending',  
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        best_matching_episode_id INTEGER REFERENCES episodes(episode_id) ON DELETE SET NULL,
        -- *** NEW VETTING FIELDS ***
        vetting_score NUMERIC,
        vetting_reasoning TEXT,
        vetting_checklist JSONB,
        last_vetted_at TIMESTAMPTZ,
        -- *** NEW CLIENT TRACKING FIELD ***
        created_by_client BOOLEAN DEFAULT FALSE  -- Track if match was created by client discovery
    );
    CREATE INDEX IF NOT EXISTS idx_match_suggestions_campaign_id ON match_suggestions (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_match_suggestions_media_id ON match_suggestions (media_id);
    CREATE INDEX IF NOT EXISTS idx_match_suggestions_best_episode_id ON match_suggestions (best_matching_episode_id);
    -- NEW: Client match tracking indexes
    CREATE INDEX IF NOT EXISTS idx_match_suggestions_created_by_client 
        ON match_suggestions(created_by_client) 
        WHERE created_by_client = TRUE;
    CREATE INDEX IF NOT EXISTS idx_match_suggestions_client_created_at 
        ON match_suggestions(created_at, created_by_client) 
        WHERE created_by_client = TRUE;
    """
    execute_sql(conn, sql_statement)
    print("Table MATCH_SUGGESTIONS created/ensured.")
    
    # Create match tracking functions and triggers
    create_match_tracking_functions_and_triggers(conn)
 
def create_match_tracking_functions_and_triggers(conn):
    """Create functions and triggers for unified match tracking system"""
    
    # Create the increment function
    increment_function_sql = """
    CREATE OR REPLACE FUNCTION increment_quality_match_counter()
    RETURNS TRIGGER AS $$
    DECLARE
        v_person_id INTEGER;
        v_plan_type TEXT;
        v_current_matches INTEGER;
        v_weekly_limit INTEGER;
    BEGIN
        -- Only count quality matches (score >= 50)
        IF NEW.vetting_score < 50 THEN
            RETURN NEW;
        END IF;
        
        -- Get user details
        SELECT c.person_id, cp.plan_type, cp.current_weekly_matches, cp.weekly_match_allowance
        INTO v_person_id, v_plan_type, v_current_matches, v_weekly_limit
        FROM campaigns c
        LEFT JOIN client_profiles cp ON c.person_id = cp.person_id
        WHERE c.campaign_id = NEW.campaign_id;
        
        IF v_person_id IS NULL THEN
            RETURN NEW;
        END IF;
        
        -- Check if limit would be exceeded (log only, don't block)
        IF v_weekly_limit IS NOT NULL AND v_current_matches >= v_weekly_limit THEN
            RAISE NOTICE 'User % has reached weekly match limit of %', v_person_id, v_weekly_limit;
        END IF;
        
        -- Increment counter for BOTH free and paid users
        UPDATE client_profiles
        SET current_weekly_matches = COALESCE(current_weekly_matches, 0) + 1,
            updated_at = NOW()
        WHERE person_id = v_person_id;
        
        RAISE NOTICE 'User % (%) match count incremented', v_person_id, v_plan_type;
        
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    execute_sql(conn, increment_function_sql)
    print("Function increment_quality_match_counter created/updated.")
    
    # Create the trigger on match_suggestions
    trigger_sql = """
    DROP TRIGGER IF EXISTS quality_match_counter ON match_suggestions;
    CREATE TRIGGER quality_match_counter
    AFTER INSERT ON match_suggestions
    FOR EACH ROW
    EXECUTE FUNCTION increment_quality_match_counter();
    """
    execute_sql(conn, trigger_sql)
    print("Trigger quality_match_counter created on match_suggestions.")
    
    # Create the weekly reset function
    reset_function_sql = """
    CREATE OR REPLACE FUNCTION reset_all_weekly_counts()
    RETURNS TABLE(
        person_id INTEGER,
        plan_type VARCHAR,
        prev_weekly_matches INTEGER,
        prev_auto_discovery INTEGER,
        weekly_limit INTEGER
    ) AS $$
    BEGIN
        RETURN QUERY
        UPDATE client_profiles cp
        SET 
            current_weekly_matches = 0,
            last_weekly_match_reset = NOW(),
            last_auto_discovery_reset = NOW(),
            updated_at = NOW()
        WHERE 
            -- Reset if it's been more than 6 days since last reset
            (last_weekly_match_reset IS NULL 
             OR last_weekly_match_reset < NOW() - INTERVAL '6 days')
        RETURNING 
            cp.person_id,
            cp.plan_type,
            current_weekly_matches as prev_weekly_matches,
            0 as prev_auto_discovery,
            cp.weekly_match_allowance as weekly_limit;
    END;
    $$ LANGUAGE plpgsql;
    """
    execute_sql(conn, reset_function_sql)
    print("Function reset_all_weekly_counts created/updated.")
    
    # Create helper function to check if user can create matches
    helper_function_sql = """
    CREATE OR REPLACE FUNCTION can_create_quality_matches(
        p_person_id INTEGER,
        p_matches_to_create INTEGER DEFAULT 1
    ) RETURNS BOOLEAN AS $$
    DECLARE
        v_current_matches INTEGER;
        v_weekly_limit INTEGER;
        v_plan_type VARCHAR;
    BEGIN
        SELECT current_weekly_matches, weekly_match_allowance, plan_type
        INTO v_current_matches, v_weekly_limit, v_plan_type
        FROM client_profiles
        WHERE person_id = p_person_id;
        
        -- No profile = no limits (admin users)
        IF NOT FOUND THEN
            RETURN TRUE;
        END IF;
        
        -- Check against limit
        IF v_weekly_limit IS NULL THEN
            RETURN TRUE;  -- No limit set
        END IF;
        
        RETURN (v_current_matches + p_matches_to_create) <= v_weekly_limit;
    END;
    $$ LANGUAGE plpgsql;
    """
    execute_sql(conn, helper_function_sql)
    print("Function can_create_quality_matches created/updated.")
    
    # Create function to check limit before insert
    check_limit_function_sql = """
    CREATE OR REPLACE FUNCTION check_match_limit_before_insert(
        p_campaign_id UUID,
        p_vetting_score NUMERIC
    ) RETURNS BOOLEAN AS $$
    DECLARE
        v_person_id INTEGER;
        v_plan_type TEXT;
        v_current_matches INTEGER;
        v_weekly_limit INTEGER;
    BEGIN
        -- Only check for quality matches
        IF p_vetting_score < 50 THEN
            RETURN TRUE; -- Allow low-score matches
        END IF;
        
        -- Get user details
        SELECT c.person_id, cp.plan_type, cp.current_weekly_matches, cp.weekly_match_allowance
        INTO v_person_id, v_plan_type, v_current_matches, v_weekly_limit
        FROM campaigns c
        JOIN client_profiles cp ON c.person_id = cp.person_id
        WHERE c.campaign_id = p_campaign_id;
        
        -- No profile = admin/unlimited
        IF NOT FOUND THEN
            RETURN TRUE;
        END IF;
        
        -- Check limits
        IF v_weekly_limit IS NOT NULL AND v_current_matches >= v_weekly_limit THEN
            RAISE NOTICE 'User % has reached weekly limit of % matches', v_person_id, v_weekly_limit;
            RETURN FALSE;
        END IF;
        
        RETURN TRUE;
    END;
    $$ LANGUAGE plpgsql;
    """
    execute_sql(conn, check_limit_function_sql)
    print("Function check_match_limit_before_insert created/updated.")

def create_pitch_templates_table(conn):
    sql_statement = """
    CREATE TABLE pitch_templates (
        template_id TEXT PRIMARY KEY,
        media_type VARCHAR(100),
        target_media_type VARCHAR(100),
        language_code VARCHAR(10),
        tone VARCHAR(100),
        prompt_body TEXT,
        created_by TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """
    execute_sql(conn, sql_statement)
    print("Table PITCH_TEMPLATES created/ensured.")
 
def create_pitch_generations_table(conn):
    sql_statement = """
    CREATE TABLE pitch_generations (
        pitch_gen_id SERIAL PRIMARY KEY,
        campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        media_id INTEGER REFERENCES media(media_id) ON DELETE RESTRICT,
        template_id TEXT REFERENCES pitch_templates(template_id) ON DELETE RESTRICT,
        draft_text TEXT,
        ai_model_used TEXT,
        pitch_topic TEXT,
        temperature NUMERIC,
        generated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        reviewer_id TEXT,
        reviewed_at TIMESTAMPTZ,
        final_text TEXT,
        send_ready_bool BOOLEAN,
        generation_status VARCHAR(100)
    );
    CREATE INDEX IF NOT EXISTS idx_pitch_generations_campaign_id ON pitch_generations (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_pitch_generations_media_id ON pitch_generations (media_id);
    CREATE INDEX IF NOT EXISTS idx_pitch_generations_template_id ON pitch_generations (template_id);
    """
    execute_sql(conn, sql_statement)
    print("Table PITCH_GENERATIONS created/ensured.")
 
def create_placements_table(conn): # Renamed from BOOKINGS
    sql_statement = """
    CREATE TABLE placements (
        placement_id SERIAL PRIMARY KEY,
        campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        media_id INTEGER REFERENCES media(media_id) ON DELETE RESTRICT,
        pitch_id INTEGER REFERENCES pitches(pitch_id) ON DELETE SET NULL, 
        current_status VARCHAR(100),
        status_ts TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        meeting_date DATE,
        call_date DATE,
        outreach_topic TEXT,
        recording_date DATE,
        go_live_date DATE,
        episode_link TEXT,
        notes TEXT,
        email_thread JSONB DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_placements_campaign_id ON placements (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_placements_media_id ON placements (media_id);
    CREATE INDEX IF NOT EXISTS idx_placements_pitch_id ON placements (pitch_id);
    CREATE INDEX IF NOT EXISTS idx_placements_email_thread ON placements USING gin (email_thread);
    COMMENT ON COLUMN placements.email_thread IS 
    'Stores the full email conversation thread as JSONB array. Each element contains: 
    timestamp, direction (sent/received), from, to, subject, body_text, body_html, message_id, instantly_data';
    """
    execute_sql(conn, sql_statement)
    print("Table PLACEMENTS created/ensured.")
 
def create_pitches_table(conn):
    sql_statement = """
    CREATE TABLE pitches (
        pitch_id SERIAL PRIMARY KEY,
        campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        media_id INTEGER REFERENCES media(media_id) ON DELETE RESTRICT,
        attempt_no INTEGER,
        match_score NUMERIC,
        matched_keywords TEXT[],
        score_evaluated_at TIMESTAMPTZ,
        outreach_type VARCHAR(100),
        subject_line TEXT,
        body_snippet TEXT,
        send_ts TIMESTAMPTZ,
        reply_bool BOOLEAN,
        reply_ts TIMESTAMPTZ,
        instantly_lead_id TEXT, -- New column for Instantly Lead ID
        pitch_gen_id INTEGER REFERENCES pitch_generations(pitch_gen_id) ON DELETE SET NULL,
        placement_id INTEGER REFERENCES placements(placement_id) ON DELETE SET NULL, -- Renamed from booking_id
        pitch_state VARCHAR(100),
        client_approval_status VARCHAR(100),
        created_by TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        -- Nylas fields
        nylas_message_id VARCHAR(255),
        nylas_thread_id VARCHAR(255),
        nylas_draft_id VARCHAR(255),
        email_provider VARCHAR(50) DEFAULT 'instantly',
        opened_ts TIMESTAMPTZ,
        clicked_ts TIMESTAMPTZ,
        bounce_type VARCHAR(50),
        bounce_reason TEXT,
        bounced_ts TIMESTAMPTZ,
        -- Enhanced tracking fields from implementation plan
        tracking_label VARCHAR(255),
        open_count INTEGER DEFAULT 0,
        click_count INTEGER DEFAULT 0,
        scheduled_send_at TIMESTAMPTZ,
        send_status VARCHAR(50) DEFAULT 'pending' -- pending, scheduled, sent, failed
    );
    CREATE INDEX IF NOT EXISTS idx_pitches_campaign_id ON pitches (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_pitches_media_id ON pitches (media_id);
    CREATE INDEX IF NOT EXISTS idx_pitches_pitch_gen_id ON pitches (pitch_gen_id);
    CREATE INDEX IF NOT EXISTS idx_pitches_placement_id ON pitches (placement_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_pitches_instantly_lead_id ON pitches (instantly_lead_id) WHERE instantly_lead_id IS NOT NULL; -- Ensure uniqueness
    -- Nylas indexes
    CREATE INDEX IF NOT EXISTS idx_pitches_nylas_message_id ON pitches(nylas_message_id) WHERE nylas_message_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_pitches_nylas_thread_id ON pitches(nylas_thread_id) WHERE nylas_thread_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_pitches_email_provider ON pitches(email_provider);
    """
    execute_sql(conn, sql_statement)
    print("Table PITCHES created/ensured.")
 
def create_status_history_table(conn):
    sql_statement = """
    CREATE TABLE status_history (
        status_history_id SERIAL PRIMARY KEY,
        placement_id INTEGER REFERENCES placements(placement_id) ON DELETE CASCADE, -- Renamed from booking_id
        old_status VARCHAR(100),
        new_status VARCHAR(100),
        changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        changed_by TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_status_history_placement_id ON status_history (placement_id);
    """
    execute_sql(conn, sql_statement)
    print("Table STATUS_HISTORY created/ensured.")
 
def create_review_tasks(conn):
    sql_statement = """
    CREATE TABLE review_tasks (
        review_task_id SERIAL PRIMARY KEY,
        task_type VARCHAR(50) NOT NULL,
        related_id INTEGER NOT NULL,
        campaign_id UUID REFERENCES campaigns(campaign_id),
        assigned_to INTEGER REFERENCES people(person_id),
        status VARCHAR(50) DEFAULT 'pending',
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMPTZ,
        notes TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_review_tasks_campaign_id ON review_tasks (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_review_tasks_assigned_to ON review_tasks (assigned_to);
    """
    execute_sql(conn, sql_statement)
    print("Table REVIEW_TASKS created/ensured.")
 
def create_ai_usage_logs_table(conn):
    sql_statement = """
    CREATE TABLE ai_usage_logs (
        log_id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        workflow TEXT NOT NULL,
        model TEXT NOT NULL,
        tokens_in INTEGER NOT NULL,
        tokens_out INTEGER NOT NULL,
        total_tokens INTEGER NOT NULL,
        cost NUMERIC(10, 6) NOT NULL, -- Cost in USD, up to 6 decimal places
        execution_time_sec NUMERIC(10, 3), -- Execution time in seconds, up to 3 decimal places
        endpoint TEXT,
        related_pitch_gen_id INTEGER REFERENCES pitch_generations(pitch_gen_id) ON DELETE SET NULL, -- Link to pitch generation
        related_campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE SET NULL, -- Link to campaign
        related_media_id INTEGER REFERENCES media(media_id) ON DELETE SET NULL -- Link to media
    );
    CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_workflow ON ai_usage_logs (workflow);
    CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_model ON ai_usage_logs (model);
    CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_pitch_gen_id ON ai_usage_logs (related_pitch_gen_id);
    CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_campaign_id ON ai_usage_logs (related_campaign_id);
    CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_timestamp ON ai_usage_logs (timestamp);
    """
    execute_sql(conn, sql_statement)
    print("Table AI_USAGE_LOGS created/ensured.")

def create_media_kits_table(conn): # NEW FUNCTION
    """Creates the media_kits table."""
    sql_statement = """
    CREATE TABLE media_kits (
        media_kit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Using UUID as primary key
        campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE CASCADE NOT NULL,
        person_id INTEGER REFERENCES people(person_id) ON DELETE CASCADE NOT NULL,
        title TEXT,
        slug TEXT UNIQUE NOT NULL,
        is_public BOOLEAN DEFAULT TRUE NOT NULL,
        theme_preference TEXT DEFAULT 'modern',
        headline TEXT,
        tagline TEXT,
        introduction TEXT,
        full_bio_content TEXT,
        summary_bio_content TEXT,
        short_bio_content TEXT,
        bio_source TEXT,
        keywords TEXT[],
        talking_points JSONB DEFAULT '[]'::jsonb, -- Default to empty JSON array
        angles_source TEXT,
        sample_questions JSONB DEFAULT '[]'::jsonb,
        key_achievements JSONB DEFAULT '[]'::jsonb, -- Default to empty JSON array
        previous_appearances JSONB DEFAULT '[]'::jsonb, -- Default to empty JSON array
        person_social_links JSONB DEFAULT '{}'::jsonb, -- NEW: For client's own social media links
        social_media_stats JSONB DEFAULT '{}'::jsonb, -- Default to empty JSON object (for follower counts etc)
        testimonials_section TEXT,
        headshot_image_url TEXT,
        logo_image_url TEXT,
        call_to_action_text TEXT,
        call_to_action_url TEXT,
        show_contact_form BOOLEAN DEFAULT TRUE,
        contact_information_for_booking TEXT, -- General contact, email, phone, website from contactInfo
        custom_sections JSONB DEFAULT '[]'::jsonb, -- Default to empty JSON array
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_media_kits_campaign_id ON media_kits (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_media_kits_person_id ON media_kits (person_id);
    CREATE INDEX IF NOT EXISTS idx_media_kits_slug ON media_kits (slug);
    CREATE INDEX IF NOT EXISTS idx_media_kits_is_public ON media_kits (is_public);
    """
    execute_sql(conn, sql_statement)
    print("Table MEDIA_KITS created/ensured.")
    apply_timestamp_update_trigger(conn, "media_kits")

def create_campaign_media_discoveries(conn):
    """Create enhanced campaign_media_discoveries table to track discovery, enrichment, and vetting workflow"""
    print("Creating campaign_media_discoveries table...")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_media_discoveries (
            id SERIAL PRIMARY KEY,
            campaign_id UUID NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
            media_id INTEGER NOT NULL REFERENCES media(media_id) ON DELETE CASCADE,
            discovery_keyword TEXT NOT NULL,
            discovered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            
            -- ENRICHMENT TRACKING
            enrichment_status TEXT DEFAULT 'pending' CHECK (enrichment_status IN ('pending', 'in_progress', 'completed', 'failed')),
            enrichment_completed_at TIMESTAMP WITH TIME ZONE,
            enrichment_error TEXT,
            
            -- VETTING TRACKING  
            vetting_status TEXT DEFAULT 'pending' CHECK (vetting_status IN ('pending', 'in_progress', 'completed', 'failed')),
            vetting_score NUMERIC(4,2),
            vetting_reasoning TEXT,
            vetting_criteria_met JSONB,
            topic_match_analysis TEXT,
            vetting_criteria_scores JSONB,
            client_expertise_matched TEXT[],
            vetted_at TIMESTAMP WITH TIME ZONE,
            vetting_error TEXT,
            
            -- MATCH CREATION TRACKING
            match_created BOOLEAN DEFAULT FALSE,
            match_suggestion_id INTEGER REFERENCES match_suggestions(match_id),
            match_created_at TIMESTAMP WITH TIME ZONE,
            
            -- REVIEW TRACKING
            review_task_created BOOLEAN DEFAULT FALSE,
            review_task_id INTEGER,
            review_status TEXT DEFAULT 'pending' CHECK (review_status IN ('pending', 'approved', 'rejected')),
            reviewed_at TIMESTAMP WITH TIME ZONE,
            
            CONSTRAINT unique_campaign_media UNIQUE(campaign_id, media_id)
        );
    """)
    
    # Create indexes for better performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_media_discoveries_campaign_id 
        ON campaign_media_discoveries(campaign_id);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_media_discoveries_media_id 
        ON campaign_media_discoveries(media_id);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_media_discoveries_discovered_at 
        ON campaign_media_discoveries(discovered_at);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_media_discoveries_enrichment_status 
        ON campaign_media_discoveries(enrichment_status);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_media_discoveries_vetting_status 
        ON campaign_media_discoveries(vetting_status);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_media_discoveries_vetting_score 
        ON campaign_media_discoveries(vetting_score);
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_media_discoveries_review_status 
        ON campaign_media_discoveries(review_status);
    """)
    
    print("Campaign media discoveries table created successfully.")

def create_password_reset_tokens_table(conn):
    """Create password_reset_tokens table"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY,
            person_id INTEGER NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
            token VARCHAR(255) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_by_ip VARCHAR(45)
        );
        
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token 
        ON password_reset_tokens(token);
        
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_person_id 
        ON password_reset_tokens(person_id);
        
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires_at 
        ON password_reset_tokens(expires_at);
    """)

def create_payment_methods_table(conn):
    """Create payment_methods table for storing Stripe payment methods"""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS payment_methods (
        id SERIAL PRIMARY KEY,
        person_id INTEGER REFERENCES people(person_id) ON DELETE CASCADE,
        stripe_payment_method_id VARCHAR(255) UNIQUE NOT NULL,
        type VARCHAR(50) NOT NULL,
        last4 VARCHAR(4),
        brand VARCHAR(50),
        exp_month INTEGER,
        exp_year INTEGER,
        is_default BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_payment_methods_person_id ON payment_methods(person_id);
    """
    execute_sql(conn, sql_statement)
    print("Table PAYMENT_METHODS created/ensured.")
    apply_timestamp_update_trigger(conn, "payment_methods")

def create_subscription_history_table(conn):
    """Create subscription_history table for tracking subscription changes"""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS subscription_history (
        id SERIAL PRIMARY KEY,
        client_profile_id INTEGER REFERENCES client_profiles(client_profile_id) ON DELETE CASCADE,
        stripe_subscription_id VARCHAR(255) NOT NULL,
        stripe_price_id VARCHAR(255) NOT NULL,
        stripe_product_id VARCHAR(255),
        plan_type VARCHAR(50) NOT NULL,
        status VARCHAR(50) NOT NULL,
        current_period_start TIMESTAMPTZ NOT NULL,
        current_period_end TIMESTAMPTZ NOT NULL,
        cancel_at_period_end BOOLEAN DEFAULT FALSE,
        canceled_at TIMESTAMPTZ,
        ended_at TIMESTAMPTZ,
        trial_start TIMESTAMPTZ,
        trial_end TIMESTAMPTZ,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_subscription_history_client_profile_id ON subscription_history(client_profile_id);
    CREATE INDEX IF NOT EXISTS idx_subscription_history_stripe_subscription_id ON subscription_history(stripe_subscription_id);
    CREATE INDEX IF NOT EXISTS idx_subscription_history_status ON subscription_history(status);
    """
    execute_sql(conn, sql_statement)
    print("Table SUBSCRIPTION_HISTORY created/ensured.")
    apply_timestamp_update_trigger(conn, "subscription_history")

def create_invoices_table(conn):
    """Create invoices table for storing Stripe invoices"""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS invoices (
        id SERIAL PRIMARY KEY,
        person_id INTEGER REFERENCES people(person_id) ON DELETE CASCADE,
        stripe_invoice_id VARCHAR(255) UNIQUE NOT NULL,
        stripe_subscription_id VARCHAR(255),
        invoice_number VARCHAR(255),
        amount_paid INTEGER NOT NULL,
        amount_due INTEGER NOT NULL,
        currency VARCHAR(3) NOT NULL,
        status VARCHAR(50) NOT NULL,
        billing_reason VARCHAR(100),
        invoice_pdf VARCHAR(500),
        hosted_invoice_url VARCHAR(500),
        paid_at TIMESTAMPTZ,
        due_date TIMESTAMPTZ,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_invoices_person_id ON invoices(person_id);
    CREATE INDEX IF NOT EXISTS idx_invoices_stripe_subscription_id ON invoices(stripe_subscription_id);
    CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
    CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at);
    """
    execute_sql(conn, sql_statement)
    print("Table INVOICES created/ensured.")

def create_price_products_table(conn):
    """Create price_products table for storing Stripe product/price information"""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS price_products (
        id SERIAL PRIMARY KEY,
        stripe_product_id VARCHAR(255) UNIQUE NOT NULL,
        stripe_price_id VARCHAR(255) UNIQUE NOT NULL,
        plan_type VARCHAR(50) NOT NULL,
        billing_period VARCHAR(20) NOT NULL,
        amount INTEGER NOT NULL,
        currency VARCHAR(3) NOT NULL,
        active BOOLEAN DEFAULT TRUE,
        features JSONB DEFAULT '{}',
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_price_products_active ON price_products(active);
    CREATE INDEX IF NOT EXISTS idx_price_products_plan_type ON price_products(plan_type);
    """
    execute_sql(conn, sql_statement)
    print("Table PRICE_PRODUCTS created/ensured.")
    apply_timestamp_update_trigger(conn, "price_products")

def create_webhook_events_table(conn):
    """Create webhook_events table for Stripe webhook idempotency"""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS webhook_events (
        id SERIAL PRIMARY KEY,
        stripe_event_id VARCHAR(255) UNIQUE NOT NULL,
        event_type VARCHAR(100) NOT NULL,
        processed BOOLEAN DEFAULT FALSE,
        error_message TEXT,
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        processed_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_webhook_events_stripe_event_id ON webhook_events(stripe_event_id);
    CREATE INDEX IF NOT EXISTS idx_webhook_events_processed ON webhook_events(processed);
    """
    execute_sql(conn, sql_statement)
    print("Table WEBHOOK_EVENTS created/ensured.")

def create_email_sync_status_table(conn):
    """Create table to track email sync status and processing."""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS email_sync_status (
        sync_id SERIAL PRIMARY KEY,
        grant_id VARCHAR(255) NOT NULL,
        last_sync_timestamp TIMESTAMPTZ,
        last_message_timestamp TIMESTAMPTZ,
        sync_cursor VARCHAR(500),
        messages_processed INTEGER DEFAULT 0,
        sync_status VARCHAR(50) DEFAULT 'active',
        error_count INTEGER DEFAULT 0,
        last_error TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_email_sync_grant_id ON email_sync_status(grant_id);
    CREATE INDEX IF NOT EXISTS idx_email_sync_status ON email_sync_status(sync_status);
    """
    execute_sql(conn, sql_statement)
    print("Table EMAIL_SYNC_STATUS created/ensured.")
    apply_timestamp_update_trigger(conn, "email_sync_status")

def create_processed_emails_table(conn):
    """Create table to track processed email messages."""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS processed_emails (
        id SERIAL PRIMARY KEY,
        message_id VARCHAR(255) UNIQUE NOT NULL,
        thread_id VARCHAR(255),
        grant_id VARCHAR(255),
        processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        processing_type VARCHAR(50), -- 'reply', 'bounce', 'opened', etc.
        pitch_id INTEGER REFERENCES pitches(pitch_id),
        placement_id INTEGER REFERENCES placements(placement_id),
        metadata JSONB DEFAULT '{}'::jsonb
    );
    
    CREATE INDEX IF NOT EXISTS idx_processed_emails_message_id ON processed_emails(message_id);
    CREATE INDEX IF NOT EXISTS idx_processed_emails_thread_id ON processed_emails(thread_id);
    CREATE INDEX IF NOT EXISTS idx_processed_emails_grant_id ON processed_emails(grant_id);
    CREATE INDEX IF NOT EXISTS idx_processed_emails_processed_at ON processed_emails(processed_at);
    """
    execute_sql(conn, sql_statement)
    print("Table PROCESSED_EMAILS created/ensured.")

def create_message_events_table(conn):
    """Create message_events table for comprehensive event tracking."""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS message_events (
        event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id VARCHAR(255) NOT NULL,
        pitch_id INTEGER REFERENCES pitches(pitch_id),
        event_type VARCHAR(50) NOT NULL, -- opened, clicked, bounced, replied, send_success, send_failed
        timestamp TIMESTAMPTZ NOT NULL,
        payload_json JSONB,
        ip_address INET,
        user_agent TEXT,
        link_url TEXT,
        is_duplicate BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_message_events_message_id ON message_events(message_id);
    CREATE INDEX IF NOT EXISTS idx_message_events_pitch_id ON message_events(pitch_id);
    CREATE INDEX IF NOT EXISTS idx_message_events_type_timestamp ON message_events(event_type, timestamp);
    """
    execute_sql(conn, sql_statement)
    print("Table MESSAGE_EVENTS created/ensured.")

def create_contact_status_table(conn):
    """Create contact_status table for email deliverability management."""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS contact_status (
        email VARCHAR(255) PRIMARY KEY,
        status VARCHAR(50) DEFAULT 'active', -- active, bounced, cleaned, do_not_contact
        last_bounce_reason TEXT,
        bounce_count INTEGER DEFAULT 0,
        hard_bounce_count INTEGER DEFAULT 0,
        soft_bounce_count INTEGER DEFAULT 0,
        do_not_contact BOOLEAN DEFAULT FALSE,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_contact_status_status ON contact_status(status);
    CREATE INDEX IF NOT EXISTS idx_contact_status_do_not_contact ON contact_status(do_not_contact);
    """
    execute_sql(conn, sql_statement)
    print("Table CONTACT_STATUS created/ensured.")
    apply_timestamp_update_trigger(conn, "contact_status")

def create_send_queue_table(conn):
    """Create send_queue table for throttling and scheduled sends."""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS send_queue (
        queue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pitch_id INTEGER REFERENCES pitches(pitch_id),
        grant_id VARCHAR(255) NOT NULL,
        scheduled_for TIMESTAMPTZ NOT NULL,
        priority INTEGER DEFAULT 5,
        attempts INTEGER DEFAULT 0,
        last_attempt_at TIMESTAMPTZ,
        status VARCHAR(50) DEFAULT 'pending', -- pending, processing, sent, failed
        error_message TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_send_queue_status_scheduled ON send_queue(status, scheduled_for);
    CREATE INDEX IF NOT EXISTS idx_send_queue_grant_id ON send_queue(grant_id);
    """
    execute_sql(conn, sql_statement)
    print("Table SEND_QUEUE created/ensured.")

def create_chatbot_conversations_table(conn):
    """Create chatbot_conversations table for storing chatbot conversation sessions"""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS chatbot_conversations (
        conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        person_id INTEGER REFERENCES people(person_id) ON DELETE CASCADE,
        status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'abandoned')),
        conversation_phase VARCHAR(50) DEFAULT 'introduction',
        messages JSONB DEFAULT '[]'::jsonb,
        extracted_data JSONB DEFAULT '{}'::jsonb,
        conversation_metadata JSONB DEFAULT '{}'::jsonb,
        progress INTEGER DEFAULT 0,
        started_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        last_activity_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_campaign_id ON chatbot_conversations(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_person_id ON chatbot_conversations(person_id);
    CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_status ON chatbot_conversations(status);
    CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_last_activity ON chatbot_conversations(last_activity_at);
    """
    execute_sql(conn, sql_statement)
    print("Table CHATBOT_CONVERSATIONS created/ensured.")
    apply_timestamp_update_trigger(conn, "chatbot_conversations")

def create_conversation_insights_table(conn):
    """Create conversation_insights table for storing extracted insights from chatbot conversations"""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS conversation_insights (
        insight_id SERIAL PRIMARY KEY,
        conversation_id UUID REFERENCES chatbot_conversations(conversation_id) ON DELETE CASCADE,
        insight_type VARCHAR(100), -- 'keyword', 'story', 'angle', 'achievement'
        content JSONB NOT NULL,
        confidence_score NUMERIC(3,2),
        extracted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_conversation_insights_conversation_id ON conversation_insights(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_conversation_insights_type ON conversation_insights(insight_type);
    CREATE INDEX IF NOT EXISTS idx_conversation_insights_confidence ON conversation_insights(confidence_score);
    """
    execute_sql(conn, sql_statement)
    print("Table CONVERSATION_INSIGHTS created/ensured.")

def create_match_notification_log_table(conn):
    """Creates MATCH_NOTIFICATION_LOG table for tracking match notification emails sent to clients"""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS match_notification_log (
        notification_id     SERIAL PRIMARY KEY,
        campaign_id         UUID NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        person_id           INTEGER NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
        match_count         INTEGER NOT NULL, -- Number of matches at time of notification
        sent_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_at          TIMESTAMPTZ DEFAULT NOW()
    );
    
    -- Index for checking when we last sent notification for a campaign
    CREATE INDEX IF NOT EXISTS idx_notification_log_campaign_sent 
        ON match_notification_log(campaign_id, sent_at DESC);
    CREATE INDEX IF NOT EXISTS idx_notification_log_person 
        ON match_notification_log(person_id, sent_at DESC);
    """
    execute_sql(conn, sql_statement)
    print("Table MATCH_NOTIFICATION_LOG created/ensured.")

def drop_all_tables(conn):
    """Drops all known tables in the database, in an order suitable for dependencies if CASCADE is not fully effective."""
    # Order for dropping: from tables that are referenced by others to tables that are not, 
    # or essentially reverse of creation order. CASCADE should make the order less critical, but explicit order can help.
    table_names_in_drop_order = [
        "CONVERSATION_INSIGHTS", # FK to CHATBOT_CONVERSATIONS
        "CHATBOT_CONVERSATIONS", # FKs to CAMPAIGNS, PEOPLE
        "MATCH_NOTIFICATION_LOG", # FKs to CAMPAIGNS, PEOPLE
        "SEND_QUEUE",         # FK to PITCHES
        "MESSAGE_EVENTS",     # FK to PITCHES
        "PROCESSED_EMAILS",   # FKs to PITCHES, PLACEMENTS
        "CONTACT_STATUS",     # No FKs
        "EMAIL_SYNC_STATUS",  # No FKs
        "WEBHOOK_EVENTS",     # No FKs, drop first
        "INVOICES",           # FK to PEOPLE
        "SUBSCRIPTION_HISTORY", # FK to CLIENT_PROFILES
        "PAYMENT_METHODS",    # FK to PEOPLE
        "PRICE_PRODUCTS",     # No FKs
        "PASSWORD_RESET_TOKENS", # FK to PEOPLE
        "CAMPAIGN_MEDIA_DISCOVERIES", # FKs to CAMPAIGNS, MEDIA, MATCH_SUGGESTIONS
        "AI_USAGE_LOGS",      # New table, drop first if it references others
        "STATUS_HISTORY",     # FK to PLACEMENTS
        "PITCHES",            # FKs to CAMPAIGNS, MEDIA, PITCH_GENERATIONS, PLACEMENTS
        "PITCH_GENERATIONS",  # FKs to CAMPAIGNS, MEDIA, PITCH_TEMPLATES
        "PLACEMENTS",         # FKs to CAMPAIGNS, MEDIA
        "MEDIA_KITS",         # ADDED to drop order
        "MATCH_SUGGESTIONS",  # FKs to CAMPAIGNS, MEDIA
        "PITCH_TEMPLATES",
        "EPISODES",           # FK to MEDIA
        "MEDIA_PEOPLE",       # FKs to MEDIA, PEOPLE
        "REVIEW_TASKS",       # FKs to CAMPAIGNS, PEOPLE
        "CAMPAIGNS",          # FK to PEOPLE
        "MEDIA",              # FK to COMPANIES
        "CLIENT_PROFILES",    # FK to PEOPLE
        "PEOPLE",             # FK to COMPANIES
        "COMPANIES"           # Base table - should be last or rely entirely on CASCADE from dependents
    ]
 
    print("Attempting to drop tables...")
    all_drops_attempted_successfully = True
    try:
        with conn.cursor() as cur:
            for table_name in table_names_in_drop_order:
                try:
                    print(f"  Executing: DROP TABLE IF EXISTS {table_name} CASCADE;")
                    cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE;").format(sql.Identifier(table_name)))
                    print(f"  Command executed for: {table_name}")
                except psycopg2.Error as e:
                    print(f"  ERROR explicitly trying to drop table {table_name}: {e}")
                    all_drops_attempted_successfully = False
            
            if all_drops_attempted_successfully:
                conn.commit()
                print("All table drop commands executed and transaction committed.")
            else:
                conn.rollback()
                print("Errors occurred during table drop commands. Transaction rolled back.")
                raise Exception("Failed to execute all DROP TABLE commands cleanly. Aborting schema creation.") 
 
    except psycopg2.Error as e: 
        print(f"A database error occurred during the drop_all_tables operation: {e}")
        if conn and not conn.closed:
            try: conn.rollback()
            except psycopg2.Error as rb_e: print(f"Further error during rollback: {rb_e}")
        raise 
    except Exception as e: 
        print(f"An unexpected Python error occurred in drop_all_tables: {e}")
        if conn and not conn.closed:
            try: conn.rollback()
            except psycopg2.Error as rb_e: print(f"Further error during rollback: {rb_e}")
        if not isinstance(e, psycopg2.Error): 
             raise 
 
# --- Main Execution ---
def create_all_tables():
    """Creates all defined tables in the correct order."""
    conn = get_db_connection()
    if not conn:
        print("Database connection failed. Aborting table creation.")
        return
 
    try:
        # Drop all tables first to ensure a clean slate
        # Uncomment the line below if you want to drop tables before creating them
        # drop_all_tables(conn)
 
        # Create helper function for triggers first
        create_timestamp_update_trigger_function(conn)
 
        # Create tables in order of dependency
        create_companies_table(conn)
        create_people_table(conn) # Depends on COMPANIES (indirectly via trigger), applies trigger
        create_client_profiles_table(conn) # Depends on PEOPLE
        create_media_table(conn) # Depends on COMPANIES
        create_media_people_table(conn) # Depends on MEDIA, PEOPLE
        create_campaigns_table(conn) # Depends on PEOPLE
        create_episodes_table(conn) # Depends on MEDIA
        create_pitch_templates_table(conn)
        create_match_suggestions(conn) # Depends on CAMPAIGNS, MEDIA
        create_review_tasks(conn) # Depends on CAMPAIGNS, PEOPLE
        create_pitch_generations_table(conn) # Depends on CAMPAIGNS, MEDIA, PITCH_TEMPLATES
        create_placements_table(conn) # Depends on CAMPAIGNS, MEDIA
        create_pitches_table(conn) # Depends on CAMPAIGNS, MEDIA, PITCH_GENERATIONS, PLACEMENTS
        create_status_history_table(conn) # Depends on PLACEMENTS
        create_ai_usage_logs_table(conn) # NEW: Depends on PITCH_GENERATIONS, CAMPAIGNS, MEDIA
        create_media_kits_table(conn) # ADDED: Depends on CAMPAIGNS, PEOPLE
        create_campaign_media_discoveries(conn) # WORKFLOW OPTIMIZATION: Depends on CAMPAIGNS, MEDIA
        create_password_reset_tokens_table(conn)
        # Create Stripe-related tables
        create_payment_methods_table(conn)
        create_subscription_history_table(conn)
        create_invoices_table(conn)
        create_price_products_table(conn)
        create_webhook_events_table(conn)
        # Create Nylas-related tables
        create_email_sync_status_table(conn)
        create_processed_emails_table(conn) # Depends on PITCHES, PLACEMENTS
        create_message_events_table(conn) # Depends on PITCHES
        create_contact_status_table(conn)
        create_send_queue_table(conn) # Depends on PITCHES
        # Create chatbot-related tables
        create_chatbot_conversations_table(conn) # Depends on CAMPAIGNS, PEOPLE
        create_conversation_insights_table(conn) # Depends on CHATBOT_CONVERSATIONS
        # Create notification tracking table
        create_match_notification_log_table(conn) # Depends on CAMPAIGNS, PEOPLE
        
        print("All tables checked/created successfully.")
    except psycopg2.Error as e:
        print(f"A database error occurred during table creation: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")
 
if __name__ == "__main__":
    print("Starting database schema creation process...")
    create_all_tables()
    print("Schema creation process finished.")
 