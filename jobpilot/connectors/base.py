from abc import ABC, abstractmethod

from jobpilot.core.models import JobListing


class JobConnector(ABC):
    """Interface every job-source connector must implement.

    A connector's only job is finding listings. JobPilot's "apply" step is
    the same for every source: find a contact email on the listing page
    and send a tailored application to it (see
    `jobpilot/agents/application_agent.py`) - so connectors don't need to
    know how to submit a platform-specific form.
    """

    #: Human-readable source name, used for dedupe keys and logging.
    name: str = "base"

    @abstractmethod
    def search(self, keywords: list[str], country: str, limit: int = 25) -> list[JobListing]:
        """Return job listings matching the given keywords and country."""
