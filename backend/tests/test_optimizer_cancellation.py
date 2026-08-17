"""Verify that a cancellation request interrupts the registered CP-SAT stage."""

import threading

from app.services import optimizer_service


class BlockingSolver:
    """Stand in for CP-SAT with a solve call that waits until StopSearch is invoked."""

    def __init__(self) -> None:
        """Create synchronization events for the fake solve lifecycle."""
        self.started = threading.Event()
        self.stopped = threading.Event()

    def Solve(self, _model: object) -> int:
        """Wait for cancellation and then return an arbitrary solver status."""
        self.started.set()
        self.stopped.wait(timeout=2)
        return 0

    def StopSearch(self) -> None:
        """Release the blocked solve as CP-SAT does after a cancellation signal."""
        self.stopped.set()


def test_cancel_generation_stops_the_active_solver() -> None:
    """Raise OptimizationCancelledError from a solver stage canceled by scenario id."""
    scenario_id = 987654
    solver = BlockingSolver()
    errors: list[Exception] = []
    optimizer_service._begin_cancellable_generation(scenario_id)
    def run_solver() -> None:
        """Capture the cancellation exception raised in the worker thread."""
        try:
            optimizer_service._solve_with_cancellation(solver, object(), scenario_id)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=run_solver)
    thread.start()
    assert solver.started.wait(timeout=1)
    assert optimizer_service.cancel_generation(scenario_id)
    thread.join(timeout=2)
    optimizer_service._finish_cancellable_generation(scenario_id)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], optimizer_service.OptimizationCancelledError)
