"""Backend implementations for the LingYun provider.

This module holds the two backend subclasses
(:class:`LingYunQuantumBackend` and :class:`LingYunSimulatorBackend`)
that bind the generic backend contract to the LingYun REST surface.
"""

from __future__ import annotations

from typing import Any

from ....backend.base import Backend
from ..client import LingYunApiClient


class LingYunBackend(Backend):
    """Base for LingYun backends; owns the API client.

    Subclasses set :attr:`_is_simulator` to distinguish the
    quantum / simulator variants.
    """

    _is_simulator: bool = False

    def __init__(
        self,
        configuration,
        api_client: LingYunApiClient,
    ) -> None:
        super().__init__(configuration=configuration, api_client=api_client)

    @property
    def is_simulator(self) -> bool:
        return self._is_simulator

    def fetch_configuration(self) -> dict:
        """Download the full hardware/calibration configuration."""
        return self.api_client.get_quantum_machine_config(
            self.configuration.backend_name
        )

    def submit_job(
        self,
        circuits: list[str],
        *,
        shots: int = 1000,
        **kwargs: Any,
    ) -> list[str]:
        """Submit a job and return the assigned task IDs."""
        return self.api_client.submit_job(
            circuits=circuits,
            machine=self.configuration.backend_name,
            shots=shots,
            language=kwargs.get("language", "qcis"),
        )

    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Fetch results for previously submitted task IDs."""
        result = self.api_client.query_job(task_ids)
        # LingYun wraps results in an object with different keys
        # depending on the endpoint version; normalize to a list.
        if isinstance(result, dict):
            return result.get("experimentResultModelList", [])
        return result or []


class LingYunQuantumBackend(LingYunBackend):
    """A real quantum computer on the LingYun platform."""

    _is_simulator = False


class LingYunSimulatorBackend(LingYunBackend):
    """A cloud-hosted simulator on the LingYun platform."""

    _is_simulator = True
