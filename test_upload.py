import requests
import os
import json
import logging

# --- Configuration ---
# Make sure your FastAPI server is running before executing this script.
BASE_URL = "http://localhost:8000"

# --- IMPORTANT: UPDATE WITH YOUR TEST USER CREDENTIALS ---
# This user must exist in your 'people' table with a hashed password.
USERNAME = "paschal@3rdbrain.co"  # The email of the user to test with
PASSWORD = "PGL_master_admin"      # The plain-text password for that user

# --- Test File Details ---
TEST_FILE_NAME = "test_profile_image.png"
TEST_FILE_CONTENT_TYPE = "image/png"
# Create a tiny, valid 1x1 PNG pixel for the test upload
TINY_PNG_DATA = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_upload_test():
    """
    Executes the end-to-end test for the file upload process.
    """
    # Use a requests.Session to automatically handle cookies after login
    session = requests.Session()
    
    # --- Step 0: Create a dummy file for uploading ---
    logger.info(f"Creating a dummy file named '{TEST_FILE_NAME}' for the test.")
    try:
        with open(TEST_FILE_NAME, "wb") as f:
            f.write(TINY_PNG_DATA)
    except IOError as e:
        logger.error(f"Failed to create dummy file: {e}")
        return False

    try:
        # --- Step 1: Authenticate with the backend ---
        logger.info(f"[STEP 1/4] Authenticating user '{USERNAME}'...")
        login_payload = {'username': USERNAME, 'password': PASSWORD}
        login_response = session.post(f"{BASE_URL}/auth/token", data=login_payload)

        if login_response.status_code != 200:
            logger.error(f"Login failed! Status: {login_response.status_code}, Response: {login_response.text}")
            return False
        logger.info("Authentication successful. Session cookie obtained.")

        # --- Step 2: Generate the presigned upload URL ---
        logger.info("[STEP 2/4] Requesting presigned URL from the backend...")
        generate_url_payload = {
            "fileName": TEST_FILE_NAME,
            "uploadContext": "profile_picture"
        }
        generate_url_response = session.post(f"{BASE_URL}/storage/generate-upload-url", json=generate_url_payload)

        if generate_url_response.status_code != 200:
            logger.error(f"Failed to get presigned URL! Status: {generate_url_response.status_code}, Response: {generate_url_response.text}")
            return False
        
        upload_data = generate_url_response.json()
        upload_url = upload_data.get("uploadUrl")
        final_url = upload_data.get("finalUrl")

        if not upload_url:
            logger.error(f"Backend response did not contain a valid 'uploadUrl'. Response: {upload_data}")
            return False
        logger.info("Successfully received presigned URL from backend.")

        # --- Step 3: Upload the file directly to S3 ---
        logger.info("[STEP 3/4] Uploading file directly to S3 presigned URL...")
        with open(TEST_FILE_NAME, 'rb') as f:
            # IMPORTANT: Use a clean `requests.put`, NOT `session.put`.
            # The session object would send our backend's auth cookie, which S3 would reject.
            s3_response = requests.put(upload_url, data=f, headers={'Content-Type': TEST_FILE_CONTENT_TYPE})

        if s3_response.status_code != 200:
            logger.error(f"S3 upload failed! Status: {s3_response.status_code}, Response: {s3_response.text}")
            logger.error("This likely means your S3 bucket's CORS policy is missing or incorrect.")
            return False
        logger.info("File successfully uploaded to S3.")

        # --- Step 4: Confirm the upload with the backend ---
        logger.info("[STEP 4/4] Confirming upload with backend and updating user profile...")
        update_profile_payload = {"profile_image_url": final_url}
        update_response = session.patch(f"{BASE_URL}/users/me/profile-image", json=update_profile_payload)

        if update_response.status_code != 200:
            logger.error(f"Failed to update profile with new image URL! Status: {update_response.status_code}, Response: {update_response.text}")
            return False
        
        logger.info("Backend successfully updated with the new profile image URL.")
        logger.info(f"Final public URL: {update_response.json().get('profile_image_url')}")

        return True

    except requests.exceptions.ConnectionError:
        logger.error(f"Connection Error: Could not connect to the backend at {BASE_URL}. Is the server running?")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return False
    finally:
        # --- Cleanup: Remove the dummy file ---
        if os.path.exists(TEST_FILE_NAME):
            os.remove(TEST_FILE_NAME)
            logger.info(f"Cleaned up dummy file '{TEST_FILE_NAME}'.")


if __name__ == "__main__":
    logger.info("--- Starting End-to-End File Upload Test ---")
    success = run_upload_test()
    print("\n" + "="*50)
    if success:
        print("✅✅✅  UPLOAD TEST PASSED! The entire flow is working correctly. ✅✅✅")
    else:
        print("❌❌❌  UPLOAD TEST FAILED. Please review the logs above for details. ❌❌❌")
    print("="*50)