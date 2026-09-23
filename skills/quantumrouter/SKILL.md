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

One vendor-agnostic interface to many quantum clouds: switch vendors by changing
one parameter, the calling code stays identical.

```bash
pip install quantumrouter           # Python >= 3.10; core deps: qiskit, requests
pip install "quantumrouter[all]"    # add every vendor extra
```

## Entry point

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

| id | Typical backend name | Extra install |
|---|---|---|
| `local` | `local_simulator` | — |
| `lingyun` | `lingyun_001` | `quantumrouter[lingyun]` |
| `tianyan` | `tianyan_sw` | `quantumrouter[tianyan]` |
| `wuyue` | `WuYue-QPUSim-FullAmpSim` | — |
| `quafu` | `ScQ-Sim10` | — |
| `lqcloud` | `MQ02` (real 24-qubit) | — |
| `ibm` | — | `quantumrouter[ibm]` |

- Pass credentials explicitly: `create_provider(backend=..., token=..., url=...)`.
  (IBM is the one exception — it falls back to the `IBM_QUANTUM_TOKEN`
  environment variable when `token=` is omitted.)

- `local` runs offline on Qiskit's `BasicSimulator` — no token, URL, or server.
  Try the whole API with it: `qr.create_provider("local")` (optional
  `n_qubits=16`).
- Backend *names* above are typical — confirm with `provider.backends(online=True)`.
- `quafu` / `lqcloud` have fixed cloud addresses (no `url`); `lqcloud`'s `MQ02`
  is a **real** pay-per-job chip — keep shots low when testing.
- Install extras with quotes: `pip install "quantumrouter[all]"`.

## Run a circuit

```python
from qiskit import QuantumCircuit

qc = QuantumCircuit(2, 2)
qc.h(0); qc.cx(0, 1); qc.measure([0, 1], [0, 1])

job    = backend.run(run_input=[qc], shots=1024)   # a qc or a list[qc]
counts = job.result().get_counts()                 # {'00': ..., '11': ...}
```

**Always pass Qiskit `QuantumCircuit` objects — never a vendor circuit string.**
Each backend serializes the circuit to its own wire format internally. `run()`
also takes `readout_calibration=` and `auto_transpile=` (both default `True`;
`auto_transpile` moves transpilation to the backend, which knows its own
coupling map). `run()` is a `BackendV2.run`, so `transpile(qc, backend=backend)`
and Qiskit's adapters work on it directly.

Handy backend attributes: `backend.name`, `.is_simulator`, `.num_qubits`,
`.target` (qiskit Target / coupling map), `.configuration.coupling_map`,
`.fetch_configuration()` (raw calibration dict).

## Sampler

`qr.Sampler` is a Qiskit `BackendSamplerV2` adapter — `qiskit-machine-learning`
can use a QuantumRouter backend like any Qiskit backend.

```python
circuit = ...                       # must contain measurements
circuit.measure_all()               # adds a classical register named "meas"

sampler = qr.Sampler(backend, default_shots=4096)
result = sampler.run([(circuit, params)]).result()   # PUBs must be in a list
counts = result[0].data.meas.get_counts()            # register name, not get_counts()
```

The circuit **must** have measurement instructions — the sampler adds none. The
classical register's name selects the accessor (`measure_all()` → `.data.meas`;
`QuantumRegister("c", ...)` → `.data.c`). Pass run options via
`options={"run_options": {...}}` or per call.

## Estimator — there is NO `qr.Estimator`

Wrap the backend in Qiskit's generic adapter:

```python
from qiskit.primitives import BackendEstimatorV2

estimator = BackendEstimatorV2(backend=backend,
                               options={"default_precision": 0.015625})
evs = estimator.run([(ansatz, observable, thetas)]).result()[0].data.evs
```

`default_precision` maps to `shots = ceil(1 / precision**2)`.

See [references/workflows.md](references/workflows.md) for runnable patterns
(counts, expectation values, QNN training, cross-vendor inference).

## Gotchas

- **Give logical circuits to Qiskit adapters; let the backend transpile**
  (`auto_transpile=True`). Pre-transpiling by hand, or feeding `SamplerQNN` a
  circuit with `.layout` already set, is the usual cause of "runs locally,
  silent wrong answer on the device".
- **Don't swap in `qiskit.primitives.StatevectorSampler`** (or any local
  sampler) for `qr.Sampler` — the request never reaches the cloud.
- If you must transpile yourself for a real device, keep
  `optimization_level=1` (level ≥ 2 can swallow entangling gates on `{h, cz,
  rz}` bases).
- **`RealAmplitudes` (class) is deprecated in Qiskit 2.1** — use the function
  `from qiskit.circuit.library import real_amplitudes`.
- Counts keys cover only measured clbits — idle qubits never appear.
- Catch `qr.QuantumRouterError` around cloud calls; a network/auth failure is
  expected when running offline.
