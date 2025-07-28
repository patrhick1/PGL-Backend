# podcast_outreach/services/chatbot/agentic/db_summary_builder.py

from typing import Dict, Any, List
import json

def build_complete_summary_from_db(extracted_data: Dict[str, Any]) -> str:
    """
    Build a complete summary from the extracted_data stored in the database
    
    Args:
        extracted_data: The extracted_data dictionary from the chatbot_conversations table
        
    Returns:
        Formatted summary string
    """
    summary_parts = []
    
    # CONTACT INFORMATION
    contact_info = []
    contact_fields = {
        'full_name': 'Full Name',
        'email': 'Email Address',
        'phone': 'Phone Number',
        'linkedin_url': 'LinkedIn Profile',
        'website': 'Website',
        'social_media': 'Social Media'
    }
    
    for field, label in contact_fields.items():
        if field in extracted_data and extracted_data[field]:
            value = extracted_data[field]
            if value != "none":
                contact_info.append(f"• {label}: {value}")
    
    if contact_info:
        summary_parts.append("CONTACT INFORMATION:")
        summary_parts.extend(contact_info)
        summary_parts.append("")  # Empty line
    
    # PROFESSIONAL BACKGROUND
    professional_info = []
    professional_fields = {
        'current_role': 'Current Role',
        'organization': 'Company/Organization',
        'company': 'Company/Organization',  # Alternative field name
        'years': 'Years of Experience',
        'years_experience': 'Years of Experience',  # Alternative field name
        'professional_bio': 'Professional Background'
    }
    
    for field, label in professional_fields.items():
        if field in extracted_data and extracted_data[field]:
            value = extracted_data[field]
            if value != "none":
                # Avoid duplicates
                if not any(label in item for item in professional_info):
                    professional_info.append(f"• {label}: {value}")
    
    if professional_info:
        summary_parts.append("PROFESSIONAL BACKGROUND:")
        summary_parts.extend(professional_info)
        summary_parts.append("")  # Empty line
    
    # EXPERTISE & ACCOMPLISHMENTS
    expertise_info = []
    
    # Expertise Keywords
    if 'expertise_keywords' in extracted_data and extracted_data['expertise_keywords']:
        if isinstance(extracted_data['expertise_keywords'], list):
            expertise_info.append(f"• Areas of Expertise: {', '.join(extracted_data['expertise_keywords'])}")
        else:
            expertise_info.append(f"• Areas of Expertise: {extracted_data['expertise_keywords']}")
    
    # Success Stories
    if 'success_stories' in extracted_data and extracted_data['success_stories']:
        if isinstance(extracted_data['success_stories'], list):
            stories = "\n  ".join([f"{i+1}. {story}" for i, story in enumerate(extracted_data['success_stories'])])
            expertise_info.append(f"• Success Stories:\n  {stories}")
        else:
            expertise_info.append(f"• Success Stories: {extracted_data['success_stories']}")
    
    # Achievements
    if 'achievements' in extracted_data and extracted_data['achievements']:
        if isinstance(extracted_data['achievements'], list):
            achievements = "\n  ".join([f"- {achievement}" for achievement in extracted_data['achievements']])
            expertise_info.append(f"• Key Achievements:\n  {achievements}")
        else:
            expertise_info.append(f"• Key Achievements: {extracted_data['achievements']}")
    
    # Unique Perspective
    if 'differentiator' in extracted_data and extracted_data['differentiator']:
        expertise_info.append(f"• Unique Perspective: {extracted_data['differentiator']}")
    elif 'unique_perspective' in extracted_data and extracted_data['unique_perspective']:
        expertise_info.append(f"• Unique Perspective: {extracted_data['unique_perspective']}")
    
    if expertise_info:
        summary_parts.append("EXPERTISE & ACCOMPLISHMENTS:")
        summary_parts.extend(expertise_info)
        summary_parts.append("")  # Empty line
    
    # PODCAST FOCUS
    podcast_info = []
    
    # Podcast Topics
    if 'podcast_topics' in extracted_data and extracted_data['podcast_topics']:
        if isinstance(extracted_data['podcast_topics'], list):
            topics = "\n  ".join([f"{i+1}. {topic}" for i, topic in enumerate(extracted_data['podcast_topics'])])
            podcast_info.append(f"• Podcast Topics:\n  {topics}")
        else:
            podcast_info.append(f"• Podcast Topics: {extracted_data['podcast_topics']}")
    
    # Target Audience
    if 'target_audience' in extracted_data and extracted_data['target_audience']:
        podcast_info.append(f"• Target Audience: {extracted_data['target_audience']}")
    
    # Key Message
    if 'key_message' in extracted_data and extracted_data['key_message']:
        podcast_info.append(f"• Key Message: {extracted_data['key_message']}")
    
    # Speaking Experience
    if 'speaking_experience' in extracted_data and extracted_data['speaking_experience']:
        if extracted_data['speaking_experience'] != "none":
            if isinstance(extracted_data['speaking_experience'], list):
                exp = "\n  ".join([f"- {item}" for item in extracted_data['speaking_experience']])
                podcast_info.append(f"• Speaking Experience:\n  {exp}")
            else:
                podcast_info.append(f"• Speaking Experience: {extracted_data['speaking_experience']}")
    
    if podcast_info:
        summary_parts.append("PODCAST FOCUS:")
        summary_parts.extend(podcast_info)
        summary_parts.append("")  # Empty line
    
    # ADDITIONAL INFORMATION
    additional_info = []
    
    # Scheduling Preference
    if 'scheduling_preference' in extracted_data and extracted_data['scheduling_preference']:
        additional_info.append(f"• Scheduling: {extracted_data['scheduling_preference']}")
    
    # Promotion Items
    if 'promotion_items' in extracted_data and extracted_data['promotion_items']:
        if extracted_data['promotion_items'] != "none":
            if isinstance(extracted_data['promotion_items'], list):
                items = "\n  ".join([f"- {item}" for item in extracted_data['promotion_items']])
                additional_info.append(f"• Items to Promote:\n  {items}")
            else:
                additional_info.append(f"• Items to Promote: {extracted_data['promotion_items']}")
    
    # Fun Facts / Additional Notes
    if 'fun_fact' in extracted_data and extracted_data['fun_fact']:
        additional_info.append(f"• Fun Fact: {extracted_data['fun_fact']}")
    
    if additional_info:
        summary_parts.append("ADDITIONAL INFORMATION:")
        summary_parts.extend(additional_info)
    
    # Remove any trailing empty lines
    while summary_parts and summary_parts[-1] == "":
        summary_parts.pop()
    
    return "\n".join(summary_parts)


