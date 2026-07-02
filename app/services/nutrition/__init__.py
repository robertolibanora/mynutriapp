"""Modulo nutrizione: provider esterni, normalizzazione, calcolo e servizio.

Punti di ingresso principali:
- :class:`NutritionService`      -> orchestrazione (ricerca, import, diete, totali)
- :func:`get_nutrition_provider` -> factory del provider configurato
- :class:`NutritionCalculatorService` -> calcolo nutrienti centralizzato
- :class:`NormalizedFood`        -> struttura dati alimento normalizzata
"""

from .calculator import NUTRIENTS, NutritionCalculatorService
from .providers import (
    FoodNotFoundError,
    NutritionProvider,
    NutritionProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedProviderError,
    get_available_providers,
    get_nutrition_provider,
)
from .schemas import NormalizedFood
from .service import (
    NutritionService,
    NutritionServiceError,
    ResourceNotFoundError,
    diet_meal_item_to_dict,
    diet_meal_to_dict,
    diet_plan_to_dict,
    food_to_dict,
)

__all__ = [
    "NUTRIENTS",
    "NutritionCalculatorService",
    "NutritionProvider",
    "NutritionProviderError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "FoodNotFoundError",
    "UnsupportedProviderError",
    "get_nutrition_provider",
    "get_available_providers",
    "NormalizedFood",
    "NutritionService",
    "NutritionServiceError",
    "ResourceNotFoundError",
    "food_to_dict",
    "diet_plan_to_dict",
    "diet_meal_to_dict",
    "diet_meal_item_to_dict",
]
