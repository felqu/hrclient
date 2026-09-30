import json

from app.integrations.llm import LLMProvider
from app.schemas.contracts import MatchResult, MatchingRules


class MatchingService:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def score(self, *, vacancy_id, resume: dict, vacancy: dict, rules: MatchingRules, custom_prompt: str | None) -> MatchResult:
        """Ask an LLM for a validated 0..100 matching assessment."""
        # TODO: apply deterministic black/whitelist and mandatory-skills gates before LLM call.
        # TODO: include structured resume/vacancy, weights and custom_prompt in a versioned prompt.
        response = await self.llm.complete(
            system="You score a candidate-vacancy match and return JSON only.",
            prompt="TODO: render matching prompt",
            json_mode=True,
        )
        data = json.loads(response)
        return MatchResult(vacancy_id=vacancy_id, **data)
