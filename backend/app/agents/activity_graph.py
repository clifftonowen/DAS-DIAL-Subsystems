"""ActivityGraph - Subsystem 3 core: LangGraph generate -> validate loop.

Runs GenerativeAgent, then ValidativeAgent; retries up to max_retries if the
activity is flagged. Wire the real StateGraph here.
"""
from app.gateways.llm_client import LLMApiClient
from app.agents.agents import GenerativeAgent, ValidativeAgent


class ActivityGraph:
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        llm = LLMApiClient()
        self.generator = GenerativeAgent(llm)
        self.validator = ValidativeAgent(llm)

    def run(self, prompt: str) -> dict:
        activity = self.generator.generate(prompt)
        for _ in range(self.max_retries):
            result = self.validator.validate(activity, framework="DAS")
            if result["valid"]:
                activity["status"] = "VALIDATED"
                return activity
            activity = self.generator.generate(prompt)
        activity["status"] = "FLAGGED"
        return activity
