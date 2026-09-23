---
name: quantumrouter
description: >-
  Use the QuantumRouter Python library — the unified interface ("one API, any
  backend") for quantum cloud providers. Trigger this whenever the user works
  with quantum circuits on a cloud vendor or simulator: LingYun (凌云), TianYan
  (天衍), WuYue (五岳), Quafu (夸父), LQCloud, IBM Quantum, or the offline local
  simulator; whenever they call `create_provider`, `provider.backends`,
  `backend.run`, `backend.submit_job`, `quantumrouter.Sampler`, or wrap a
  QuantumRouter backend in a Qiskit `BackendEstimatorV2` / `SamplerQNN`; and
  whenever they want to switch quantum vendors by changing one parameter, or
  debug "circuit works locally but not on the real device".
---

# QuantumRouter

A Python library giving a **vendor-agnostic** interface to multiple quantum
cloud providers. Switching vendors is a one-parameter change; the calling code
stays identical. Layered as `Provider` → `Backend` → `Transport`, with vendor
implementations under `quantumrouter/providers/<vendor>/` that self-register on
import.

- **Repo/package**: `quantumrouter` (PyPI: `pip install quantumrouter`)
- **Python**: ≥ 3.10. Core deps: `qiskit`, `requests`, `dotenv`.
- **Local venv in this repo**: `.venv\Scripts\python.exe` (a managed Python
  will hit `ModuleNotFoundError: quantumrouter`).

## The one entry point

```python
import quantumrouter as qr

provider = qr.create_provider(
    backend="lingyun",               # <- change this to switch vendors
    url="http://127.0.0.1:8000",     # HTTP transport; some vendors are fixed
    token="...",                     # optional for simulators
)
backends = provider.backends(online=True)   # list[Backend], hits the cloud
backend  = provider.backend("lingyun_001")  # one Backend by name
```

`create_provider(backend, *, url=None, token=None, instance=None,
**connection_overrides)` looks the vendor up in a process-wide registry. Vendor
subpackages are imported **lazily** (so installing one vendor never forces
another's deps) — the first call to `create_provider("<vendor>")` triggers the
import and the self-registration.

## Vendors

`create_provider`'s `backend=` accepts these ids. Backend *names* below are
typical — always confirm with `provider.backends(online=True)`, since the real
list comes from the cloud.

| id | Transport | Typical backend name | Env vars | Extra install |
|---|---|---|---|---|
| `local` | none (in-process) | `local_simulator` | none | — |
| `lingyun` | HTTP / PCIe | `lingyun_001` | `LINGYUN_TOKEN`, `LINGYUN_URL` | `quantumrouter[lingyun]` |
| `tianyan` | HTTP | `tianyan_sw` | `TianYan_TOKEN` | `quantumrouter[tianyan]` |
| `wuyue` | HTTP | `WuYue-QPUSim-FullAmpSim` | `WUYUE_TOKEN` | — (core deps) |
| `quafu` | HTTP | `ScQ-Sim10` | `QUANFU_TOKEN` | — (core deps) |
| `lqcloud` | HTTP | `MQ02` (real 24-qubit) | `LQCLOUD_TOKEN` | — (core deps) |
| `ibm` | HTTP (SDK) | — | `IBM_QUANTUM_TOKEN`, `IBM_INSTANCE` | `quantumrouter[ibm]` |

- `local` runs on Qiskit's built-in simulator via `BasicSimulator` (no
  `qiskit-aer`). It needs **no** token, URL, or server — use it to try the whole
  API offline. Optional bit-width: `qr.create_provider("local", n_qubits=16)`.
- `lingyun` defaults its URL to `http://0.0.0.0:8000` when none is given; a
  local simulation server typically runs at `http://127.0.0.1:8000`.
- `quafu` and `lqcloud` have **fixed** cloud addresses, so no URL is needed.
- `lqcloud`'s `MQ02` is a **real** 24-qubit chip on a pay-per-job QPU queue —
  keep shots low when testing.
- `ibm` uses the official `qiskit-ibm-provider` SDK, which owns its own HTTPS
  transport; `instance` is forwarded via `ConnectionConfig.extra`.

## Core API

### Provider

```python
provider.backends(*, simulator=None, online=True, name=None) -> list[Backend]
provider.backend(name) -> Backend          # raises BackendNotFoundError
```

`simulator=True/False` filters sim vs. real chip; `online=True` drops backends
not in RUNNING/ONLINE.

### Backend

Concrete backends subclass Qiskit's `BackendV2` (the abstract `Backend` in
`quantumrouter/backend/base.py` documents the intended contract, but each
vendor binds directly to `BackendV2`). The surface you can rely on:

```python
backend.name                   # str
backend.is_simulator           # bool
backend.num_qubits             # int
backend.target                 # qiskit Target (real coupling map)
backend.configuration          # BackendConfiguration
backend.configuration.status   # BackendStatus  (note: on .configuration, not the backend)
backend.configuration.coupling_map
backend.api_client             # vendor-specific, transport-backed client

# Execution: Qiskit circuits in, a Result out (qiskit JobV1)
job    = backend.run(run_input=[qc], shots=1024,     # a qc or a list[qc]
                     readout_calibration=True, auto_transpile=True)
job.job_id()
counts = job.result().get_counts()

backend.fetch_configuration()  # -> dict: raw hardware/calibration payload
```

