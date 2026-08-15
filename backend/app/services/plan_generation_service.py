"""Orchestrates `POST /scenarios/{id}/generate`: runs Phase 3's `optimizer_service`
unchanged (still solving all 5 supported objective types), narrows the result
down to the scenario's own selected `scenario_objectives` (if any were submitted,
per their `display_order`), persists each surviving plan, and reloads it as a
`DegreePlanOut` ready to return over HTTP."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.enums import OptimizationObjectiveType
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_objective import ScenarioObjective
from app.schemas.plan import DegreePlanOut
from app.services import optimizer_persistence, optimizer_service
from app.services.optimizer_service import GeneratedPlan


def generate_and_persist_plans(db: Session, planning_scenario_id: int) -> list[DegreePlanOut]:
    """Generate, filter/order, and persist degree plans for one scenario, returning
    each as a `DegreePlanOut`. Raises `ValueError` if the scenario doesn't exist."""
    scenario = _load_scenario(db, planning_scenario_id)
    generated_plans = optimizer_service.generate_plans(db, planning_scenario_id)
    selected_plans = _select_requested_plans(db, planning_scenario_id, generated_plans)
    degree_plan_ids = [
        optimizer_persistence.persist_plan(db, planning_scenario_id, scenario.student_id, plan).degree_plan_id
        for plan in selected_plans
    ]
    db.flush()
    return [_reload_plan(db, degree_plan_id) for degree_plan_id in degree_plan_ids]


def _load_scenario(db: Session, planning_scenario_id: int) -> PlanningScenario:
    """Look up a planning scenario by id, raising `ValueError` if it doesn't exist."""
    scenario = db.get(PlanningScenario, planning_scenario_id)
    if scenario is None:
        raise ValueError(f"planning_scenario_id {planning_scenario_id} not found")
    return scenario


def _select_requested_plans(
    db: Session, planning_scenario_id: int, generated_plans: list[GeneratedPlan]
) -> list[GeneratedPlan]:
    """Narrow `generated_plans` to the scenario's own `scenario_objectives` selection,
    in that selection's `display_order`. A whole-model infeasibility (no objective_type
    at all) always passes through unfiltered. No selection at all keeps every plan
    in the solver's default order."""
    if any(plan.objective_type is None for plan in generated_plans):
        return generated_plans
    requested_order = _requested_objective_order(db, planning_scenario_id)
    if not requested_order:
        return generated_plans
    plans_by_objective = {plan.objective_type: plan for plan in generated_plans}
    return [plans_by_objective[objective] for objective in requested_order if objective in plans_by_objective]


def _requested_objective_order(db: Session, planning_scenario_id: int) -> list[OptimizationObjectiveType]:
    """Return this scenario's selected objective types, ordered by display_order
    (nulls last, then insertion order)."""
    rows = (
        db.query(ScenarioObjective)
        .filter(ScenarioObjective.planning_scenario_id == planning_scenario_id)
        .order_by(
            ScenarioObjective.display_order.asc().nulls_last(), ScenarioObjective.scenario_objective_id.asc()
        )
        .all()
    )
    return [row.objective_type for row in rows]


def _reload_plan(db: Session, degree_plan_id: int) -> DegreePlanOut:
    """Reload a just-persisted plan as a `DegreePlanOut` (never `None` -- it was just created)."""
    plan = optimizer_persistence.load_degree_plan(db, degree_plan_id)
    assert plan is not None
    return plan
