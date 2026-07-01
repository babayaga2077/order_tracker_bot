"""Single place where providers are wired together. This is where the
config (.env) meets the concrete implementations from track17.py /
store_generic.py (or your own files like ozon.py, wildberries.py, etc.)."""
from typing import Optional

from config import Config

from .cypost import CyprusPostProvider
from .imusic import ImusicProvider
from .store_generic import GenericStoreProvider
from .track17 import Track17Provider


def build_registry(config: Config):
    """Returns (parcel_provider, store_providers):
    - parcel_provider: the single adapter for tracking parcels by tracking
      number (None if TRACK17_API_KEY is not set).
    - store_providers: a {site_name: provider} dict for order statuses shown
      directly on a store's site. Add your own adapters here.
    """
    parcel_provider: Optional[Track17Provider] = (
        Track17Provider(config.track17_api_key) if config.track17_api_key else None
    )

    store_providers = {"cypost": CyprusPostProvider(), "imusic": ImusicProvider()}
    if config.generic_store_state_path:
        store_providers["generic"] = GenericStoreProvider(config.generic_store_state_path)

    # Examples for extending this to specific marketplaces:
    # from .ozon import OzonProvider
    # store_providers["ozon"] = OzonProvider(config.ozon_state_path)
    #
    # from .wildberries import WildberriesProvider
    # store_providers["wildberries"] = WildberriesProvider(config.wb_state_path)

    return parcel_provider, store_providers
