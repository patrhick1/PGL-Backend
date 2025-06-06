#!/usr/bin/env python3
"""
Test script for the questionnaire submission API endpoint.
"""

import requests
import json

def test_questionnaire_submission():
    # API endpoint
    url = 'http://localhost:8000/campaigns/cdc33aee-b0f8-4460-beec-cce66ea3772c/submit-questionnaire'
    
    # Headers with session cookie
    headers = {
        'Content-Type': 'application/json',
        'Cookie': 'session=eyJ1c2VybmFtZSI6ICJlYnViZTR1QGdtYWlsLmNvbSIsICJyb2xlIjogImNsaWVudCIsICJwZXJzb25faWQiOiA0MiwgImZ1bGxfbmFtZSI6ICJNYXJ5IFV3YSJ9.aD0HAA.Rd9zDy3GHWP-BiGRLTEIdCZck-o'
    }
    
    # Test data with the proper nested structure
    test_data = {
        "questionnaire_data": {
            "contactInfo": {
                "fullName": "Mary Uwa",
                "email": "mary.uwa@example.com",
                "phone": "555-123-4567",
                "website": "https://maryuwa.com",
                "socialMedia": [
                    { "platform": "LinkedIn", "handle": "https://www.linkedin.com/in/maryanne-onwunuma" }
                ]
            },
            "professionalBio": {
                "aboutWork": "Mary is a dynamic professional with a passion for Project Management, Event Planning, and Student Leadership. With a background built on [mention specific professional background details once known], Mary has consistently demonstrated the ability to drive successful projects, create memorable events, and empower students to reach their full potential. Her journey into these fields was sparked by [mention the story of how she got into the field once known], leading her to develop a unique perspective on the challenges and opportunities within each domain. Mary is committed to providing actionable advice and insights to those just starting out, helping them navigate the complexities of their chosen paths. She is available to share her expertise on a range of topics, from effective project management strategies to the importance of student engagement and leadership development.",
                "expertiseTopics": "Project Management, Event Planning, Student Leadership, Youth Empowerment, Campus Engagement Strategies",
                "achievements": "Successfully managed three large-scale university events with over 5000 attendees each. Secured $50k in sponsorship for student-led initiatives. Recognized as 'Student Leader of the Year' in 2021."
            },
            "atAGlanceStats": {
                "keynoteEngagements": "20+",
                "yearsOfExperience": "5+",
                "emailSubscribers": "1k+"
            },
            "mediaExperience": {
                "previousAppearances": [
                    { "showName": "The Student Success Podcast", "link": "https://example.com/podcast/student-success-ep10" },
                    { "showName": "Campus Life Today", "link": "https://example.com/show/campus-life-s2e5" }
                ],
                "speakingClips": [
                    { "title": "Keynote on Student Engagement", "link": "https://youtube.com/clip/student-engagement-keynote" },
                    { "title": "Webinar: Event Planning for Beginners", "link": "https://vimeo.com/clip/event-planning-webinar" }
                ]
            },
            "suggestedTopics": {
                "topics": "1. Strategies for Effective Student Project Management.\n2. Creating Impactful and Memorable Campus Events.\n3. Fostering Leadership Skills in Young Adults.\n4. The Role of Community in Student Development.\n5. Navigating Early Career Challenges in Event Coordination.",
                "keyStoriesOrMessages": "I often share a story about a challenging event that required quick problem-solving and teamwork, highlighting the importance of adaptability. A key message is always about empowering students to take initiative and find their voice."
            },
            "sampleQuestions": {
                "frequentlyAsked": "• What are the first steps to planning a successful campus event?\n• How do you motivate student volunteers?\n• What's the biggest challenge facing student leaders today?",
                "loveToBeAsked": "• How can universities better support student-led initiatives?\n• What's one unconventional approach to event planning that yields great results?\n• How has your own leadership journey shaped your advice to students?"
            },
            "socialProof": {
                "testimonials": "'Mary was an exceptional guest on our podcast. Her insights into student leadership were both practical and inspiring. Our listeners loved her energy and the actionable advice she shared.' - Host of 'Future Leaders Now' Podcast.",
                "notableStats": "• Increased student participation in campus activities by 30% during my tenure as Student Council President.\n• My workshops on project management have an average rating of 4.8/5 stars from over 200 participants."
            },
            "assets": {
                "headshotUrl": "https://example.com/path/to/mary-uwa-headshot.jpg",
                "logoUrl": "https://example.com/path/to/university-logo-if-relevant.png",
                "otherAssets": [
                    { "title": "My Recent Publication on Student Engagement", "url": "https://example.com/link/to/publication.pdf" },
                    { "title": "Award Certificate Scan", "url": "https://example.com/link/to/award.jpg" }
                ]
            },
            "promotionPrefs": {
                "preferredIntro": "Our next guest, Mary Uwa, is a passionate advocate for student leadership and an expert in project and event management. She's dedicated to helping young professionals create impactful experiences and build strong communities.",
                "itemsToPromote": "My upcoming workshop series on 'Event Management for Student Organizations'. Also, my LinkedIn newsletter where I share tips for young leaders.",
                "bestContactForHosts": "Please reach out via email at mary.booking@example.com or through my website\'s contact form."
            },
            "finalNotes": {
                "anythingElse": "I\'m particularly interested in podcasts that focus on empowering the next generation of leaders. I\'m also happy to provide a custom list of talking points tailored to your audience if needed.",
                "questionsOrConcerns": "Could you let me know the typical recording length and if video is preferred?"
            }
        }
    }
    
    print("🔄 Testing questionnaire submission API...")
    print(f"URL: {url}")
    print(f"Data: {json.dumps(test_data, indent=2)}")
    
    try:
        # Make the API request
        response = requests.post(url, headers=headers, json=test_data)
        
        print(f"\n📊 Response Status: {response.status_code}")
        print(f"📝 Response Headers: {dict(response.headers)}")
        print(f"💬 Response Text: {response.text}")
        
        if response.status_code == 200:
            print("✅ SUCCESS: Questionnaire submitted successfully!")
            try:
                response_json = response.json()
                print(f"📋 Response JSON: {json.dumps(response_json, indent=2)}")
            except:
                print("⚠️  Response is not valid JSON")
        else:
            print(f"❌ FAILED: API returned status {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ FAILED: Could not connect to the server. Is it running on localhost:8000?")
    except Exception as e:
        print(f"❌ FAILED: Unexpected error: {e}")

if __name__ == "__main__":
    test_questionnaire_submission() 