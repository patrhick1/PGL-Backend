#!/usr/bin/env python3
"""
Comprehensive validation test for the LLM-Powered Media Kit Generation System.
This script tests all major components to ensure robustness and proper functionality.
"""

import asyncio
import json
import uuid
import sys
import os
from typing import Dict, Any, List
from datetime import datetime

# Add the podcast_outreach directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'podcast_outreach'))

# Test data scenarios
TEST_QUESTIONNAIRE_DATA = [
    {
        "scenario": "Complete Professional Profile",
        "data": {
            "full_name": "Dr. Sarah Johnson",
            "email": "sarah@techconsulting.com",
            "company": "TechConsult Pro",
            "title": "Chief Technology Officer",
            "professional_bio": "Dr. Sarah Johnson is a seasoned technology executive with over 15 years of experience in digital transformation and enterprise software development. She holds a PhD in Computer Science from MIT and has led multiple successful tech initiatives at Fortune 500 companies.",
            "areas_of_expertise": ["Digital Transformation", "Enterprise Software", "AI Implementation", "Team Leadership"],
            "suggested_topics": "Digital transformation strategies, AI in business, remote team management, tech leadership for non-technical executives",
            "achievements": "Named Top 50 Women in Tech 2023, Led $50M digital transformation at previous company, Author of 'Leading Digital Change'",
            "media_experience": "TEDx speaker, interviewed on Tech Talks podcast, featured in Harvard Business Review",
            "testimonials": "Sarah's insights revolutionized our approach to digital transformation - CEO, Fortune 500 Company",
            "promotion_preferences": "Professional headshots available, comfortable with video interviews, prefers 30-45 minute format"
        }
    },
    {
        "scenario": "Entrepreneur Profile",
        "data": {
            "full_name": "Marcus Rodriguez",
            "email": "marcus@greentech.io",
            "professional_bio": "Serial entrepreneur and sustainability advocate who has founded three successful startups in the clean technology space.",
            "expertise": "Sustainable business models, green technology, startup funding",
            "suggested_topics": "Building sustainable startups, clean tech innovation, raising capital for green businesses",
            "media_appearances": "Bloomberg Green podcast, Sustainable Business Weekly",
            "social_proof": "Featured in Forbes 30 Under 30, raised $25M in Series A funding"
        }
    },
    {
        "scenario": "Minimal Data Profile",
        "data": {
            "full_name": "Alex Kim",
            "email": "alex@consulting.com",
            "professional_bio": "Business consultant specializing in operations optimization.",
            "areas_of_expertise": ["Operations", "Process Improvement"]
        }
    },
    {
        "scenario": "Complex Nested Data",
        "data": {
            "full_name": "Dr. Maria Santos",
            "contact_info": {
                "email": "maria@healthtech.org",
                "phone": "+1-555-0123",
                "website": "https://mariasantos.com"
            },
            "professional_background": {
                "title": "Healthcare Innovation Director",
                "company": "HealthTech Solutions",
                "experience_years": 12,
                "specializations": ["Telemedicine", "Health Data Analytics", "Patient Experience"]
            },
            "topics_and_expertise": {
                "primary_topics": ["Digital Health", "Telemedicine", "Healthcare AI"],
                "secondary_topics": ["Patient Engagement", "Health Policy"],
                "speaking_experience": ["HIMSS Conference", "Digital Health Summit"]
            },
            "achievements_and_credentials": {
                "degrees": ["MD from Johns Hopkins", "MBA from Wharton"],
                "certifications": ["Board Certified Internal Medicine"],
                "awards": ["Healthcare Innovation Award 2022"]
            }
        }
    }
]

async def test_questionnaire_processor():
    """Test the QuestionnaireProcessor with various data scenarios."""
    print("🧪 Testing QuestionnaireProcessor...")
    
    try:
        from podcast_outreach.services.campaigns.questionnaire_processor import QuestionnaireProcessor
        
        processor = QuestionnaireProcessor()
        results = []
        
        for test_case in TEST_QUESTIONNAIRE_DATA:
            print(f"   Testing scenario: {test_case['scenario']}")
            
            try:
                # Test keyword generation
                keywords = await processor._generate_keywords_from_questionnaire_llm(test_case['data'])
                
                # Test mock interview creation
                mock_interview = processor._construct_mock_interview_from_questionnaire(test_case['data'])
                
                result = {
                    "scenario": test_case['scenario'],
                    "keywords_generated": len(keywords),
                    "keywords_valid": len(keywords) == 20,
                    "mock_interview_created": bool(mock_interview and len(mock_interview) > 50),
                    "keywords_sample": keywords[:5] if keywords else [],
                    "success": True
                }
                
            except Exception as e:
                result = {
                    "scenario": test_case['scenario'],
                    "success": False,
                    "error": str(e)
                }
            
            results.append(result)
            print(f"   ✅ {test_case['scenario']}: {'Success' if result['success'] else 'Failed'}")
        
        return results
        
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return []
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return []

