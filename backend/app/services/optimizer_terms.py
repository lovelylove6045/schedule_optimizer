"""Builds the ordered list of terms a planning scenario's solver is allowed
to place courses into: starting at `planning_scenarios.start_term_id`,
dropping any `scenario_terms.is_excluded` term, and (unless
`allow_summer`) dropping SUMMER terms."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.planning_scenario import PlanningScenario
from app.models.scenario_term import ScenarioTerm
from app.models.term import Term

DEFAULT_MAX_HORIZON_TERMS = 16
ABSOLUTE_MAX_HORIZON_TERMS = 36
SUMMER_TERM_TYPE = "SUMMER"


def build_term_horizon(
    db: Session, scenario: PlanningScenario, maximum_terms: int = DEFAULT_MAX_HORIZON_TERMS
) -> list[Term]:
    """Return eligible terms from the scenario start through the requested safe horizon.
    Excluded/disallowed summer terms are removed and an explicit target remains hard."""
    start_term = db.get(Term, scenario.start_term_id) if scenario.start_term_id else None
    excluded_term_ids = _load_excluded_term_ids(db, scenario.planning_scenario_id)
    candidate_terms = _load_terms_from(db, start_term)
    eligible_terms = [
        term
        for term in candidate_terms
        if term.term_id not in excluded_term_ids and _is_summer_allowed(term, scenario)
    ]
    eligible_terms = _truncate_at_target(db, scenario, eligible_terms)
    return eligible_terms[: min(maximum_terms, ABSOLUTE_MAX_HORIZON_TERMS)]


def _truncate_at_target(db: Session, scenario: PlanningScenario, terms: list[Term]) -> list[Term]:
    """Drop every term after the scenario's target_graduation_term_id, if it has one."""
    if scenario.target_graduation_term_id is None:
        return terms
    target_term = db.get(Term, scenario.target_graduation_term_id)
    if target_term is None:
        return terms
    return [term for term in terms if term.sequence_index <= target_term.sequence_index]


def _load_terms_from(db: Session, start_term: Term | None) -> list[Term]:
    """Return every term at or after `start_term`'s sequence index, ordered chronologically."""
    query = db.query(Term).order_by(Term.sequence_index.asc())
    if start_term is not None:
        query = query.filter(Term.sequence_index >= start_term.sequence_index)
    return query.all()


def _load_excluded_term_ids(db: Session, planning_scenario_id: int) -> set[int]:
    """Return the term ids this scenario explicitly excludes via `scenario_terms.is_excluded`."""
    rows = (
        db.query(ScenarioTerm.term_id)
        .filter(
            ScenarioTerm.planning_scenario_id == planning_scenario_id,
            ScenarioTerm.is_excluded.is_(True),
        )
        .all()
    )
    return {term_id for (term_id,) in rows}


def _is_summer_allowed(term: Term, scenario: PlanningScenario) -> bool:
    """Return whether this term is eligible given the scenario's summer-enrollment preference."""
    if term.term_type != SUMMER_TERM_TYPE:
        return True
    return scenario.allow_summer
