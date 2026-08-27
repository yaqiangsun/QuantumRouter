"""Backend implementations for the IBM Quantum provider.

Two flavors: real quantum computers (:class:`IBMBackend`) and
cloud-hosted simulators (:class:`IBMSimulatorBackend`). Both share
the same job lifecycle — submit, query, fetch configuration — and
differ only in ``is_simulator``.
"""

from __future__ import annotations

from ...backend.base import Backend
from .client import IBMApiClient


class IBMBackend(Backend):
    """Base for IBM Quantum backends; owns the API client."""

    _is_simulator: bool = False

    def __init__(self, configuration, api_client: IBMApiClient) -> None:
        super().__init__(configuration=configuration, api_client=api_client)

    @property
    def is_simulator(self) -> bool:
        return self._is_simulator

    def fetch_configuration(self) -> dict:
        """Download the backend configuration (properties)."""
        return self.api_client.get_machine_config(
            self.configuration.backend_name
        )

    def submit_job(
        self,
        circuits: list[str],
        *,
        shots: int = 1000,
    ) -> list[str]:
        """Submit OpenQASM circuits and return assigned job IDs."""
        return self.api_client.submit_job(
            circuits=circuits,
            machine=self.configuration.backend_name,
            shots=shots,
        )

    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Fetch results for previously submitted job IDs."""
        result = self.api_client.query_job(task_ids)
        # Normalize to a list of dicts for the calling code.
        if isinstance(result, dict):
            return list(result.values())
        return result or []


class IBMQuantumBackend(IBMBackend):
    """A real quantum computer on IBM Quantum Platform."""

    _is_simulator = False


class IBMSimulatorBackend(IBMBackend):
    """A cloud-hosted simulator on IBM Quantum Platform."""

    _is_simulator = True
