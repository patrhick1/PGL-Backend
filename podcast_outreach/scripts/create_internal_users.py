# podcast_outreach/scripts/create_internal_users.py
import asyncio
import os
import sys
from getpass import getpass # For securely getting password input
from typing import Optional

# Add project root to sys.path to allow importing project modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from podcast_outreach.database.connection import init_db_pool, close_db_pool
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.api.dependencies import hash_password # For hashing
from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, '.env')) # Load .env from project root

async def create_user(email: str, full_name: str, role: str, dashboard_username: Optional[str] = None):
    """Creates a user in the people table."""
    
    # Use email as dashboard_username if not provided
    final_dashboard_username = dashboard_username if dashboard_username else email

    existing_by_email = await people_queries.get_person_by_email_from_db(email)
    if existing_by_email:
        print(f"User with email '{email}' already exists (Person ID: {existing_by_email['person_id']}). Skipping.")
        return

    if final_dashboard_username != email: # Also check if dashboard_username is taken if it's different
        existing_by_username = await people_queries.get_person_by_dashboard_username(final_dashboard_username)
        if existing_by_username:
            print(f"User with dashboard username '{final_dashboard_username}' already exists (Person ID: {existing_by_username['person_id']}). Skipping.")
            return

    while True:
        password = getpass(f"Enter password for {role} '{full_name}' ({email}): ")
        password_confirm = getpass("Confirm password: ")
        if password == password_confirm:
            if len(password) < 8: # Basic complexity, enhance as needed
                print("Password must be at least 8 characters long. Please try again.")
            else:
                break
        else:
            print("Passwords do not match. Please try again.")

    password_hash = hash_password(password)

    user_data = {
        "full_name": full_name,
        "email": email,
        "role": role,
        "dashboard_username": final_dashboard_username,
        "dashboard_password_hash": password_hash,
        # Add other fields like company_id if necessary for admin/staff
    }
    
    created_person = await people_queries.create_person_in_db(user_data)
    if created_person:
        print(f"Successfully created {role} user: {full_name} (Email: {email}, Person ID: {created_person['person_id']})")
    else:
        print(f"Failed to create {role} user: {full_name} ({email})")

async def main():
    print("--- Create Internal Users Script ---")
    await init_db_pool()

    try:
        # Create Admin User
        admin_email = input("Enter admin email (e.g., admin@pgl.com): ").strip()
        admin_full_name = input("Enter admin full name (e.g., Admin User): ").strip()
        admin_dashboard_username = input(f"Enter admin dashboard username (default: {admin_email}): ").strip() or admin_email
        if admin_email and admin_full_name:
            await create_user(admin_email, admin_full_name, "admin", admin_dashboard_username)
        else:
            print("Admin email and full name are required. Skipping admin creation.")

        print("\n---")

        # Create Staff User
        staff_email = input("Enter staff email (e.g., staff@pgl.com): ").strip()
        staff_full_name = input("Enter staff full name (e.g., Staff User): ").strip()
        staff_dashboard_username = input(f"Enter staff dashboard username (default: {staff_email}): ").strip() or staff_email
        if staff_email and staff_full_name:
            await create_user(staff_email, staff_full_name, "staff", staff_dashboard_username)
        else:
            print("Staff email and full name are required. Skipping staff creation.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await close_db_pool()
        print("--- Script Finished ---")

if __name__ == "__main__":
    asyncio.run(main())