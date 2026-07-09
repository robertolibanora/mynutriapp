"""Base astratta dei provider nutrizionali ed errori correlati.

Ogni provider (Open Food Facts, FatSecret, Edamam, ...) implementa
:class:`NutritionProvider`. Il resto dell'app ottiene un provider tramite
la factory :func:`get_nutrition_provider`, quindi router e logica dieta non
dipendono mai da un provider specifico.
"""

from __future__ import annotations

import abc
from typing import List, Optional

from .schemas import NormalizedFood


# ========================
# ERRORI DOMINIO PROVIDER
# ========================

class NutritionProviderError(Exception):
    """Errore generico di un provider nutrizionale."""


class ProviderTimeoutError(NutritionProviderError):
    """L'API esterna non ha risposto in tempo utile."""


class ProviderUnavailableError(NutritionProviderError):
    """L'API esterna è irraggiungibile o ha risposto con un errore."""


class FoodNotFoundError(NutritionProviderError):
    """L'alimento richiesto non è stato trovato presso il provider."""


class UnsupportedProviderError(NutritionProviderError):
    """È stato richiesto un provider non registrato/non supportato."""


# ========================
# BASE ASTRATTA PROVIDER
# ========================

class NutritionProvider(abc.ABC):
    """Interfaccia comune a tutti i provider nutrizionali."""

    #: Nome logico del provider (deve coincidere con la chiave del registry).
    name: str = "base"

    @abc.abstractmethod
    def search_foods(self, query: str, limit: int = 10) -> List[NormalizedFood]:
        """Cerca alimenti per query testuale.

        Ritorna una lista (eventualmente vuota) di :class:`NormalizedFood`.
        Deve sollevare :class:`ProviderTimeoutError` /
        :class:`ProviderUnavailableError` in caso di problemi di rete.
        """

    @abc.abstractmethod
    def get_food_details(self, external_id: str) -> NormalizedFood:
        """Recupera il dettaglio di un singolo alimento.

        Solleva :class:`FoodNotFoundError` se l'alimento non esiste.
        """


# ========================
# REGISTRY + FACTORY
# ========================

def _build_registry() -> dict:
    """Costruisce la mappa nome->classe provider.

    L'import è locale per evitare import circolari e per non caricare
    dipendenze di rete se un provider non viene usato.
    """
    from .openfoodfacts import OpenFoodFactsProvider
    from .usda_fdc import UsdaFdcProvider

    return {
        OpenFoodFactsProvider.name: OpenFoodFactsProvider,
        UsdaFdcProvider.name: UsdaFdcProvider,
        # Provider futuri (nessuna modifica ai router necessaria):
        # FatSecretProvider.name: FatSecretProvider,
        # EdamamProvider.name: EdamamProvider,
    }


def get_available_providers() -> List[str]:
    """Elenca i nomi dei provider disponibili."""
    return sorted(_build_registry().keys())


def get_nutrition_provider(name: Optional[str] = None) -> NutritionProvider:
    """Factory: ritorna l'istanza del provider configurato.

    Se ``name`` è ``None`` viene letto ``NUTRITION_PROVIDER`` dalla config
    (default: ``usda_fdc``). Solleva :class:`UnsupportedProviderError`
    se il provider non è registrato.
    """
    if name is None:
        try:
            from flask import current_app

            name = current_app.config.get("NUTRITION_PROVIDER")
        except Exception:
            name = None
    if not name:
        import os

        name = os.getenv("NUTRITION_PROVIDER", "usda_fdc")

    name = str(name).strip().lower()
    registry = _build_registry()
    provider_cls = registry.get(name)
    if provider_cls is None:
        raise UnsupportedProviderError(
            f"Provider nutrizionale non supportato: '{name}'. "
            f"Disponibili: {', '.join(sorted(registry.keys()))}"
        )
    return provider_cls()
