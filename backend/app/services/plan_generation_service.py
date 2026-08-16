"""Persist recommended and alternative solver results for scenario API routes."""

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


def generate_and_persist_recommended_plan(
    db: Session, planning_scenario_id: int
) -> DegreePlanOut:
    """Generate and persist only the lexicographic recommended plan."""
    scenario = _load_scenario(db, planning_scenario_id)
    generated = optimizer_service.generate_recommended_plan(db, planning_scenario_id)
    plan = optimizer_persistence.persist_plan(
        db, planning_scenario_id, scenario.student_id, generated
    )
    db.flush()
    return _reload_plan(db, plan.degree_plan_id)


def generate_and_persist_alternative_plans(
    db: Session, planning_scenario_id: int
) -> list[DegreePlanOut]:
    """Generate and persist alternatives independently of the recommended plan."""
    scenario = _load_scenario(db, planning_scenario_id)
    existing = optimizer_persistence.list_degree_plans_for_scenario(db, planning_scenario_id)
    excluded = {frozenset((course.course.course_id, course.term_id) for course in plan.courses) for plan in existing}
    generated = optimizer_service.generate_alternative_plans(
        db, planning_scenario_id, excluded_signatures=excluded
    )
    plan_ids = [
        optimizer_persistence.persist_plan(db, planning_scenario_id, scenario.student_id, plan).degree_plan_id
        for plan in generated
    ]
    db.flush()
    return [_reload_plan(db, plan_id) for plan_id in plan_ids]


def _load_scenario(db: Session, planning_scenario_id: int) -> PlanningScenario:
    """Look up a planning scenario by id, raising `ValueError` if it doesn't exist."""
    scenario = db.get(PlanningScenario, planning_scenario_id)
    if scenario is None:
        raise ValueError(f"planning_scenario_id {planning_scenario_id} not found")
    return scenario


def _select_requested_plans(
    db: Session, planning_scenario_id: int, generated_plans: list[GeneratedPlan]
) -> list[GeneratedPlan]:
    """Keep the recommended plan first, followed by requested legacy alternatives."""
    if not generated_plans or generated_plans[0].infeasibility_reason is not None:
        return generated_plans
    requested_order = _requested_objective_order(db, planning_scenario_id)
    if not requested_order:
        return generated_plans
    recommended = generated_plans[0]
    plans_by_objective = {plan.objective_type: plan for plan in generated_plans[1:]}
    alternatives = [
        plans_by_objective[objective]
        for objective in requested_order
        if objective in plans_by_objective
    ]
    return [recommended, *alternatives]


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
