import os
from dotenv import load_dotenv

load_dotenv()
 
# Database
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
# Add other config variables here 