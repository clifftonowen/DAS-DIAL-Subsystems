"""GenerativeAgent + ValidativeAgent - the two LLM nodes in the graph."""
from app.gateways.llm_client import LLMApiClient


class GenerativeAgent:
    def __init__(self, llm: LLMApiClient):
        self.llm = llm

    def generate(self, prompt: str) -> dict:
        raw = self.llm.complete(prompt)
        return {"content": raw, "status": "GENERATED"}


class ValidativeAgent:
    def __init__(self, llm: LLMApiClient):
        self.llm = llm

    def validate(self, activity: dict, framework: str) -> dict:
        # TODO: ask the LLM whether `activity` respects the DAS framework
        return {"valid": True, "notes": ""}
