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
        email                     TEXT       UNIQUE,
        linkedin_profile_url      TEXT,
        twitter_profile_url       TEXT,
        instagram_profile_url     TEXT,
        tiktok_profile_url        TEXT,
        dashboard_username        TEXT,
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
        privacy_settings          JSONB DEFAULT '{}'::jsonb
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
        plan_type                 VARCHAR(50) DEFAULT 'free' NOT NULL, -- e.g., 'free', 'paid_basic', 'paid_premium'
        daily_discovery_allowance INTEGER DEFAULT 10 NOT NULL,
        weekly_discovery_allowance INTEGER DEFAULT 50 NOT NULL,
        current_daily_discoveries INTEGER DEFAULT 0 NOT NULL,
        current_weekly_discoveries INTEGER DEFAULT 0 NOT NULL,
        last_daily_reset          DATE DEFAULT CURRENT_DATE,
        last_weekly_reset         DATE DEFAULT CURRENT_DATE, -- Could be Monday of the week
        subscription_provider_id  VARCHAR(255), -- e.g., Stripe subscription ID
        subscription_status       VARCHAR(50),  -- e.g., 'active', 'canceled', 'past_due'
        subscription_ends_at      TIMESTAMPTZ,
        created_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_client_profiles_person_id ON client_profiles (person_id);
    CREATE INDEX IF NOT EXISTS idx_client_profiles_plan_type ON client_profiles (plan_type);
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
        rss_url                   TEXT,
        category                  TEXT,
        language                  VARCHAR(50),
        image_url                 TEXT,
        avg_downloads             INTEGER,
        contact_email             TEXT,
        fetched_episodes          BOOLEAN,
        description               TEXT,
        ai_description            TEXT,
        embedding                 VECTOR(1536),
        created_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- NEW: Add updated_at
        last_fetched_at           TIMESTAMPTZ,
        latest_episode_date       DATE, -- This will be updated by enrichment
 
        -- new profile_data fields from EnrichedPodcastProfile
        source_api                TEXT,
        api_id                    TEXT UNIQUE, -- NEW: Make api_id unique for easier lookup
        title                     TEXT,
        website                   TEXT,
        podcast_spotify_id        TEXT,
        itunes_id                 TEXT,
        total_episodes            INTEGER,
        last_posted_at            TIMESTAMPTZ, -- This is likely redundant with latest_episode_date, consider removing one
        rss_feed_url              TEXT, -- Redundant with rss_url, but keeping for now
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
        -- NEW FIELDS FOR ENRICHMENT SUPPORT
        quality_score             NUMERIC,     -- Calculated quality score
        first_episode_date        DATE         -- When the podcast first published an episode
    );
 
    CREATE INDEX IF NOT EXISTS idx_media_company_id           ON media (company_id);
    CREATE INDEX IF NOT EXISTS idx_media_embedding_hnsw       ON media USING hnsw (embedding vector_cosine_ops);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_media_api_id        ON media (api_id);
    """
    execute_sql(conn, sql_statement)
    print("Table MEDIA created/ensured with extended profile_data columns.")
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
        mock_interview_trancript TEXT,
        embedding VECTOR(1536),
        start_date DATE,
        end_date DATE,
        goal_note TEXT,
        media_kit_url TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        instantly_campaign_id TEXT,
        questionnaire_responses JSONB,
        ideal_podcast_description TEXT  -- *** NEW FIELD ***
    );
    CREATE INDEX IF NOT EXISTS idx_campaigns_person_id ON CAMPAIGNS (person_id);
    CREATE INDEX IF NOT EXISTS idx_campaigns_embedding_hnsw ON CAMPAIGNS USING hnsw (embedding vector_cosine_ops);
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
        ai_analysis_done BOOLEAN DEFAULT FALSE
    );
    CREATE INDEX IF NOT EXISTS idx_episodes_media_id ON episodes (media_id);
    CREATE INDEX IF NOT EXISTS idx_episodes_embedding_hnsw ON episodes USING hnsw (embedding vector_cosine_ops);
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
        last_vetted_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_match_suggestions_campaign_id ON match_suggestions (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_match_suggestions_media_id ON match_suggestions (media_id);
    CREATE INDEX IF NOT EXISTS idx_match_suggestions_best_episode_id ON match_suggestions (best_matching_episode_id);
    """
    execute_sql(conn, sql_statement)
    print("Table MATCH_SUGGESTIONS created/ensured.")
 
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
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_placements_campaign_id ON placements (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_placements_media_id ON placements (media_id);
    CREATE INDEX IF NOT EXISTS idx_placements_pitch_id ON placements (pitch_id); -- <<< ADD THIS INDEX
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
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_pitches_campaign_id ON pitches (campaign_id);
    CREATE INDEX IF NOT EXISTS idx_pitches_media_id ON pitches (media_id);
    CREATE INDEX IF NOT EXISTS idx_pitches_pitch_gen_id ON pitches (pitch_gen_id);
    CREATE INDEX IF NOT EXISTS idx_pitches_placement_id ON pitches (placement_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_pitches_instantly_lead_id ON pitches (instantly_lead_id) WHERE instantly_lead_id IS NOT NULL; -- Ensure uniqueness
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
        headshot_image_urls TEXT[],
        logo_image_url TEXT,
        call_to_action_text TEXT,
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

def drop_all_tables(conn):
    """Drops all known tables in the database, in an order suitable for dependencies if CASCADE is not fully effective."""
    # Order for dropping: from tables that are referenced by others to tables that are not, 
    # or essentially reverse of creation order. CASCADE should make the order less critical, but explicit order can help.
    table_names_in_drop_order = [
        "AI_USAGE_LOGS", # New table, drop first if it references others
        "STATUS_HISTORY",       # FK to PLACEMENTS
        "PITCHES",            # FKs to CAMPAIGNS, MEDIA, PITCH_GENERATIONS, PLACEMENTS
        "PITCH_GENERATIONS",  # FKs to CAMPAIGNS, MEDIA, PITCH_TEMPLATES
        "PLACEMENTS",         # FKs to CAMPAIGNS, MEDIA
        "MEDIA_KITS",         # ADDED to drop order
        "PITCH_TEMPLATES",
        "EPISODES",           # FK to MEDIA
        "MEDIA_PEOPLE",       # FKs to MEDIA, PEOPLE
        "REVIEW_TASKS",       # FKs to CAMPAIGNS, PEOPLE
        "CAMPAIGNS",          # FK to PEOPLE
        "MEDIA",              # FK to COMPANIES
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
        create_password_reset_tokens_table(conn)
        
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
 