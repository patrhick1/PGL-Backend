#!/usr/bin/env python3
"""Monitor chatbot logs for errors and debug information"""

import re
import sys
from datetime import datetime, timedelta

def analyze_chatbot_logs(log_file_path=None):
    """Analyze recent chatbot-related log entries"""
    
    if not log_file_path:
        # Try to find the most recent log file
        log_file_path = "app.log"  # Adjust based on your logging configuration
    
    print(f"Analyzing chatbot logs from: {log_file_path}")
    print("=" * 80)
    
    # Patterns to look for
    patterns = {
        "validation_error": r"Validation error in extraction",
        "llm_error": r"Error in LLM extraction",
        "parse_error": r"Failed to parse LLM response",
        "chatbot_request": r"chatbot_nlp_extraction.*Tokens",
        "conversation_phase": r"conversation_phase",
        "message_count": r"Messages exchanged: (\d+)"
    }
    
    stats = {
        "total_errors": 0,
        "validation_errors": 0,
        "llm_errors": 0,
        "successful_extractions": 0,
        "phase_transitions": [],
        "message_counts": []
    }
    
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # Process last 1000 lines
        recent_lines = lines[-1000:] if len(lines) > 1000 else lines
        
        for line in recent_lines:
            # Check for validation errors
            if patterns["validation_error"] in line:
                stats["validation_errors"] += 1
                stats["total_errors"] += 1
                print(f"\nValidation Error Found:")
                print(f"  {line.strip()}")
                
                # Try to find the response that caused the error
                for i, prev_line in enumerate(recent_lines):
                    if "Response was:" in prev_line and recent_lines.index(line) - i < 5:
                        print(f"  Response: {prev_line.strip()}")
                        break
            
            # Check for LLM errors
            elif patterns["llm_error"] in line:
                stats["llm_errors"] += 1
                stats["total_errors"] += 1
                print(f"\nLLM Error Found:")
                print(f"  {line.strip()}")
            
            # Check for successful extractions
            elif patterns["chatbot_request"] in line:
                stats["successful_extractions"] += 1
                
            # Extract message counts
            message_match = re.search(patterns["message_count"], line)
            if message_match:
                count = int(message_match.group(1))
                stats["message_counts"].append(count)
        
        # Print summary
        print("\n" + "=" * 80)
        print("SUMMARY:")
        print(f"  Total Errors: {stats['total_errors']}")
        print(f"  - Validation Errors: {stats['validation_errors']}")
        print(f"  - LLM Errors: {stats['llm_errors']}")
        print(f"  Successful Extractions: {stats['successful_extractions']}")
        
        if stats["message_counts"]:
            avg_messages = sum(stats["message_counts"]) / len(stats["message_counts"])
            print(f"  Average Message Count: {avg_messages:.1f}")
            print(f"  Max Messages: {max(stats['message_counts'])}")
        
        # Recommendations
        print("\nRECOMMENDATIONS:")
        if stats["validation_errors"] > 0:
            print("  - The LLM is returning improperly formatted JSON")
            print("  - Check that the prompt explicitly requests valid JSON")
            print("  - Consider adding more robust parsing fallbacks")
        
        if stats["llm_errors"] > 0:
            print("  - There are issues with the LLM API calls")
            print("  - Check API key and rate limits")
            print("  - Verify the Gemini service is properly configured")
            
    except FileNotFoundError:
        print(f"Error: Log file not found at {log_file_path}")
        print("Please specify the correct path to your log file")
    except Exception as e:
        print(f"Error analyzing logs: {e}")

if __name__ == "__main__":
    # You can pass a log file path as an argument
    log_path = sys.argv[1] if len(sys.argv) > 1 else None
    analyze_chatbot_logs(log_path)