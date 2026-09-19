from abc import ABC, abstractmethod

from jobpilot.core.models import Application, JobListing


class JobConnector(ABC):
    """Interface every job-source connector must implement.

    A connector is responsible for two things: finding job listings, and
    (optionally) submitting an application for one of them. Connectors that
    only aggregate public listings (e.g. an official job-board API) can
    leave `apply` unimplemented and let the application agent fall back to
    emailing the listed contact instead.
    """

    #: Human-readable source name, used for dedupe keys and logging.
    name: str = "base"

    #: Whether this connector automates a site whose Terms of Service
    #: restrict automated use. Surfaced in the CLI/README so the risk is
    #: never silent.
    tos_risk: bool = False

    @abstractmethod
    def search(self, keywords: list[str], country: str, limit: int = 25) -> list[JobListing]:
        """Return job listings matching the given keywords and country."""

    def apply(self, job: JobListing, application: Application) -> bool:
        """Submit an application. Returns True on success.

        Default implementation does nothing - connectors that only source
        listings (no direct apply flow) should rely on the email fallback
        in the application agent instead of overriding this.
        """
        raise NotImplementedError(f"{self.name} does not support direct apply()")