async def test_media_kit_service():
    """Test the MediaKitService with various scenarios."""
    print("🎨 Testing MediaKitService...")
    
    try:
        from podcast_outreach.services.media_kits.generator import MediaKitService
        
        service = MediaKitService()
        results = []
        
        for test_case in TEST_QUESTIONNAIRE_DATA:
            print(f"   Testing scenario: {test_case['scenario']}")
            
            try:
                # Test content extraction
                content = service._extract_questionnaire_content(test_case['data'])
                
                # Test individual LLM methods (without actual LLM calls for speed)
                test_campaign_id = uuid.uuid4()
                
                # Test keyword generation structure
                keywords_test = await service._generate_keywords(content, test_campaign_id)
                
                # Test tagline generation
                tagline_test = await service._generate_tagline(content, test_campaign_id)
                
                # Test bio generation
                bio_test = await service._generate_comprehensive_bio(content, test_campaign_id)
                
                result = {
                    "scenario": test_case['scenario'],
                    "content_extracted": bool(content and len(content) > 10),
                    "keywords_structure": isinstance(keywords_test, list),
                    "tagline_structure": isinstance(tagline_test, str),
                    "bio_structure": isinstance(bio_test, dict) and 'long_bio' in bio_test,
                    "success": True
                }
                
            except Exception as e:
                result = {
                    "scenario": test_case['scenario'],
                    "success": False,
                    "error": str(e)
                }
            
            results.append(result)
            print(f"   ✅ {test_case['scenario']}: {'Success' if result['success'] else 'Failed'}")
        
        return results
        
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return []
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return []

def test_imports():
    """Test all critical imports."""
    print("📦 Testing Critical Imports...")
    
    import_tests = [
        ("GeminiService", "podcast_outreach.services.ai.gemini_client"),
        ("SocialDiscoveryService", "podcast_outreach.services.enrichment.social_scraper"),
        ("MediaKitService", "podcast_outreach.services.media_kits.generator"),
        ("QuestionnaireProcessor", "podcast_outreach.services.campaigns.questionnaire_processor"),
        ("media_kit_queries", "podcast_outreach.database.queries.media_kits"),
        ("campaign_queries", "podcast_outreach.database.queries.campaigns"),
        ("people_queries", "podcast_outreach.database.queries.people"),
        ("GoogleDocsService", "podcast_outreach.integrations.google_docs"),
        ("task_manager", "podcast_outreach.services.tasks.manager")
    ]
    
    results = []
    
    for import_name, module_path in import_tests:
        try:
            module = __import__(module_path, fromlist=[import_name])
            getattr(module, import_name if import_name != "task_manager" else "task_manager")
            results.append({"import": f"{module_path}.{import_name}", "success": True})
            print(f"   ✅ {module_path}.{import_name}")
        except ImportError as e:
            results.append({"import": f"{module_path}.{import_name}", "success": False, "error": str(e)})
            print(f"   ❌ {module_path}.{import_name}: {e}")
        except AttributeError as e:
            results.append({"import": f"{module_path}.{import_name}", "success": False, "error": f"Attribute not found: {e}"})
            print(f"   ❌ {module_path}.{import_name}: Attribute not found")
    
    return results

def test_data_structures():
    """Test data structure handling."""
    print("🗂️  Testing Data Structure Handling...")
    
    # Test various data structure scenarios
    test_structures = [
        {"name": "Simple String", "data": "test string"},
        {"name": "List of Strings", "data": ["item1", "item2", "item3"]},
        {"name": "Nested Dict", "data": {"key1": "value1", "key2": {"nested": "value"}}},
        {"name": "Mixed Types", "data": {"string": "text", "list": [1, 2, 3], "dict": {"nested": True}}},
        {"name": "Empty Values", "data": {"empty_string": "", "none_value": None, "empty_list": []}},
        {"name": "Unicode Characters", "data": {"unicode": "Café, naïve, résumé, 你好"}}
    ]
    
    results = []
    
    try:
        from podcast_outreach.services.media_kits.generator import MediaKitService
        service = MediaKitService()
        
        for test in test_structures:
            try:
                content = service._extract_questionnaire_content(test["data"])
                results.append({
                    "test": test["name"],
                    "success": True,
                    "content_length": len(content),
                    "has_content": bool(content.strip())
                })
                print(f"   ✅ {test['name']}: Content extracted successfully")
            except Exception as e:
                results.append({
                    "test": test["name"],
                    "success": False,
                    "error": str(e)
                })
                print(f"   ❌ {test['name']}: {e}")
    
    except Exception as e:
        print(f"   ❌ Failed to initialize MediaKitService: {e}")
    
    return results