def count_filled_fields(extracted_data: Dict[str, Any]) -> Dict[str, int]:
    """Count how many fields are filled in each category"""
    counts = {
        'contact': 0,
        'professional': 0,
        'expertise': 0,
        'podcast': 0,
        'additional': 0,
        'total': 0
    }
    
    # Contact fields
    contact_fields = ['full_name', 'email', 'phone', 'linkedin_url', 'website', 'social_media']
    for field in contact_fields:
        if field in extracted_data and extracted_data[field] and extracted_data[field] != "none":
            counts['contact'] += 1
    
    # Professional fields
    professional_fields = ['current_role', 'organization', 'company', 'years', 'years_experience', 'professional_bio']
    for field in professional_fields:
        if field in extracted_data and extracted_data[field] and extracted_data[field] != "none":
            counts['professional'] += 1
    
    # Expertise fields
    expertise_fields = ['expertise_keywords', 'success_stories', 'achievements', 'differentiator', 'unique_perspective']
    for field in expertise_fields:
        if field in extracted_data and extracted_data[field] and extracted_data[field] != "none":
            counts['expertise'] += 1
    
    # Podcast fields
    podcast_fields = ['podcast_topics', 'target_audience', 'key_message', 'speaking_experience']
    for field in podcast_fields:
        if field in extracted_data and extracted_data[field] and extracted_data[field] != "none":
            counts['podcast'] += 1
    
    # Additional fields
    additional_fields = ['scheduling_preference', 'promotion_items', 'fun_fact']
    for field in additional_fields:
        if field in extracted_data and extracted_data[field] and extracted_data[field] != "none":
            counts['additional'] += 1
    
    counts['total'] = sum([counts['contact'], counts['professional'], counts['expertise'], 
                          counts['podcast'], counts['additional']])
    
    return counts


# Example usage with the data you provided
if __name__ == "__main__":
    # Sample extracted data from the database
    sample_data = {
        "email": "marytilda20@gmail.com",
        "years": "4",
        "website": "https://www.podcastguestlaunch.com/",
        "full_name": "Maryanne Onwunuma",
        "achievements": [
            "Lowered event expenses by 15% through vendor negotiation",
            "Increased event attendance by 20% through student mentorship",
            "Received national recognition for cultural programs",
            "Managed event budgets up to $50,000"
        ],
        "current_role": "Graduate Assistant for the Union Activities Council (UAC)",
        "linkedin_url": "https://www.linkedin.com/in/maryanne-onwunuma",
        "organization": "Emporia State University",
        "differentiator": "Combining practical event management experience with MBA studies, offering a data-driven and strategic approach to event planning and community engagement.",
        "podcast_topics": [
            "Effective Event Budgeting",
            "Maximizing Student Engagement in Events",
            "Negotiating Vendor Contracts for Events",
            "Building Community Partnerships Through Events",
            "The Role of Cultural Events in Promoting Diversity"
        ],
        "success_stories": "I am most proud of my role in empowering student engagement and building a strong community on campus. Through effective administrative support and leadership in event management, I have helped create meaningful experiences for students and ensured successful execution of campus activities, all while maintaining careful budget oversight. Attending and learning from my first National Association for Campus Activities (NACA) Conference was a turning point that inspired me to bring new ideas back to my university, enhancing student involvement and inclusion. Seeing the positive impact these efforts have had on my peers and the university community gives me immense pride.",
        "target_audience": "Event planners, student affairs professionals, non-profit organizations, community engagement specialists, and anyone interested in event budgeting and student involvement.",
        "professional_bio": "A passionate event coordinator and administrative professional, currently pursuing an MBA, excels in community engagement and organizational success. With a proven track record in event management and budget oversight, they bring a unique perspective on streamlining operations and fostering stakeholder relations.",
        "expertise_keywords": [
            "Event Management",
            "Budget Oversight",
            "Administrative Coordination",
            "Vendor Negotiation",
            "Student Engagement",
            "Community Engagement",
            "Strategic Planning",
            "Process Improvement"
        ],
        "speaking_experience": "none"
    }
    
    # Build summary
    summary = build_complete_summary_from_db(sample_data)
    print(summary)
    print("\n" + "="*50 + "\n")
    
    # Count fields
    counts = count_filled_fields(sample_data)
    print(f"Field counts: {counts}")
    print(f"Total fields filled: {counts['total']}")