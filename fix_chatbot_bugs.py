#!/usr/bin/env python3
"""
Analyze and fix chatbot bugs from the conversation log
"""

import json

# The conversation log from user
conversation = [
    {"type":"bot","phase":"introduction","content":"Hi Michael Greenberg! I'm excited to help you create an amazing media kit and find perfect podcast opportunities for Michael Greenberg's First Campaign. \n\nThis conversation will take about 15-20 minutes. I'll be asking about your work, expertise, and what makes you a great podcast guest. \n\nFeel free to share as much detail as you'd like - the more I learn about you, the better I can help position you for success!\n\nReady to get started?","timestamp":"2025-07-03T19:29:57.303523"},
    {"type":"user","phase":"introduction","content":"Yes i am","timestamp":"2025-07-03T19:30:18.051460"},
    {"type":"bot","phase":"introduction","content":"Great! Do you have a LinkedIn profile? If yes, please share your LinkedIn URL - I can analyze it to learn more about your expertise and save us both time!","timestamp":"2025-07-03T19:31:29.487293"},
    {"type":"user","phase":"introduction","content":"http://linkedin.com/in/gentoftech/","timestamp":"2025-07-03T19:32:45.362892"},
    {"type":"bot","phase":"introduction","content":"Great! I've analyzed your LinkedIn profile and learned a lot about your expertise. This will help me ask more relevant questions and save us both time. Let me continue with a few specific questions based on what I found...","timestamp":"2025-07-03T19:32:59.008045"},
    {"type":"bot","phase":"core_discovery","content":"I see from your LinkedIn profile that you've had some impressive experiences. Can you share specific metrics or numbers from one of your biggest wins?","timestamp":"2025-07-03T19:32:59.009046"},
    {"type":"user","phase":"core_discovery","content":"One of my biggest achievements is co-founding a startup that raised $1.5M, and successfully exited to launch a podcast production agency","timestamp":"2025-07-03T19:37:22.505542"},
    {"type":"bot","phase":"core_discovery","content":"I see from your LinkedIn profile that you've had some impressive experiences. Can you share specific metrics or numbers from one of your biggest wins?","timestamp":"2025-07-03T19:37:24.469024"},
    {"type":"user","phase":"core_discovery","content":"Helping over 20 clients land an average of 5 podcast placements a month","timestamp":"2025-07-03T19:38:28.455836"},
    {"type":"bot","phase":"confirmation","content":"We're almost done! Is there anything specific you'd like to promote (book, course, service)?","timestamp":"2025-07-03T19:38:30.267444"},
    {"type":"user","phase":"confirmation","content":"None for now","timestamp":"2025-07-03T19:38:38.472211"},
    {"type":"bot","phase":"confirmation","content":"Perfect! I'll need your email address to include in the media kit. What's the best email for podcast hosts to reach you? Also, do you have a LinkedIn profile? If yes, please share your LinkedIn URL - I can analyze it to learn more about your expertise!","timestamp":"2025-07-03T19:38:40.039631"},
    {"type":"user","phase":"confirmation","content":"mgg@modernindustrialist.com","timestamp":"2025-07-03T19:38:55.670073"},
    {"type":"bot","phase":"confirmation","content":"We're almost done! Is there anything specific you'd like to promote (book, course, service)?","timestamp":"2025-07-03T19:38:57.463704"},
    {"type":"user","phase":"confirmation","content":"I wont be promoting anything for now","timestamp":"2025-07-03T19:39:09.110504"},
    {"type":"bot","phase":"confirmation","content":"We're almost done! Is there anything specific you'd like to promote (book, course, service)?","timestamp":"2025-07-03T19:39:10.728909"},
    {"type":"user","phase":"confirmation","content":"a book, but nothing for now","timestamp":"2025-07-03T19:39:26.961524"},
    {"type":"bot","phase":"confirmation","content":"We're almost done! Is there anything specific you'd like to promote (book, course, service)?","timestamp":"2025-07-03T19:39:28.819648"},
    {"type":"user","phase":"confirmation","content":"A book","timestamp":"2025-07-03T19:39:35.054000"},
    {"type":"bot","phase":"confirmation","content":"We're almost done! Is there anything specific you'd like to promote (book, course, service)?","timestamp":"2025-07-03T19:39:36.695341"}
]

print("CHATBOT CONVERSATION ANALYSIS")
print("=" * 80)

# Identify issues
issues = []

# Issue 1: Missing email request after "Yes I am"
if "email" not in conversation[2]["content"].lower():
    issues.append("Issue 1: Bot doesn't ask for email after 'Yes I am' (only asks for LinkedIn)")

# Issue 2: Duplicate messages
for i in range(len(conversation) - 1):
    for j in range(i + 1, len(conversation)):
        if (conversation[i]["type"] == "bot" and 
            conversation[j]["type"] == "bot" and 
            conversation[i]["content"] == conversation[j]["content"]):
            issues.append(f"Issue 2: Duplicate bot message at positions {i} and {j}")

# Issue 3: Loop in confirmation phase
promotion_count = sum(1 for msg in conversation if msg["type"] == "bot" and "Is there anything specific you'd like to promote" in msg["content"])
if promotion_count > 2:
    issues.append(f"Issue 3: Bot stuck in loop asking about promotions ({promotion_count} times)")

# Issue 4: LinkedIn asked again after already provided
linkedin_provided_at = None
for i, msg in enumerate(conversation):
    if msg["type"] == "user" and "linkedin.com" in msg["content"].lower():
        linkedin_provided_at = i
        break

if linkedin_provided_at:
    for i in range(linkedin_provided_at + 1, len(conversation)):
        if conversation[i]["type"] == "bot" and "LinkedIn profile" in conversation[i]["content"] and "do you have" in conversation[i]["content"].lower():
            issues.append(f"Issue 4: Bot asks for LinkedIn again at position {i} after it was provided at position {linkedin_provided_at}")

print("\nISSUES FOUND:")
for issue in issues:
    print(f"  - {issue}")

print("\n" + "=" * 80)
print("ROOT CAUSES:")
print("=" * 80)

print("""
1. MISSING EMAIL REQUEST:
   - The conversation starts with name already known (Michael Greenberg)
   - After "Yes I am", the bot should ask for email AND LinkedIn
   - Current: Only asks for LinkedIn
   - Fix: Check if name is already known and adjust opener accordingly

2. DUPLICATE MESSAGES:
   - The bot sends the same message twice after LinkedIn analysis
   - Likely due to double message append in conversation engine
   - Fix: Ensure messages aren't duplicated when transitioning phases

3. CONFIRMATION LOOP:
   - Bot gets stuck asking about promotions
   - User's responses aren't being properly processed
   - Fix: Improve NLP extraction for promotion preferences

4. LINKEDIN RE-ASKED:
   - Bot asks for LinkedIn in confirmation phase despite already having it
   - The email targeted question includes LinkedIn
   - Fix: Check if LinkedIn already provided before including in email question
""")