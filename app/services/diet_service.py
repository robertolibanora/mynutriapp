"""Diete paziente: DietPlan (strutturato) + Dieta (PDF legacy).

Allineato alla dashboard web: attiva = ultimo DietPlan published,
altrimenti ultima Dieta per created_at.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.models.models import Dieta, DietPlan
from app.services.nutrition.calculator import NutritionCalculatorService
from app.services.nutrition.service import (
    diet_meal_item_to_dict,
    diet_meal_to_dict,
    diet_plan_to_dict,
    food_to_dict,
)


def create_pdf_diet(
    *,
    patient_id: int,
    data_inizio: date,
    data_fine: date,
    pdf_path: str,
    kcal: int,
    carbo=None,
    proteine=None,
    grassi=None,
    note: Optional[str] = None,
) -> Dieta:
    """Crea una dieta PDF e applica il guard licensing se risulta attiva."""
    from app.models.models import Patient, db
    from app.services.licensing_service import assert_can_increase_active_patients

    patient = db.session.get(Patient, patient_id)
    if patient is None:
        raise ValueError(f"Paziente {patient_id} inesistente")

    if data_fine >= date.today():
        nutri_id = getattr(patient, "nutrizionista_id", None)
        if nutri_id is not None:
            assert_can_increase_active_patients(int(nutri_id), patient_id=int(patient.id))

    dieta = Dieta(
        patient_id=patient_id,
        data_inizio=data_inizio,
        data_fine=data_fine,
        pdf_path=pdf_path,
        kcal=kcal,
        carbo=carbo,
        proteine=proteine,
        grassi=grassi,
        note=note,
    )
    db.session.add(dieta)
    db.session.commit()
    return dieta


def list_plans_for_patient(patient_id: int) -> list[DietPlan]:
    return (
        DietPlan.query.filter_by(patient_id=patient_id, status="published")
        .order_by(DietPlan.created_at.desc())
        .all()
    )


def list_pdf_for_patient(patient_id: int) -> list[Dieta]:
    return (
        Dieta.query.filter_by(patient_id=patient_id)
        .order_by(Dieta.created_at.desc())
        .all()
    )


def list_for_patient(patient_id: int) -> dict[str, Any]:
    """Ritorna piani published e diete PDF del paziente (come lista web)."""
    return {
        "plans": list_plans_for_patient(patient_id),
        "pdf_diete": list_pdf_for_patient(patient_id),
    }


def get_active_for_patient(patient_id: int) -> Optional[tuple[str, Any]]:
    """(kind, model) con kind in {'diet_plan','dieta_pdf'} oppure None."""
    plan = (
        DietPlan.query.filter_by(patient_id=patient_id, status="published")
        .order_by(DietPlan.created_at.desc())
        .first()
    )
    if plan is not None:
        return "diet_plan", plan

    dieta = (
        Dieta.query.filter_by(patient_id=patient_id)
        .order_by(Dieta.created_at.desc())
        .first()
    )
    if dieta is not None:
        return "dieta_pdf", dieta
    return None


def get_plan_for_patient(plan_id: int, patient_id: int) -> Optional[DietPlan]:
    plan = DietPlan.query.filter_by(id=plan_id).first()
    if plan is None or plan.patient_id != patient_id:
        return None
    if plan.status != "published":
        return None
    return plan


def get_pdf_for_patient(dieta_id: int, patient_id: int) -> Optional[Dieta]:
    dieta = Dieta.query.filter_by(id=dieta_id).first()
    if dieta is None or dieta.patient_id != patient_id:
        return None
    return dieta


def get_for_patient(diet_id: int, patient_id: int) -> Optional[tuple[str, Any]]:
    """Lookup dettaglio: prova DietPlan published, poi Dieta PDF.

    ID possono collidere tra tabelle: priorità al DietPlan (flusso nuovo).
    """
    plan = get_plan_for_patient(diet_id, patient_id)
    if plan is not None:
        return "diet_plan", plan
    dieta = get_pdf_for_patient(diet_id, patient_id)
    if dieta is not None:
        return "dieta_pdf", dieta
    return None


def _iso_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep="T", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _pdf_is_active(dieta: Dieta, today: Optional[date] = None) -> bool:
    today = today or date.today()
    return bool(dieta.data_fine and dieta.data_fine >= today)


def serialize_plan_summary(plan: DietPlan, *, attiva: bool = False) -> dict[str, Any]:
    base = diet_plan_to_dict(plan)
    return {
        "kind": "diet_plan",
        "id": plan.id,
        "title": plan.title,
        "goal": plan.goal,
        "notes": plan.notes,
        "status": plan.status,
        "attiva": attiva,
        "data_inizio": None,
        "data_fine": None,
        "has_pdf": False,
        "created_at": _iso_dt(plan.created_at),
        "target_kcal": base.get("target_kcal"),
        "target_protein_pct": base.get("target_protein_pct"),
        "target_carbs_pct": base.get("target_carbs_pct"),
        "target_fat_pct": base.get("target_fat_pct"),
        "meals_count": len(plan.meals or []),
    }


def serialize_pdf_summary(dieta: Dieta, *, today: Optional[date] = None) -> dict[str, Any]:
    attiva = _pdf_is_active(dieta, today=today)
    return {
        "kind": "dieta_pdf",
        "id": dieta.id,
        "title": f"Dieta {dieta.id}",
        "goal": None,
        "notes": dieta.note,
        "status": "attiva" if attiva else "scaduta",
        "attiva": attiva,
        "data_inizio": _iso_dt(dieta.data_inizio),
        "data_fine": _iso_dt(dieta.data_fine),
        "has_pdf": bool(dieta.pdf_path),
        "created_at": _iso_dt(dieta.created_at),
        "kcal": dieta.kcal,
        "carbo": float(dieta.carbo) if dieta.carbo is not None else None,
        "proteine": float(dieta.proteine) if dieta.proteine is not None else None,
        "grassi": float(dieta.grassi) if dieta.grassi is not None else None,
    }


def serialize_plan_detail(plan: DietPlan, *, attiva: bool = False) -> dict[str, Any]:
    meals_out = []
    for meal in plan.meals or []:
        meal_dict = diet_meal_to_dict(meal)
        meal_totals = NutritionCalculatorService.compute_meal(meal.items or [])
        items_out = []
        for item in meal.items or []:
            item_dict = diet_meal_item_to_dict(item)
            food = getattr(item, "food", None)
            item_dict["food"] = food_to_dict(food) if food is not None else None
            item_dict["unita"] = "g"
            items_out.append(item_dict)
        meal_dict["items"] = items_out
        meal_dict["totals"] = {
            "kcal": meal_totals.get("kcal"),
            "protein": meal_totals.get("protein"),
            "carbs": meal_totals.get("carbs"),
            "fat": meal_totals.get("fat"),
        }
        meals_out.append(meal_dict)

    plan_totals = NutritionCalculatorService.compute_plan(plan.meals or [])
    summary = serialize_plan_summary(plan, attiva=attiva)
    summary["meals"] = meals_out
    summary["totals"] = {
        "kcal": plan_totals.get("kcal"),
        "protein": plan_totals.get("protein"),
        "carbs": plan_totals.get("carbs"),
        "fat": plan_totals.get("fat"),
    }
    return summary


def serialize_pdf_detail(
    dieta: Dieta,
    *,
    today: Optional[date] = None,
    attiva: Optional[bool] = None,
) -> dict[str, Any]:
    detail = serialize_pdf_summary(dieta, today=today)
    if attiva is not None:
        detail["attiva"] = attiva
        if attiva:
            detail["status"] = "attiva"
    detail["meals"] = []
    detail["totals"] = {
        "kcal": float(dieta.kcal) if dieta.kcal is not None else None,
        "protein": float(dieta.proteine) if dieta.proteine is not None else None,
        "carbs": float(dieta.carbo) if dieta.carbo is not None else None,
        "fat": float(dieta.grassi) if dieta.grassi is not None else None,
    }
    return detail


def serialize_diet(kind: str, obj: Any, *, attiva: bool = False) -> dict[str, Any]:
    if kind == "diet_plan":
        return serialize_plan_detail(obj, attiva=attiva)
    return serialize_pdf_detail(obj, attiva=attiva)


def build_list_payload(patient_id: int) -> dict[str, Any]:
    data = list_for_patient(patient_id)
    active = get_active_for_patient(patient_id)
    active_ref = None
    active_kind = None
    active_id = None
    if active is not None:
        active_kind, active_obj = active
        active_id = active_obj.id
        active_ref = {"kind": active_kind, "id": active_id}

    diets: list[dict[str, Any]] = []
    for plan in data["plans"]:
        diets.append(
            serialize_plan_summary(
                plan,
                attiva=(active_kind == "diet_plan" and plan.id == active_id),
            )
        )
    today = date.today()
    for dieta in data["pdf_diete"]:
        diets.append(
            serialize_pdf_summary(
                dieta,
                today=today,
            )
        )
        # attiva flag già da date PDF; allinea anche a dashboard active
        if active_kind == "dieta_pdf" and dieta.id == active_id:
            diets[-1]["attiva"] = True

    return {"active": active_ref, "diets": diets}
