import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Base directory for all AI prompts
PROMPTS_BASE_DIR = os.path.join(os.path.dirname(__file__), 'prompts')

def load_pitch_template(template_name: str) -> Optional[str]:
    """
    Loads a pitch template from the file system.

    Args:
        template_name: The name of the template file (e.g., 'friendly_intro_template').
                       Assumes it's located in services/ai/prompts/pitch/.

    Returns:
        The content of the template file as a string, or None if not found.
    """
    file_path = os.path.join(PROMPTS_BASE_DIR, 'pitch', f'{template_name}.txt')
    
    if not os.path.exists(file_path):
        logger.warning(f"Pitch template file not found: {file_path}")
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.debug(f"Successfully loaded pitch template: {template_name}")
        return content
    except Exception as e:
        logger.error(f"Error reading pitch template file {file_path}: {e}", exc_info=True)
        return None

def load_prompt_template(template_path_and_name: str) -> Optional[str]:
    """
    Loads a prompt template from the file system from a specified subfolder.

    Args:
        template_path_and_name: The path relative to PROMPTS_BASE_DIR and name of the template file 
                                (e.g., 'media_kit/parse_bio_prompt').
                                It will append '.txt' to this name.

    Returns:
        The content of the template file as a string, or None if not found.
    """
    # Construct the full file path
    # template_path_and_name could be "subdir/filename" or just "filename"
    file_path = os.path.join(PROMPTS_BASE_DIR, f'{template_path_and_name}.txt')
    
    if not os.path.exists(file_path):
        logger.warning(f"Prompt template file not found: {file_path}")
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.debug(f"Successfully loaded prompt template: {template_path_and_name}")
        return content
    except Exception as e:
        logger.error(f"Error reading prompt template file {file_path}: {e}", exc_info=True)
        return None

# Example usage (for testing this module directly)
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    print("--- Testing Pitch Template Loader ---")

    template_content = load_pitch_template("friendly_intro_template")
    if template_content:
        print("\n'friendly_intro_template.txt' loaded successfully (first 200 chars):")
        print(template_content[:200] + "...")
    else:
        print("\nFailed to load 'friendly_intro_template.txt'.")

    template_content = load_pitch_template("non_existent_template")
    if template_content:
        print("\n'non_existent_template.txt' loaded successfully (THIS SHOULD NOT HAPPEN).")
    else:
        print("\n'non_existent_template.txt' not found as expected.")

    print("\n--- Testing Generic Prompt Template Loader ---")
    # Create dummy files for testing if they don't exist
    media_kit_prompt_dir = os.path.join(PROMPTS_BASE_DIR, 'media_kit')
    if not os.path.exists(media_kit_prompt_dir):
        os.makedirs(media_kit_prompt_dir)
    
    dummy_bio_path = os.path.join(media_kit_prompt_dir, 'parse_bio_prompt.txt')
    if not os.path.exists(dummy_bio_path):
        with open(dummy_bio_path, 'w') as f:
            f.write("This is a dummy bio prompt for {{user_query}} and {format_instructions}.")

    bio_prompt_content = load_prompt_template("media_kit/parse_bio_prompt")
    if bio_prompt_content:
        print(f"\n'media_kit/parse_bio_prompt.txt' loaded: {bio_prompt_content[:50]}...")
    else:
        print("\nFailed to load 'media_kit/parse_bio_prompt.txt'.")

    non_existent_content = load_prompt_template("non_existent_subdir/non_existent_prompt")
    if non_existent_content:
        print("\nLoaded a non-existent prompt (THIS SHOULD NOT HAPPEN).")
    else:
        print("\nNon-existent prompt not found as expected.")

    # Consider refactoring load_pitch_template to use load_prompt_template:
    # def load_pitch_template(template_name: str) -> Optional[str]:
    #     return load_prompt_template(f"pitch/{template_name}")

    print("\n--- Test Finished ---")