**Always submit Qiskit `QuantumCircuit` objects — never a vendor circuit
string** (`"QINIT 4\nH 0"`, OpenQASM, ...). The whole point of QuantumRouter is
that one circuit object travels to every vendor; each backend serializes it to
its own wire format internally. Reach the transpiler, the `Sampler`, and the
`Estimator` through the same circuit object.

Two **QuantumRouter-specific switches** appear on every backend's `run()` (they
are not vendor-private — `readout_calibration` toggles readout-error
mitigation, `auto_transpile` moves transpilation to the backend side, which
knows its own coupling map):

- `backend.run()` accepts them directly.
- `qr.Sampler` passes them through, without exposing them as separate params —
  set them via `options={"run_options": {...}}` or per-call.

`run()` is a `BackendV2.run`, so `transpile(qc, backend=backend)` and Qiskit's
generic adapters work on it directly.

### Sampler (ships with the package)

`quantumrouter.Sampler` is a Qiskit `BackendSamplerV2` adapter; user code —
including `qiskit-machine-learning` — can treat a QuantumRouter backend like any
Qiskit backend.

```python
circuit = ...                       # must contain measurements
circuit.measure_all()               # adds a classical register named "meas"

sampler = qr.Sampler(backend, default_shots=4096,
                     options={"run_options": {"readout_calibration": False}})
result = sampler.run([(circuit, params)]).result()   # PUBs must be in a list
counts = result[0].data.meas.get_counts()            # register name, not get_counts()
```

The circuit **must** have measurement instructions — the sampler does not add
them. Its classical register's name selects the result accessor
(`measure_all()` → `.data.meas`; an explicit `QuantumRegister("c", ...)` →
`.data.c`). `SamplerPubResult` itself has no `get_counts()`.

Config precedence (low → high): module default `DEFAULT_RUN_OPTIONS` (both
`True`) < constructor `options["run_options"]` < explicit `run(...)` kwargs
(`readout_calibration=` / `auto_transpile=`; `None` means "don't override").

### Estimator — there is NO `qr.Estimator`

The package ships only `qr.Sampler`. To get expectation values, wrap the
backend in Qiskit's generic adapter:

```python
from qiskit.primitives import BackendEstimatorV2
from qiskit.quantum_info import SparsePauliOp

estimator = BackendEstimatorV2(backend=backend,
                               options={"default_precision": 0.015625})
job = estimator.run([(ansatz, observable, thetas)])   # thetas: broadcasting
evs  = job.result()[0].data.evs
```

Write the ansatz and observable on **logical** qubits and let the backend's
`auto_transpile` route them — do **not** pre-transpile (see gotchas below).

See [references/workflows.md](references/workflows.md) for complete runnable
patterns (counts, expectation values, QNN training, cross-vendor inference).

## Errors

All library errors derive from `qr.QuantumRouterError`: `ProviderNotFoundError`,
`BackendNotFoundError`, `ConnectionError`, `TimeoutError`, `ProtocolError`,
`TransportError`, `TransportNotImplementedError`. Catch the base class around
cloud calls — a network/auth failure is expected when running offline.

## Transports

The transport (wire layer) is inferred from the URL scheme by
`ConnectionConfig.from_url()`, so the calling code never changes:

- `http://` / `https://` → `HttpTransport`
- `pcie:///dev/quantum0` → `PcieTransport` (direct-to-hardware; currently a
  placeholder that raises `TransportNotImplementedError` — the API is fixed and
  will work unchanged once BAR mapping is implemented)

```python
provider = qr.create_provider(backend="lingyun", url="pcie:///dev/quantum0")
```

## Gotchas (hard-won — trust these)

- **Give logical circuits to Qiskit adapters; let the backend transpile.**
  Backends carry their real coupling map in their `Target` and map logical →
  physical internally (`auto_transpile=True` by default). Pre-transpiling by
  hand, or passing a circuit whose `.layout` is already set into `SamplerQNN`,
  is the usual cause of "runs locally, silent wrong answer on the device".
- **`SamplerQNN` wants a logical circuit** (`circuit.layout is None`), so it
  resolves counts by direct key lookup. Don't feed it backend-routed circuits.
- **Don't put `qiskit.primitives.StatevectorSampler` (or any local sampler) in
  place of `qr.Sampler`** — it shadows the import and the request never reaches
  the cloud.
- **Use `backend.run(...)`'s `auto_transpile`, not manual `transpile`** for
  real devices; if you must transpile, keep `optimization_level=1` (level ≥ 2's
  block consolidation can swallow entangling gates on `{h, cz, rz}` bases).
- **`RealAmplitudes` (class) is deprecated in Qiskit 2.1** — use the function
  `from qiskit.circuit.library import real_amplitudes`.
- **Counts keys cover only measured clbits** — idle qubits never appear in
  the key.
- Install vendor extras with quotes so the shell keeps the brackets:
  `pip install "quantumrouter[all]"`.
