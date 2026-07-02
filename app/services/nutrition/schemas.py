"""Strutture dati normalizzate per gli alimenti.

Tutti i provider esterni (Open Food Facts, FatSecret, Edamam, ...) devono
convertire le loro risposte in :class:`NormalizedFood`, in modo che il resto
dell'applicazione (service, router, calcolo nutrienti) non veda mai payload
grezzi specifici del provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


def _to_float(value: Any) -> Optional[float]:
    """Converte un valore in float, tollerando None, stringhe e virgole.

    Ritorna ``None`` se il valore non è convertibile: questo evita crash
    quando l'API esterna non fornisce un nutriente o lo fornisce vuoto.
    """
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class NormalizedFood:
    """Rappresentazione unica di un alimento, indipendente dal provider.

    I valori nutrizionali sono sempre riferiti a 100 g di prodotto.
    """

    provider: str
    external_id: str
    name: str

    brand: Optional[str] = None
    category: Optional[str] = None

    kcal_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    sugars_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    saturated_fat_per_100g: Optional[float] = None
    fiber_per_100g: Optional[float] = None
    salt_per_100g: Optional[float] = None
    sodium_per_100g: Optional[float] = None

    serving_size: Optional[float] = None
    serving_unit: Optional[str] = None

    # Payload grezzo del provider, conservato per audit/riuso ma mai usato
    # direttamente dalla logica dieta.
    source_payload: Optional[dict] = field(default=None, repr=False)

    # Campi nutrizionali per 100 g gestiti dal sistema.
    NUTRIENT_FIELDS = (
        "kcal_per_100g",
        "protein_per_100g",
        "carbs_per_100g",
        "sugars_per_100g",
        "fat_per_100g",
        "saturated_fat_per_100g",
        "fiber_per_100g",
        "salt_per_100g",
        "sodium_per_100g",
    )

    def to_dict(self, include_payload: bool = False) -> dict:
        """Serializza in dizionario JSON-friendly per le risposte API."""
        data = asdict(self)
        data.pop("source_payload", None)
        if include_payload:
            data["source_payload"] = self.source_payload
        return data

    @classmethod
    def build(cls, provider: str, external_id: str, name: str, **kwargs: Any) -> "NormalizedFood":
        """Costruisce un NormalizedFood applicando la conversione numerica.

        I nutrienti e la porzione vengono normalizzati a float (o None),
        così i provider possono passare valori grezzi senza preoccuparsi
        del tipo.
        """
        numeric_fields = set(cls.NUTRIENT_FIELDS) | {"serving_size"}
        clean: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key in numeric_fields:
                clean[key] = _to_float(value)
            else:
                clean[key] = value
        return cls(
            provider=provider,
            external_id=str(external_id),
            name=name,
            **clean,
        )
