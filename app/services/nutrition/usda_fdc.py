"""Provider USDA FoodData Central (FDC).

Documentazione API: https://fdc.nal.usda.gov/api-guide.html
- Ricerca:  POST /fdc/v1/foods/search
- Dettaglio: GET  /fdc/v1/food/{fdcId}

Richiede una API key gratuita (data.gov): https://fdc.nal.usda.gov/api-key-signup.html
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

import requests

from .providers import (
    FoodNotFoundError,
    NutritionProvider,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .schemas import NormalizedFood

logger = logging.getLogger(__name__)

# Mappatura nutrientNumber USDA -> campo NormalizedFood (per 100 g).
_NUTRIENT_MAP = {
    "208": "kcal_per_100g",
    "203": "protein_per_100g",
    "205": "carbs_per_100g",
    "269": "sugars_per_100g",
    "204": "fat_per_100g",
    "606": "saturated_fat_per_100g",
    "291": "fiber_per_100g",
    "307": "sodium_per_100g",
}

# Traduzione IT -> EN per ricerche comuni in app dietetica italiana.
# Le frasi intere hanno priorità sulle singole parole.
_IT_EN_FOOD_TERMS = {
    "petto di pollo": "chicken breast raw skinless",
    "coscia di pollo": "chicken thigh",
    "ala di pollo": "chicken wing",
    "pollo arrosto": "chicken roasted",
    "carne macinata": "ground beef",
    "carne di manzo": "beef",
    "bistecca di manzo": "beef steak",
    "filetto di manzo": "beef tenderloin",
    "riso integrale": "brown rice cooked",
    "riso basmati": "rice basmati cooked",
    "pasta integrale": "whole wheat pasta cooked",
    "pasta di semola": "pasta cooked",
    "olio d'oliva": "olive oil",
    "olio extravergine": "olive oil",
    "latte scremato": "milk skim",
    "latte intero": "milk whole",
    "yogurt greco": "greek yogurt",
    "tonno in scatola": "tuna canned",
    "prosciutto crudo": "ham",
    "prosciutto cotto": "ham cooked",
    "pollo": "chicken",
    "manzo": "beef",
    "vitello": "veal",
    "maiale": "pork",
    "tacchino": "turkey",
    "pesce": "fish",
    "salmone": "salmon",
    "tonno": "tuna",
    "uova": "eggs",
    "uovo": "egg",
    "latte": "milk",
    "yogurt": "yogurt",
    "formaggio": "cheese",
    "mozzarella": "mozzarella",
    "parmigiano": "parmesan cheese",
    "ricotta": "ricotta cheese",
    "riso": "rice cooked",
    "pasta": "pasta cooked",
    "pane": "bread",
    "farina": "flour",
    "patate": "potatoes",
    "patata": "potato",
    "pomodoro": "tomato",
    "pomodori": "tomatoes",
    "zucchine": "zucchini",
    "melanzane": "eggplant",
    "melanzana": "eggplant",
    "broccoli": "broccoli",
    "spinaci": "spinach",
    "insalata": "lettuce",
    "carote": "carrots",
    "carota": "carrot",
    "mela": "apple",
    "banana": "banana",
    "arancia": "orange",
    "avena": "oats",
    "olio": "oil",
    "burro": "butter",
    "zucchero": "sugar",
    "miele": "honey",
    "mandorle": "almonds",
    "noci": "walnuts",
    "legumi": "legumes",
    "fagioli": "beans",
    "lenticchie": "lentils",
    "ceci": "chickpeas",
    "tofu": "tofu",
    "petto": "breast",
    "coscia": "thigh",
    "di": "",
    "crudo": "raw",
    "cotto": "cooked",
    "al": "",
    "vapore": "steamed",
}

# Termini generici che non devono influenzare il ranking.
_QUERY_STOPWORDS = frozenset({"di", "al", "con", "e", "in", "da", "del", "della", "the", "and", "or"})


class UsdaFdcProvider(NutritionProvider):
    """Implementazione del provider basata su USDA FoodData Central."""

    name = "usda_fdc"

    _DEFAULT_DATA_TYPES = ("Foundation", "SR Legacy", "Survey (FNDDS)")

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        data_types: Optional[List[str]] = None,
    ) -> None:
        self.api_key = api_key or self._config("USDA_FDC_API_KEY")
        self.base_url = (
            base_url or self._config("USDA_FDC_BASE_URL", "https://api.nal.usda.gov/fdc/v1")
        ).rstrip("/")
        self.timeout = float(timeout or self._config("NUTRITION_HTTP_TIMEOUT", 8))
        raw_types = data_types or self._parse_data_types(
            self._config("USDA_FDC_DATA_TYPES", ",".join(self._DEFAULT_DATA_TYPES))
        )
        self.data_types = raw_types or list(self._DEFAULT_DATA_TYPES)

    @staticmethod
    def _config(key: str, default: Any = None) -> Any:
        try:
            from flask import current_app

            if current_app:
                return current_app.config.get(key, os.getenv(key, default))
        except Exception:
            pass
        return os.getenv(key, default)

    @staticmethod
    def _parse_data_types(value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            return [str(v).strip() for v in value if str(v).strip()]
        return [part.strip() for part in str(value).split(",") if part.strip()]

    def search_foods(self, query: str, limit: int = 10) -> List[NormalizedFood]:
        query = (query or "").strip()
        if not query:
            return []

        if not self.api_key:
            raise ProviderUnavailableError(
                "USDA_FDC_API_KEY non configurata. "
                "Registrati su https://fdc.nal.usda.gov/api-key-signup.html"
            )

        limit = max(1, min(int(limit or 10), 50))
        search_query = self._translate_query(query)

        payload = {
            "query": search_query,
            "pageSize": min(max(limit * 4, 20), 50),
            "dataType": self.data_types,
        }
        data = self._post(f"{self.base_url}/foods/search", payload)
        foods = data.get("foods") or []

        results: List[NormalizedFood] = []
        for food in foods:
            normalized = self._normalize(food)
            if normalized is not None:
                results.append(normalized)

        results = self._rank_results(query, search_query, results)
        with_kcal = [item for item in results if item.kcal_per_100g is not None]
        if len(with_kcal) >= max(3, limit // 2):
            results = with_kcal + [item for item in results if item.kcal_per_100g is None]
        return results[:limit]

    def get_food_details(self, external_id: str) -> NormalizedFood:
        external_id = (external_id or "").strip()
        if not external_id:
            raise FoodNotFoundError("external_id mancante")

        if not self.api_key:
            raise ProviderUnavailableError(
                "USDA_FDC_API_KEY non configurata. "
                "Registrati su https://fdc.nal.usda.gov/api-key-signup.html"
            )

        data = self._get(f"{self.base_url}/food/{external_id}")
        if not data or not data.get("fdcId"):
            raise FoodNotFoundError(
                f"Alimento '{external_id}' non trovato su USDA FoodData Central"
            )

        normalized = self._normalize(data)
        if normalized is None:
            raise FoodNotFoundError(
                f"Alimento '{external_id}' senza dati utilizzabili"
            )
        return normalized

    # ------------------------------------------------------------------
    # Rete
    # ------------------------------------------------------------------
    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        params = dict(params or {})
        params["api_key"] = self.api_key
        return self._request("GET", url, params=params)

    def _post(self, url: str, payload: dict) -> dict:
        return self._request("POST", url, params={"api_key": self.api_key}, json=payload)

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict:
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json,
                timeout=self.timeout,
            )
            if response.status_code == 404:
                return {}
            if response.status_code == 429:
                raise ProviderUnavailableError(
                    "Limite richieste USDA FDC superato (429). Riprova più tardi."
                )
            response.raise_for_status()
            return response.json() or {}
        except requests.Timeout as exc:
            logger.warning("Timeout USDA FDC su %s: %s", url, exc)
            raise ProviderTimeoutError("USDA FoodData Central non ha risposto in tempo") from exc
        except ProviderUnavailableError:
            raise
        except requests.RequestException as exc:
            logger.warning("Errore USDA FDC su %s: %s", url, exc)
            raise ProviderUnavailableError("USDA FoodData Central non raggiungibile") from exc
        except ValueError as exc:
            logger.warning("Risposta non-JSON da USDA FDC su %s: %s", url, exc)
            raise ProviderUnavailableError("Risposta non valida da USDA FoodData Central") from exc

    # ------------------------------------------------------------------
    # Normalizzazione
    # ------------------------------------------------------------------
    def _normalize(self, food: dict) -> Optional[NormalizedFood]:
        if not isinstance(food, dict):
            return None

        external_id = food.get("fdcId")
        name = (food.get("description") or "").strip()
        if not external_id or not name:
            return None

        nutrients = self._extract_nutrients(food.get("foodNutrients") or [])
        category = self._category_label(food.get("foodCategory"))
        brand = (food.get("brandOwner") or food.get("brandName") or None)
        if brand:
            brand = str(brand).strip() or None

        serving_size = food.get("servingSize")
        serving_unit = food.get("servingSizeUnit")
        if serving_unit:
            serving_unit = str(serving_unit).strip().lower() or None

        sodium_mg = nutrients.pop("sodium_per_100g", None)
        salt_g = None
        if sodium_mg is not None:
            salt_g = round(float(sodium_mg) * 2.5 / 1000, 4)

        return NormalizedFood.build(
            provider=self.name,
            external_id=str(external_id),
            name=name,
            brand=brand,
            category=category,
            sodium_per_100g=sodium_mg,
            salt_per_100g=salt_g,
            serving_size=serving_size,
            serving_unit=serving_unit,
            source_payload=food,
            **nutrients,
        )

    def _extract_nutrients(self, food_nutrients: list) -> dict:
        """Estrae i macro principali da foodNutrients (formato search o detail)."""
        out: dict[str, Optional[float]] = {}
        for item in food_nutrients:
            if not isinstance(item, dict):
                continue

            nutrient_number = self._nutrient_number(item)
            if nutrient_number is None:
                continue

            field = _NUTRIENT_MAP.get(str(nutrient_number))
            if not field:
                continue

            value = item.get("amount")
            if value is None:
                value = item.get("value")
            if value is None:
                continue

            # Preferisci kcal (208) rispetto a kJ (268) se entrambi presenti.
            if field == "kcal_per_100g" and out.get(field) is not None:
                continue

            try:
                out[field] = float(value)
            except (TypeError, ValueError):
                continue

        return out

    @staticmethod
    def _nutrient_number(item: dict) -> Optional[str]:
        nutrient = item.get("nutrient")
        if isinstance(nutrient, dict) and nutrient.get("number") is not None:
            return str(nutrient["number"])
        if item.get("nutrientNumber") is not None:
            return str(item["nutrientNumber"])
        return None

    @staticmethod
    def _category_label(value: Any) -> Optional[str]:
        if isinstance(value, dict):
            text = value.get("description")
            return str(text).strip() if text else None
        if value:
            return str(value).strip()
        return None

    @classmethod
    def _translate_query(cls, query: str) -> str:
        lowered = query.lower().strip()
        if lowered in _IT_EN_FOOD_TERMS:
            translated = _IT_EN_FOOD_TERMS[lowered]
            return translated or lowered

        # Prova match delle frasi più lunghe prima (es. "petto di pollo").
        for phrase, english in sorted(_IT_EN_FOOD_TERMS.items(), key=lambda x: len(x[0]), reverse=True):
            if not phrase or " " not in phrase:
                continue
            if phrase in lowered:
                return english or lowered

        translated_words = []
        for word in lowered.split():
            mapped = _IT_EN_FOOD_TERMS.get(word, word)
            if mapped:
                translated_words.append(mapped)
        return " ".join(translated_words) if translated_words else lowered

    @staticmethod
    def _query_tokens(*queries: str) -> List[str]:
        tokens: List[str] = []
        seen = set()
        for query in queries:
            for word in (query or "").lower().replace(",", " ").split():
                word = word.strip()
                if len(word) < 2 or word in _QUERY_STOPWORDS:
                    continue
                if word not in seen:
                    seen.add(word)
                    tokens.append(word)
        return tokens

    @classmethod
    def _rank_results(
        cls,
        original_query: str,
        search_query: str,
        items: List[NormalizedFood],
    ) -> List[NormalizedFood]:
        tokens = cls._query_tokens(original_query, search_query)

        def score(food: NormalizedFood) -> tuple:
            name = (food.name or "").lower()
            token_hits = sum(1 for token in tokens if token in name)
            token_ratio = token_hits / max(len(tokens), 1)
            has_kcal = food.kcal_per_100g is not None
            raw_bonus = 1 if "raw" in name else 0
            cooked_penalty = 1 if any(x in name for x in ("fried", "breaded", "coated")) else 0
            generic_penalty = 1 if any(x in name for x in ("lunchmeat", "soup", "sopa")) else 0
            return (
                token_hits,
                token_ratio,
                1 if has_kcal else 0,
                raw_bonus,
                -cooked_penalty,
                -generic_penalty,
                name,
            )

        return sorted(items, key=score, reverse=True)
