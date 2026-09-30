from abc import ABC, abstractmethod


class ApplicationGateway(ABC):
    @abstractmethod
    async def send(self, *, vacancy_external_id: str, resume_external_id: str | None, letter: str) -> str:
        """Send an application and return external negotiation identifier."""


class HHApplicationGateway(ApplicationGateway):
    async def send(self, *, vacancy_external_id: str, resume_external_id: str | None, letter: str) -> str:
        # TODO: POST official HH /negotiations endpoint using a valid applicant OAuth token.
        # TODO: Map non-retryable HTTP errors to domain errors before queue retry handling.
        raise NotImplementedError("HH application sender is not configured")
