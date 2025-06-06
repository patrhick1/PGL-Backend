# podcast_outreach/services/matches/vetting_agent.py
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries

logger = logging.getLogger(__name__)

# --- Pydantic Models for Structured LLM Output ---

class VettingCriterion(BaseModel):
    criterion: str = Field(description="A specific criterion for evaluating the podcast's fit.")
    reasoning: str = Field(description="Why this criterion is important based on the client's goals.")
    weight: int = Field(description="The importance of this criterion on a scale of 1 to 5.", ge=1, le=5)

class VettingChecklist(BaseModel):
    checklist: List[VettingCriterion] = Field(description="A list of vetting criteria.")

class CriterionScore(BaseModel):
    criterion: str = Field(description="The specific criterion being scored.")
    score: int = Field(description="The score from 0 to 10 for this criterion.", ge=0, le=10)
    justification: str = Field(description="The justification for the score, citing specific evidence from the podcast data.")

class VettingAnalysis(BaseModel):
    scores: List[CriterionScore] = Field(description="A list of scores for each criterion.")
    final_summary: str = Field(description="A final summary of the podcast's fit, explaining the overall score.")

# --- Vetting Agent Service ---

class VettingAgent:
    """An intelligent agent to vet podcast opportunities against a client's ideal profile."""

    def __init__(self):
        self.gemini_service = GeminiService()
        logger.info("VettingAgent initialized.")

    async def _generate_vetting_checklist(self, ideal_podcast_description: str) -> Optional[VettingChecklist]:
        """Uses an LLM to create a dynamic checklist from the client's description."""
        prompt = f"""
        Based on the following description of an ideal podcast provided by a client, create a prioritized checklist of 5-7 specific, measurable criteria to evaluate potential podcasts. For each criterion, provide a brief reasoning and a weight from 1 (least important) to 5 (most important).

        Client's Ideal Podcast Description:
        "{ideal_podcast_description}"

        Generate a JSON object that adheres to the following schema.
        """
        try:
            checklist_obj = await self.gemini_service.get_structured_data(
                prompt_template_str=prompt,
                user_query="", # Not needed as prompt is self-contained
                output_model=VettingChecklist,
                workflow="vetting_checklist_generation"
            )
            return checklist_obj
        except Exception as e:
            logger.error(f"Failed to generate vetting checklist: {e}", exc_info=True)
            return None

    async def _gather_podcast_evidence(self, media_id: int) -> str:
        """Gathers all available enriched data for a podcast to be used as evidence."""
        media_record = await media_queries.get_media_by_id_from_db(media_id)
        if not media_record:
            return "No media data available."

        episodes = await episode_queries.get_episodes_for_media_with_content(media_id)
        
        evidence_parts = [
            f"Podcast Name: {media_record.get('name')}",
            f"Description: {media_record.get('description')}",
            f"AI Description: {media_record.get('ai_description')}",
            f"Category: {media_record.get('category')}",
            f"Host(s): {', '.join(media_record.get('host_names', []))}",
            f"Audience Size Estimate: {media_record.get('audience_size')}",
            f"ListenNotes Score: {media_record.get('listen_score')}",
            f"Social Followers (Twitter): {media_record.get('twitter_followers')}",
            f"Quality Score: {media_record.get('quality_score')}"
        ]

        if episodes:
            evidence_parts.append("\nRecent Episode Analysis:")
            for ep in episodes[:3]: # Use top 3 recent episodes
                evidence_parts.append(f"- Title: {ep.get('title')}")
                evidence_parts.append(f"  Summary: {ep.get('ai_episode_summary') or ep.get('episode_summary')}")
                evidence_parts.append(f"  Themes: {', '.join(ep.get('episode_themes', []))}")
                evidence_parts.append(f"  Keywords: {', '.join(ep.get('episode_keywords', []))}")

        return "\n".join(filter(None, evidence_parts))

    async def _score_podcast_against_checklist(self, checklist: VettingChecklist, evidence: str) -> Optional[VettingAnalysis]:
        """Uses an LLM to score a podcast against the generated checklist."""
        prompt = f"""
        You are a meticulous podcast vetting analyst. Evaluate the following podcast based on the provided checklist and evidence. For each criterion, provide a score from 0 (no fit) to 10 (perfect fit) and a brief justification for your score, citing specific details from the evidence. Finally, provide a concise summary of your overall assessment.

        **Vetting Checklist:**
        {json.dumps(checklist.model_dump(), indent=2)}

        **Evidence (Podcast Data):**
        ---
        {evidence}
        ---

        Generate a JSON object that adheres to the following schema. Ensure your justification for each score directly references the provided evidence.
        """
        try:
            analysis_obj = await self.gemini_service.get_structured_data(
                prompt_template_str=prompt,
                user_query="",
                output_model=VettingAnalysis,
                workflow="vetting_scoring"
            )
            return analysis_obj
        except Exception as e:
            logger.error(f"Failed to score podcast against checklist: {e}", exc_info=True)
            return None

    def _calculate_final_weighted_score(self, analysis: VettingAnalysis, checklist: VettingChecklist) -> float:
        """Calculates the final weighted score out of 10."""
        total_score = 0
        total_weight = 0
        
        checklist_map = {item.criterion: item.weight for item in checklist.checklist}

        for score_item in analysis.scores:
            weight = checklist_map.get(score_item.criterion, 1) # Default weight of 1 if not found
            total_score += score_item.score * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0

        # Normalize the score to be out of 10
        normalized_score = (total_score / (total_weight * 10)) * 10
        return round(normalized_score, 2)

    async def vet_match(self, campaign_data: Dict[str, Any], media_id: int) -> Optional[Dict[str, Any]]:
        """Main method to orchestrate the vetting of a single podcast for a campaign."""
        ideal_desc = campaign_data.get('ideal_podcast_description')
        if not ideal_desc:
            logger.warning(f"Campaign {campaign_data['campaign_id']} has no ideal_podcast_description. Skipping vetting.")
            return None

        # 1. Generate Checklist
        checklist = await self._generate_vetting_checklist(ideal_desc)
        if not checklist:
            return None

        # 2. Gather Evidence
        evidence = await self._gather_podcast_evidence(media_id)

        # 3. Score against Checklist
        analysis = await self._score_podcast_against_checklist(checklist, evidence)
        if not analysis:
            return None

        # 4. Calculate Final Score
        final_score = self._calculate_final_weighted_score(analysis, checklist)

        # 5. Compile and return results
        vetting_results = {
            "vetting_score": final_score,
            "vetting_reasoning": analysis.final_summary,
            "vetting_checklist": checklist.model_dump(),
            "last_vetted_at": datetime.now(timezone.utc)
        }
        return vetting_results