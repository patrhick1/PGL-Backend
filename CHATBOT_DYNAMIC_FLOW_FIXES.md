# Chatbot Dynamic Flow Fixes

## Overview
Fixed the chatbot to use dynamic, data-driven question selection instead of static, index-based flow. This prevents duplicate questions and improves conversation quality.

## Problems Identified

### 1. Static Question Flow
- Questions were selected based on message count in phase
- No checking if data already exists before asking
- Led to duplicate questions (e.g., asking for metrics twice)

### 2. Poor State Tracking
- No memory of which questions were already asked
- No tracking of what data was extracted from responses
- Confirmation phase showed summary multiple times

### 3. LinkedIn Integration Issues
- Special LinkedIn questions didn't coordinate with regular flow
- Metrics question asked even when LinkedIn provided the data

### 4. Confirmation Phase Loop
- Summary shown multiple times
- Same questions repeated
- No tracking of user responses to "Let's leave it at this"

## Solutions Implemented

### 1. Conversation State Management
Added state tracking per conversation:
```python
self.conversation_states[conversation_id] = {
    "asked_questions": set(),      # Track asked questions
    "asked_topics": set(),          # Track topics covered
    "phase_states": {               # Track phase-specific state
        "confirmation": {
            "summary_shown": False,
            "questions_asked": 0
        }
    }
}
```

### 2. Data Existence Checking
Created `_check_if_data_exists()` method to detect:
- Metrics in stories (looks for numbers, $, %)
- Email in contact info
- Promotion preferences in responses
- Contact preferences (calendly links, etc.)

### 3. Smart Question Generation
Updated `_get_smart_question()` to:
- Check if data already exists before asking
- Track which questions have been asked
- Show confirmation summary only once
- Properly sequence confirmation questions

### 4. Dynamic Flow Management
Modified flow manager to:
- Adjust core_discovery opener if metrics already exist
- Skip questions for data obtained from LinkedIn
- Prevent question repetition

### 5. Response Tracking
Added recent response storage:
```python
extracted_data['recent_responses'] = []  # Last 5 user messages
```
This helps detect answers like "Let's leave it at this" or "None for now"

## Example Flow After Fixes

### Before:
```
BOT: Share metrics from your biggest win?
USER: Raised $1.5M and exited
BOT: Share metrics from your biggest win?  [DUPLICATE]
USER: ...
BOT: Summary of what we learned...
USER: That's all
BOT: Summary of what we learned...  [DUPLICATE]
```

### After:
```
BOT: Share metrics from your biggest win?
USER: Raised $1.5M and exited
BOT: Based on your impressive achievements, what are your top areas of expertise?
USER: ...
BOT: Summary of what we learned...
USER: That's all
BOT: Is there anything you'd like to promote?
USER: None for now
BOT: What's the best way for hosts to contact you?
USER: calendly.com/mylink
BOT: Excellent! I have everything needed...
```

## Key Methods Added/Modified

### 1. `_get_conversation_state(conversation_id)`
Gets or creates conversation-specific state

### 2. `_has_asked_about(conversation_id, topic)`
Checks if a topic was already covered

### 3. `_mark_question_asked(conversation_id, question, topic)`
Records that a question/topic was asked

### 4. `_check_if_data_exists(extracted_data, data_type)`
Intelligently checks if data already exists

### 5. Updated `_get_smart_question()`
Now includes conversation_id and uses state tracking

## Testing
Run test script to verify fixes:
```bash
pgl_env/Scripts/python.exe test_chatbot_state_fixes.py
```

## Benefits
1. **No Duplicate Questions** - Each question asked only once
2. **Intelligent Flow** - Adapts based on what data exists
3. **Better UX** - No repetitive loops or redundant questions
4. **LinkedIn Aware** - Properly skips questions answered by LinkedIn
5. **State Persistence** - Remembers conversation context

## Next Steps
1. Add database persistence for conversation states
2. Implement more sophisticated answer detection
3. Add analytics to track question effectiveness
4. Consider ML-based question selection