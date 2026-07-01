from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """The provider failed to fetch a status (tracking number not found, the
    site changed its markup, the session expired, etc). Kept separate from
    programming errors so the scheduler can quietly skip the order and try
    again next run."""


@dataclass
class StatusResult:
    status: str
    detail: str = ""


class BaseProvider(ABC):
    """Common interface for any order/parcel status source.
    To add support for a new site, subclass this and implement
    get_status(); then register the adapter in registry.py."""

    name: str = "base"

    @abstractmethod
    async def get_status(self, order: dict) -> StatusResult:
        """order — an entry from orders.py (see db.py). Must return the
        current status or raise ProviderError if the status couldn't be fetched."""
        raise NotImplementedError
