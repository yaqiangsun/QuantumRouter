"""Abstract backend contract.

A backend wraps one quantum computer or simulator and exposes the
operations users care about: querying its configuration, submitting
jobs, and fetching results.

Implementations (``LingYunQuantumBackend``, ...) delegate the actual
request/response to a transport-owned client, but present the same
surface to user code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Union

from ..types import BackendStatus, JobStatus
from .configuration import BackendConfiguration
from qiskit.providers import BackendV2 as Backend, Options, JobV1
from qiskit.circuit import QuantumCircuit


class Backend(ABC):
    """Vendor-agnostic quantum backend interface.

    Parameters
    ----------
    configuration:
        The :class:`BackendConfiguration` describing this backend.
    api_client:
        The transport-backed client used to reach the provider's API.
        Typed as ``Any`` so providers can ship their own client
        subclass without creating an import cycle here.
    """

    def __init__(self, configuration: BackendConfiguration, api_client: Any) -> None:
        self.configuration = configuration
        self.api_client = api_client

    # ------------------------------------------------------------------ #
    # Metadata
    # ------------------------------------------------------------------ #
    @property
    def name(self) -> str:
        """Human-readable backend identifier."""
        return self.configuration.backend_name

    @property
    def status(self) -> BackendStatus:
        """Current lifecycle state of the backend."""
        return self.configuration.status

    @property
    def is_simulator(self) -> bool:
        """True if this backend is a simulator rather than a real chip."""
        return self.configuration.simulator

    @property
    def is_online(self) -> bool:
        """True if the backend is available to accept jobs."""
        return self.status in (BackendStatus.RUNNING, BackendStatus.ONLINE)

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #
    @abstractmethod
    def submit_job(
        self,
        circuits: list[str],
        *,
        shots: int = 1000,
        **kwargs: Any,
    ) -> list[str]:
        """Submit a list of circuit strings as a single job.

        Returns
        -------
        list[str]
            The task IDs assigned by the provider.
        """

    @abstractmethod
    def query_job(self, task_ids: list[str]) -> list[dict]:
        """Fetch results for previously submitted task IDs."""

    @abstractmethod
    def fetch_configuration(self) -> dict:
        """Download the full hardware/calibration configuration."""

    @abstractmethod
    def run(
        self,
        run_input: Union[QuantumCircuit, list[QuantumCircuit]],
        shots: int = 1024,
        readout_calibration: bool = True,
        auto_transpile: bool = True,
        **options: Any,
    ) -> JobV1:
        """Submits a job to the backend."""


    # ------------------------------------------------------------------ #
    # Niceties
    # ------------------------------------------------------------------ #
    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        kind = "simulator" if self.is_simulator else "quantum"
        return f"<{self.__class__.__name__} {self.name!r} ({kind})>"