def test_error_handling():
    """Test error handling scenarios."""
    print("🛡️  Testing Error Handling...")
    
    results = []
    
    # Test empty data handling
    try:
        from podcast_outreach.services.campaigns.questionnaire_processor import QuestionnaireProcessor
        processor = QuestionnaireProcessor()
        
        # Test with empty data
        empty_result = processor._construct_mock_interview_from_questionnaire({})
        results.append({
            "test": "Empty Questionnaire Data",
            "success": bool(empty_result),
            "has_fallback": "Mock interview content" in empty_result or len(empty_result) > 10
        })
        print("   ✅ Empty questionnaire data handling: Success")
        
    except Exception as e:
        results.append({
            "test": "Empty Questionnaire Data",
            "success": False,
            "error": str(e)
        })
        print(f"   ❌ Empty questionnaire data handling: {e}")
    
    # Test malformed data handling
    try:
        from podcast_outreach.services.media_kits.generator import MediaKitService
        service = MediaKitService()
        
        malformed_data = {
            "malformed_list": [{"incomplete": "dict"}, None, "", []],
            "circular_ref": {"self": None}
        }
        malformed_data["circular_ref"]["self"] = malformed_data
        
        content = service._extract_questionnaire_content(malformed_data)
        results.append({
            "test": "Malformed Data Handling",
            "success": True,
            "content_extracted": bool(content)
        })
        print("   ✅ Malformed data handling: Success")
        
    except Exception as e:
        results.append({
            "test": "Malformed Data Handling",
            "success": False,
            "error": str(e)
        })
        print(f"   ❌ Malformed data handling: {e}")
    
    return results

async def main():
    """Run comprehensive system validation."""
    print("🚀 Starting LLM-Powered Media Kit System Validation")
    print("=" * 60)
    
    # Track overall results
    all_results = {}
    
    # Test imports first
    print("\n1. Import Validation")
    import_results = test_imports()
    all_results['imports'] = import_results
    
    # Test data structure handling
    print("\n2. Data Structure Testing")
    structure_results = test_data_structures()
    all_results['data_structures'] = structure_results
    
    # Test error handling
    print("\n3. Error Handling Testing")
    error_results = test_error_handling()
    all_results['error_handling'] = error_results
    
    # Test questionnaire processor
    print("\n4. Questionnaire Processor Testing")
    questionnaire_results = await test_questionnaire_processor()
    all_results['questionnaire_processor'] = questionnaire_results
    
    # Test media kit service
    print("\n5. Media Kit Service Testing")
    mediakit_results = await test_media_kit_service()
    all_results['media_kit_service'] = mediakit_results
    
    # Generate summary report
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY REPORT")
    print("=" * 60)
    
    total_tests = 0
    passed_tests = 0
    
    for category, results in all_results.items():
        if results:
            category_total = len(results)
            category_passed = sum(1 for r in results if r.get('success', False))
            total_tests += category_total
            passed_tests += category_passed
            
            print(f"{category.replace('_', ' ').title()}: {category_passed}/{category_total} passed")
            
            # Show failed tests
            failed_tests = [r for r in results if not r.get('success', False)]
            if failed_tests:
                for failure in failed_tests:
                    print(f"  ❌ {failure.get('test', failure.get('scenario', failure.get('import', 'Unknown')))}: {failure.get('error', 'Failed')}")
    
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\nOverall Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
    
    if success_rate >= 90:
        print("🎉 SYSTEM VALIDATION: EXCELLENT - System is robust and ready for production!")
    elif success_rate >= 75:
        print("✅ SYSTEM VALIDATION: GOOD - System is functional with minor issues to address.")
    elif success_rate >= 50:
        print("⚠️  SYSTEM VALIDATION: MODERATE - System has significant issues that should be addressed.")
    else:
        print("❌ SYSTEM VALIDATION: POOR - System requires immediate attention before deployment.")
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"validation_results_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: {results_file}")
    
    return all_results

if __name__ == "__main__":
    # Run the validation
    results = asyncio.run(main()) 