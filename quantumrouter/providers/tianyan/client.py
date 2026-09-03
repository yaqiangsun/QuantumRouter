"""TianYan API client.
Wrap official cqlib high-level TianYanPlatform, remove all low-level Transport/HTTP assemble logic.
Only responsible for TianYan vendor-specific parameter adaptation, network, request envelope,
response check, auth header logic all delegated to native cqlib SDK.
All public methods directly call standardized top-level cqlib platform interfaces.
"""
from __future__ import annotations
from cqlib_adapter.qiskit_ext.tianyan_provider import TianYanProvider
from cqlib_adapter.utils.api_client import ApiClient as CqlibApiClient
from cqlib.quantum_platform import TianYanPlatform, QuantumLanguage


class TianYanApiClient:
    """Cqlib wrapped high-level client for TianYan quantum cloud.
    No manual Transport/HTTP low-level assembly, all network logic inside cqlib.TianYanPlatform.

    Parameters
    ----------
    transport:
        Reserved compatible param, no longer used internally (cqlib manages all transport)
    token:
        Auth token for TianYan cloud login
    """

    def __init__(self, transport, token: str = "") -> None:
        self.token = token
        self._platform = TianYanPlatform(login_key=self.token)
        self.transport = transport
    

    def get_backends(self) -> list[dict]:
        """List available quantum backends for the current user."""
        # two ways both ok
        # provider = TianYanProvider(token=self.token)
        # tmp = provider.backends()

        adapter_client = CqlibApiClient(token=self.token)
        backend_obj_list = adapter_client.get_backends()

        return backend_obj_list
    

    def get_quantum_computer_config(self, computer_id: str) -> dict:
        """Fetch the configuration overview of a quantum computer."""
        return self._platform.get_computer_overview(machine_id=computer_id) or {}


    def get_quantum_machine_config(self, computer_code: str) -> dict:
        """Download the physical machine data."""
        print("[client.py] get_quantum_machine_config computer_code: ", computer_code)
        return self._platform.download_config(machine=computer_code) or {}


    def submit_job(
        self,
        circuits: list[str],
        machine: str,
        *,
        shots: int = 1000,
        language: QuantumLanguage = QuantumLanguage.QCIS,
    ) -> list:
        task_ids = self._platform.submit_experiment(
            circuits,
            machine_name=machine,
            language=language,
            num_shots=shots,
        )
        return task_ids


    def query_job(self, task_ids: list[str]) -> list[dict]:
        adapter_client = CqlibApiClient(token=self.token)
        result_list = adapter_client.query_job(task_ids=task_ids)
        # print("[INFO] out query_job", result_list)
        return result_list
