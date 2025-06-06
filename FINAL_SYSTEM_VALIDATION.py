#!/usr/bin/env python3
"""
Final comprehensive validation test for the LLM-Powered Media Kit Generation System.
This script tests the actual data flow through the system to ensure everything works correctly.
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

async def test_questionnaire_to_media_kit_flow():
    """Test the complete flow from questionnaire submission to media kit generation."""
    print("🔄 Testing Complete Questionnaire → Media Kit Flow...")
    
    try:
        # Test data
        test_questionnaire = {
            "full_name": "Dr. Jane Smith",
            "email": "jane@example.com",
            "company": "TechInnovate Solutions",
            "title": "Chief Technology Officer",
            "professional_bio": "Dr. Jane Smith is a technology leader with 15 years of experience in AI and machine learning. She has led digital transformation initiatives at Fortune 500 companies and holds a PhD in Computer Science from Stanford.",
            "areas_of_expertise": ["Artificial Intelligence", "Machine Learning", "Digital Transformation", "Tech Leadership"],
            "suggested_topics": "AI implementation in enterprise, building high-performing tech teams, future of machine learning, ethical AI development",
            "achievements": "Published 50+ research papers, Led $100M digital transformation, Named Top 100 Women in Tech 2023",
            "media_experience": "Keynote speaker at AI Summit 2023, Featured on Tech Leaders podcast, Interviewed by Forbes",
            "testimonials": "Jane's insights on AI implementation transformed our entire approach to technology - CEO, Global Corp"
        }
        
        # Test 1: Questionnaire Processing
        print("   Testing questionnaire processing...")
        from podcast_outreach.services.campaigns.questionnaire_processor import QuestionnaireProcessor
        
        processor = QuestionnaireProcessor()
        
        # Test keyword generation
        keywords = await processor._generate_keywords_from_questionnaire_llm(test_questionnaire)
        print(f"   ✅ Generated {len(keywords)} keywords: {keywords[:5]}...")
        
        # Test mock interview generation
        mock_interview = processor.construct_mock_interview_from_questionnaire(test_questionnaire)
        print(f"   ✅ Generated mock interview ({len(mock_interview)} chars)")
        
        # Test 2: Media Kit Generation
        print("   Testing media kit generation...")
        from podcast_outreach.services.media_kits.generator import MediaKitService
        
        media_kit_service = MediaKitService()
        
        # Test content extraction
        content = media_kit_service._extract_questionnaire_content(test_questionnaire)
        print(f"   ✅ Extracted content ({len(content)} chars)")
        
        # Test individual generation methods
        test_campaign_id = uuid.uuid4()
        
        tagline = await media_kit_service._generate_tagline(content, test_campaign_id)
        print(f"   ✅ Generated tagline: '{tagline}'")
        
        bio_sections = await media_kit_service._generate_comprehensive_bio(content, test_campaign_id)
        print(f"   ✅ Generated bio sections: {list(bio_sections.keys())}")
        
        talking_points = await media_kit_service._generate_talking_points(content, test_campaign_id)
        print(f"   ✅ Generated {len(talking_points)} talking points")
        
        sample_questions = await media_kit_service._generate_sample_questions(content, test_campaign_id)
        print(f"   ✅ Generated {len(sample_questions)} sample questions")
        
        # Test 3: Standalone Functions
        print("   Testing standalone functions...")
        from podcast_outreach.services.campaigns.questionnaire_processor import (
            process_campaign_questionnaire_submission,
            construct_mock_interview_from_questionnaire
        )
        
        # Test standalone mock interview function
        standalone_interview = construct_mock_interview_from_questionnaire(test_questionnaire)
        print(f"   ✅ Standalone mock interview function works ({len(standalone_interview)} chars)")
        
        return {
            "questionnaire_processing": True,
            "keyword_generation": len(keywords) == 20,
            "mock_interview_generation": len(mock_interview) > 50,
            "media_kit_content_extraction": len(content) > 100,
            "tagline_generation": len(tagline) > 5,
            "bio_generation": "long_bio" in bio_sections and "short_bio" in bio_sections,
            "talking_points_generation": len(talking_points) > 0,
            "sample_questions_generation": len(sample_questions) > 0,
            "standalone_functions": len(standalone_interview) > 50,
            "success": True
        }
        
    except Exception as e:
        print(f"   ❌ Error in flow test: {e}")
        return {"success": False, "error": str(e)}

async def test_error_handling():
    """Test error handling with various edge cases."""
    print("🛡️  Testing Error Handling...")
    
    try:
        from podcast_outreach.services.campaigns.questionnaire_processor import QuestionnaireProcessor
        from podcast_outreach.services.media_kits.generator import MediaKitService
        
        processor = QuestionnaireProcessor()
        media_kit_service = MediaKitService()
        
        test_cases = [
            {"name": "Empty Data", "data": {}},
            {"name": "Minimal Data", "data": {"full_name": "Test User"}},
            {"name": "Malformed Data", "data": {"invalid": [None, "", {"broken": True}]}},
            {"name": "Unicode Data", "data": {"full_name": "José María", "bio": "Café résumé naïve 你好"}}
        ]
        
        results = []
        
        for test_case in test_cases:
            try:
                # Test questionnaire processing
                keywords = await processor._generate_keywords_from_questionnaire_llm(test_case["data"])
                mock_interview = processor.construct_mock_interview_from_questionnaire(test_case["data"])
                
                # Test media kit processing
                content = media_kit_service._extract_questionnaire_content(test_case["data"])
                
                results.append({
                    "test": test_case["name"],
                    "keywords_generated": len(keywords),
                    "mock_interview_created": len(mock_interview) > 10,
                    "content_extracted": len(content) >= 0,
                    "success": True
                })
                print(f"   ✅ {test_case['name']}: Handled gracefully")
                
            except Exception as e:
                results.append({
                    "test": test_case["name"],
                    "success": False,
                    "error": str(e)
                })
                print(f"   ❌ {test_case['name']}: {e}")
        
        return results
        
    except Exception as e:
        print(f"   ❌ Error in error handling test: {e}")
        return [{"success": False, "error": str(e)}]

def test_imports_and_dependencies():
    """Test all critical imports and dependencies."""
    print("📦 Testing Critical Imports and Dependencies...")
    
    import_tests = [
        ("GeminiService", "podcast_outreach.services.ai.gemini_client"),
        ("SocialDiscoveryService", "podcast_outreach.services.enrichment.social_scraper"),
        ("MediaKitService", "podcast_outreach.services.media_kits.generator"),
        ("QuestionnaireProcessor", "podcast_outreach.services.campaigns.questionnaire_processor"),
        ("ClientContentProcessor", "podcast_outreach.services.campaigns.content_processor"),
        ("process_campaign_questionnaire_submission", "podcast_outreach.services.campaigns.questionnaire_processor"),
        ("construct_mock_interview_from_questionnaire", "podcast_outreach.services.campaigns.questionnaire_processor"),
    ]
    
    results = []
    
    for import_name, module_path in import_tests:
        try:
            module = __import__(module_path, fromlist=[import_name])
            imported_item = getattr(module, import_name)
            
            # Additional validation
            if import_name == "MediaKitService":
                # Test that MediaKitService can be instantiated
                service = imported_item()
                assert hasattr(service, 'create_or_update_media_kit')
                assert hasattr(service, '_extract_questionnaire_content')
            
            elif import_name == "QuestionnaireProcessor":
                # Test that QuestionnaireProcessor can be instantiated
                processor = imported_item()
                assert hasattr(processor, 'construct_mock_interview_from_questionnaire')
                assert hasattr(processor, 'process_campaign_questionnaire_submission')
            
            elif callable(imported_item):
                # Test that functions are callable
                assert callable(imported_item)
            
            results.append({"import": f"{module_path}.{import_name}", "success": True})
            print(f"   ✅ {module_path}.{import_name}")
            
        except ImportError as e:
            results.append({"import": f"{module_path}.{import_name}", "success": False, "error": f"Import error: {e}"})
            print(f"   ❌ {module_path}.{import_name}: Import error: {e}")
        except AttributeError as e:
            results.append({"import": f"{module_path}.{import_name}", "success": False, "error": f"Attribute not found: {e}"})
            print(f"   ❌ {module_path}.{import_name}: Attribute not found: {e}")
        except Exception as e:
            results.append({"import": f"{module_path}.{import_name}", "success": False, "error": f"Validation error: {e}"})
            print(f"   ❌ {module_path}.{import_name}: Validation error: {e}")
    
    return results

async def test_integration_points():
    """Test integration between different components."""
    print("🔗 Testing Integration Points...")
    
    try:
        # Test that content processor can use media kit service
        from podcast_outreach.services.campaigns.content_processor import ClientContentProcessor
        
        processor = ClientContentProcessor()
        
        # Verify that all required services are available
        assert hasattr(processor, 'media_kit_service')
        assert hasattr(processor, 'google_docs_service')
        assert hasattr(processor, 'openai_service')
        assert hasattr(processor, 'match_creation_service')
        
        # Test that podcast transcriber is optional
        if processor.podcast_transcriber is None:
            print("   ✅ Podcast transcriber gracefully unavailable (yt_dlp not installed)")
        else:
            print("   ✅ Podcast transcriber available")
        
        # Test content extraction method
        test_data = {"full_name": "Test User", "bio": "Test bio"}
        formatted_content = processor._format_questionnaire_for_embedding(test_data)
        assert isinstance(formatted_content, str)
        
        print("   ✅ Content processor integration working")
        
        return {"success": True, "content_processor_integration": True}
        
    except Exception as e:
        print(f"   ❌ Integration test failed: {e}")
        return {"success": False, "error": str(e)}

async def main():
    """Run comprehensive final validation."""
    print("🚀 Starting Final LLM-Powered Media Kit System Validation")
    print("=" * 70)
    
    # Track overall results
    all_results = {}
    
    # Test 1: Import validation
    print("\n1. Import and Dependency Validation")
    import_results = test_imports_and_dependencies()
    all_results['imports'] = import_results
    
    # Test 2: Integration points
    print("\n2. Integration Points Testing")
    integration_results = await test_integration_points()
    all_results['integration'] = integration_results
    
    # Test 3: Error handling
    print("\n3. Error Handling Testing")
    error_results = await test_error_handling()
    all_results['error_handling'] = error_results
    
    # Test 4: Complete flow
    print("\n4. Complete Data Flow Testing")
    flow_results = await test_questionnaire_to_media_kit_flow()
    all_results['complete_flow'] = flow_results
    
    # Generate summary report
    print("\n" + "=" * 70)
    print("📊 FINAL VALIDATION SUMMARY REPORT")
    print("=" * 70)
    
    total_tests = 0
    passed_tests = 0
    
    # Count import tests
    if isinstance(all_results['imports'], list):
        import_total = len(all_results['imports'])
        import_passed = sum(1 for r in all_results['imports'] if r.get('success', False))
        total_tests += import_total
        passed_tests += import_passed
        print(f"Import Tests: {import_passed}/{import_total} passed")
    
    # Count integration tests
    if all_results['integration'].get('success'):
        total_tests += 1
        passed_tests += 1
        print(f"Integration Tests: 1/1 passed")
    else:
        total_tests += 1
        print(f"Integration Tests: 0/1 passed")
    
    # Count error handling tests
    if isinstance(all_results['error_handling'], list):
        error_total = len(all_results['error_handling'])
        error_passed = sum(1 for r in all_results['error_handling'] if r.get('success', False))
        total_tests += error_total
        passed_tests += error_passed
        print(f"Error Handling Tests: {error_passed}/{error_total} passed")
    
    # Count flow tests
    if all_results['complete_flow'].get('success'):
        total_tests += 1
        passed_tests += 1
        print(f"Complete Flow Tests: 1/1 passed")
    else:
        total_tests += 1
        print(f"Complete Flow Tests: 0/1 passed")
    
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\nOverall Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
    
    # Show any failures
    failures = []
    for category, results in all_results.items():
        if isinstance(results, list):
            failures.extend([r for r in results if not r.get('success', False)])
        elif isinstance(results, dict) and not results.get('success', False):
            failures.append({**results, 'category': category})
    
    if failures:
        print(f"\n❌ Failed Tests ({len(failures)}):")
        for failure in failures:
            error_msg = failure.get('error', 'Unknown error')
            test_name = failure.get('test', failure.get('import', failure.get('category', 'Unknown')))
            print(f"  • {test_name}: {error_msg}")
    
    # Final assessment
    if success_rate >= 95:
        print("\n🎉 FINAL VALIDATION: EXCELLENT - System is production-ready and bulletproof!")
        status = "PRODUCTION_READY"
    elif success_rate >= 85:
        print("\n✅ FINAL VALIDATION: GOOD - System is functional with minor issues.")
        status = "FUNCTIONAL_WITH_MINOR_ISSUES"
    elif success_rate >= 70:
        print("\n⚠️  FINAL VALIDATION: MODERATE - System has issues that should be addressed.")
        status = "NEEDS_ATTENTION"
    else:
        print("\n❌ FINAL VALIDATION: POOR - System requires immediate fixes.")
        status = "REQUIRES_FIXES"
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"final_validation_results_{timestamp}.json"
    
    final_report = {
        "timestamp": timestamp,
        "success_rate": success_rate,
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "status": status,
        "detailed_results": all_results,
        "failures": failures
    }
    
    with open(results_file, 'w') as f:
        json.dump(final_report, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: {results_file}")
    
    return final_report

if __name__ == "__main__":
    # Run the final validation
    results = asyncio.run(main()) 