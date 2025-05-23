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

    print("\n--- Test Finished ---")
