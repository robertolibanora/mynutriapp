"""Provider Open Food Facts.

Documentazione API: https://world.openfoodfacts.org/data
- Ricerca:  /cgi/search.pl
- Dettaglio: /api/v2/product/{barcode}.json

Il provider si occupa unicamente di parlare con l'API e di convertire la
risposta in :class:`NormalizedFood`. Nessun payload grezzo esce da qui se
non dentro ``source_payload``.
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


class OpenFoodFactsProvider(NutritionProvider):
    """Implementazione del provider basata su Open Food Facts."""

    name = "openfoodfacts"

    # Campi richiesti all'API per ridurre il payload trasferito.
    _FIELDS = (
        "code,product_name,product_name_it,brands,categories,"
        "serving_size,serving_quantity,nutriments"
    )

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or self._config("OPENFOODFACTS_BASE_URL", "https://world.openfoodfacts.org")).rstrip("/")
        self.timeout = float(timeout or self._config("NUTRITION_HTTP_TIMEOUT", 8))
        self.user_agent = user_agent or self._config(
            "OPENFOODFACTS_USER_AGENT", "MyNutriApp/1.0 (nutrition module)"
        )

    # ------------------------------------------------------------------
    # Config helper (funziona sia dentro Flask sia standalone/test)
    # ------------------------------------------------------------------
    @staticmethod
    def _config(key: str, default: Any) -> Any:
        try:
            from flask import current_app

            if current_app:
                return current_app.config.get(key, os.getenv(key, default))
        except Exception:
            pass
        return os.getenv(key, default)

    # ------------------------------------------------------------------
    # API pubblica del provider
    # ------------------------------------------------------------------
    def search_foods(self, query: str, limit: int = 10) -> List[NormalizedFood]:
        query = (query or "").strip()
        if not query:
            return []

        limit = max(1, min(int(limit or 10), 50))
        fetch_size = min(limit * 3, 30)

        results = self._search_v2(query, fetch_size)
        if not results:
            results = self._search_legacy(query, fetch_size)

        results = self._filter_by_query(query, results)
        results = self._rank_results(query, results)
        return results[:limit]

    def _search_v2(self, query: str, fetch_size: int) -> List[NormalizedFood]:
        """API v2 (più stabile del vecchio cgi/search.pl)."""
        params = {
            "q": query,
            "page_size": fetch_size,
            "fields": self._FIELDS,
            "sort_by": "unique_scans_n",
            "lc": "it",
        }
        # Preferisci il dominio italiano per risultati più pertinenti.
        urls = ["https://it.openfoodfacts.org", self.base_url, "https://world.openfoodfacts.org"]
        seen_bases = set()
        for base in urls:
            base = base.rstrip("/")
            if base in seen_bases:
                continue
            seen_bases.add(base)
            try:
                data = self._get(f"{base}/api/v2/search", params)
                products = data.get("products") or []
                out: List[NormalizedFood] = []
                for product in products:
                    normalized = self._normalize(product)
                    if normalized is not None:
                        out.append(normalized)
                if out:
                    return out
            except (ProviderTimeoutError, ProviderUnavailableError) as exc:
                logger.warning("Ricerca OFF v2 fallita su %s: %s", base, exc)
        return []

    def _search_legacy(self, query: str, fetch_size: int) -> List[NormalizedFood]:
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": fetch_size,
            "fields": self._FIELDS,
            "sort_by": "unique_scans_n",
            "lc": "it",
            "countries": "Italy",
            "tagtype_0": "countries",
            "tag_contains_0": "contains",
            "tag_0": "italy",
        }
        data = self._search_with_fallback(params)
        products = data.get("products") or []
        results: List[NormalizedFood] = []
        for product in products:
            normalized = self._normalize(product)
            if normalized is not None:
                results.append(normalized)
        return results

    def _search_with_fallback(self, params: dict) -> dict:
        """Prova il dominio IT, poi world, con filtro paese."""
        urls = [self.base_url]
        if "it.openfoodfacts" not in self.base_url:
            urls.append("https://it.openfoodfacts.org")
        if "world.openfoodfacts" not in self.base_url:
            urls.append("https://world.openfoodfacts.org")

        last_error: Optional[Exception] = None
        for base in urls:
            try:
                return self._get(f"{base.rstrip('/')}/cgi/search.pl", params)
            except (ProviderTimeoutError, ProviderUnavailableError) as exc:
                last_error = exc
                logger.warning("Ricerca OFF fallita su %s: %s", base, exc)
        if last_error:
            raise last_error
        return {}

    @staticmethod
    def _filter_by_query(query: str, items: List[NormalizedFood]) -> List[NormalizedFood]:
        """Tieni solo risultati il cui nome contiene almeno una parola della query."""
        words = [w for w in query.lower().split() if len(w) >= 2]
        if not words:
            return items
        filtered = [
            item for item in items
            if any(w in (item.name or "").lower() for w in words)
        ]
        return filtered if filtered else items

    @staticmethod
    def _rank_results(query: str, items: List[NormalizedFood]) -> List[NormalizedFood]:
        """Ordina per rilevanza: match nome, presenza kcal, popolarità implicita."""
        q = query.lower()

        def score(food: NormalizedFood) -> tuple:
            name = (food.name or "").lower()
            brand = (food.brand or "").lower()
            name_hit = q in name
            brand_hit = q in brand
            starts = name.startswith(q)
            has_kcal = food.kcal_per_100g is not None
            # Preferisci nomi italiani / generici (petto di pollo vs prodotti brand stranieri)
            italian_hint = any(w in name for w in ("pollo", "manzo", "riso", "pasta", "yogurt", "uova", "pesce"))
            return (
                1 if starts else 0,
                1 if name_hit else 0,
                1 if brand_hit else 0,
                1 if has_kcal else 0,
                1 if italian_hint else 0,
                name,
            )

        return sorted(items, key=score, reverse=True)

    def get_food_details(self, external_id: str) -> NormalizedFood:
        external_id = (external_id or "").strip()
        if not external_id:
            raise FoodNotFoundError("external_id mancante")

        url = f"{self.base_url}/api/v2/product/{external_id}.json"
        data = self._get(url, {"fields": self._FIELDS})

        # v2 usa status: 1 trovato, 0 non trovato
        if data.get("status") == 0 or not data.get("product"):
            raise FoodNotFoundError(
                f"Alimento '{external_id}' non trovato su Open Food Facts"
            )

        normalized = self._normalize(data["product"])
        if normalized is None:
            raise FoodNotFoundError(
                f"Alimento '{external_id}' senza dati utilizzabili"
            )
        return normalized

    # ------------------------------------------------------------------
    # Rete
    # ------------------------------------------------------------------
    def _get(self, url: str, params: dict) -> dict:
        headers = {"User-Agent": self.user_agent}
        try:
            response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json() or {}
        except requests.Timeout as exc:
            logger.warning("Timeout Open Food Facts su %s: %s", url, exc)
            raise ProviderTimeoutError("Open Food Facts non ha risposto in tempo") from exc
        except requests.RequestException as exc:
            logger.warning("Errore Open Food Facts su %s: %s", url, exc)
            raise ProviderUnavailableError("Open Food Facts non raggiungibile") from exc
        except ValueError as exc:  # JSON non valido
            logger.warning("Risposta non-JSON da Open Food Facts su %s: %s", url, exc)
            raise ProviderUnavailableError("Risposta non valida da Open Food Facts") from exc

    # ------------------------------------------------------------------
    # Normalizzazione
    # ------------------------------------------------------------------
    def _normalize(self, product: dict) -> Optional[NormalizedFood]:
        """Converte un prodotto OFF in NormalizedFood.

        Ritorna ``None`` se manca sia il nome sia il codice (record inutile).
        """
        if not isinstance(product, dict):
            return None

        external_id = product.get("code") or product.get("_id")
        name = (
            product.get("product_name_it")
            or product.get("product_name")
            or (product.get("brands") or "").split(",")[0].strip()
        )
        if not external_id or not name:
            return None

        nutriments = product.get("nutriments") or {}

        brand = self._first(product.get("brands"))
        category = self._first(product.get("categories"))

        serving_unit = "g" if product.get("serving_quantity") else None

        return NormalizedFood.build(
            provider=self.name,
            external_id=external_id,
            name=str(name).strip(),
            brand=brand,
            category=category,
            kcal_per_100g=self._energy_kcal(nutriments),
            protein_per_100g=nutriments.get("proteins_100g"),
            carbs_per_100g=nutriments.get("carbohydrates_100g"),
            sugars_per_100g=nutriments.get("sugars_100g"),
            fat_per_100g=nutriments.get("fat_100g"),
            saturated_fat_per_100g=nutriments.get("saturated-fat_100g"),
            fiber_per_100g=nutriments.get("fiber_100g"),
            salt_per_100g=nutriments.get("salt_100g"),
            sodium_per_100g=nutriments.get("sodium_100g"),
            serving_size=product.get("serving_quantity"),
            serving_unit=serving_unit,
            source_payload=product,
        )

    @staticmethod
    def _first(value: Optional[str]) -> Optional[str]:
        """Prende la prima voce di una lista separata da virgole."""
        if not value:
            return None
        first = str(value).split(",")[0].strip()
        return first or None

    @staticmethod
    def _energy_kcal(nutriments: dict) -> Optional[Any]:
        """Ricava le kcal per 100 g, con fallback da kJ se serve."""
        kcal = nutriments.get("energy-kcal_100g")
        if kcal is not None:
            return kcal
        kj = nutriments.get("energy_100g") or nutriments.get("energy-kj_100g")
        if kj is not None:
            try:
                return round(float(kj) / 4.184, 2)
            except (TypeError, ValueError):
                return None
        return None
