# QuantumRouter workflows

Runnable patterns. Every snippet works against **any** vendor — only the
`create_provider(backend=..., url=..., token=...)` arguments change.

## 0. Offline: the local simulator

No token, no URL, no server — the fastest way to exercise the API.

```python
import quantumrouter as qr

provider = qr.create_provider("local")           # id-only is fine for local
backend  = provider.backend("local_simulator")
```

## 1. Measurement counts (`backend.run`)

```python
import quantumrouter as qr
from qiskit import QuantumCircuit

provider = qr.create_provider("lingyun", url="http://127.0.0.1:8000",
                              token="...")
backend  = provider.backend("lingyun_001")

qc = QuantumCircuit(2, 2)
qc.h(0); qc.cx(0, 1); qc.measure([0, 1], [0, 1])

job    = backend.run(run_input=[qc], shots=1024)
counts = job.result().get_counts()   # {'00': ..., '11': ...}
```

`run()` takes a `QuantumCircuit` or a `list[QuantumCircuit]`; a *list* is the
recommended form (matches the publisher/batch contract across vendors).

## 2. Expectation values (Estimator)

The package has **no** `qr.Estimator`. Wrap the backend in Qiskit's generic
`BackendEstimatorV2` (the same adapter `qr.Sampler` builds on).

```python
import quantumrouter as qr
from qiskit.circuit.library import real_amplitudes
from qiskit.primitives import BackendEstimatorV2
from qiskit.quantum_info import SparsePauliOp

backend = qr.create_provider("local").backend("local_simulator")

ansatz = real_amplitudes(num_qubits=2, reps=2)      # logical qubits, no transpile
observable = SparsePauliOp.from_list([("II", 1), ("IZ", 2), ("XI", 3)])
thetas = [[0, 1, 1, 2, 3, 5], [1, 0, 2, 1, 4, 2]]   # broadcasting: one job, many θ

estimator = BackendEstimatorV2(backend=backend,
                               options={"default_precision": 0.015625})
pub_result = estimator.run([(ansatz, observable, thetas)]).result()[0]
print(pub_result.data.evs, pub_result.data.stds)
```

`default_precision` maps to `shots = ceil(1 / precision**2)`. Use a coarser
precision (fewer shots) on pay-per-shot real QPUs such as `lqcloud`'s `MQ02`.

## 3. Sampling through `qr.Sampler`

```python
import quantumrouter as qr
from qiskit.circuit.library import real_amplitudes

backend = qr.create_provider("local").backend("local_simulator")
sampler = qr.Sampler(backend, default_shots=4096,
                     options={"run_options": {"readout_calibration": False}})

circuit = real_amplitudes(num_qubits=2, reps=1)
circuit.measure_all()                  # REQUIRED: the sampler adds no measurements
params  = [0.1, 0.2, 0.3, 0.4]
result  = sampler.run([(circuit, params)]).result()   # PUBs in a LIST
counts  = result[0].data.meas.get_counts()            # note .data.<creg>
```

The result accessor follows the circuit's classical-register name:
`measure_all()` gives `.data.meas`; an explicit `QuantumRegister("c", 2)` gives
`.data.c`. `SamplerPubResult` has no `get_counts()` of its own.

Per-call overrides beat constructor options:

```python
sampler.run([(circuit, params)], shots=2048, auto_transpile=True)
```

## 4. Training a QNN (`qiskit-machine-learning`)

Requires `pip install qiskit-machine-learning`. Runs on the QuantumRouter
backend — **not** a local statevector sim.

```python
import numpy as np
import quantumrouter as qr
from qiskit_machine_learning.circuit.library import qnn_circuit
from qiskit_machine_learning.neural_networks import SamplerQNN
from qiskit_machine_learning.algorithms.classifiers import NeuralNetworkClassifier
from qiskit_machine_learning.optimizers import COBYLA
from qiskit.circuit.library import real_amplitudes

backend = qr.create_provider("local").backend("local_simulator")
sampler = qr.Sampler(backend)

circuit, input_params, weight_params = qnn_circuit(
    ansatz=real_amplitudes(2, reps=1)          # LOGICAL circuit (layout is None)
)

def parity(bitstring: int) -> int:             # map measured int -> class label
    return f"{bitstring:b}".count("1") % 2

qnn = SamplerQNN(circuit=circuit, input_params=input_params,
                 weight_params=weight_params,
                 interpret=parity, output_shape=2, sampler=sampler)

clf = NeuralNetworkClassifier(neural_network=qnn, optimizer=COBYLA(maxiter=30),
                              callback=lambda w, v: print(f"obj: {v:.6f}"))
X = 2 * np.random.random((8, 2)) - 1
y = 1 * (np.sum(X, axis=1) >= 0)
clf.fit(X, y)
print(clf.score(X, y), clf.weights)
```

**Critical**: pass the *logical* circuit (no `transpile`, no `initial_layout`,
`circuit.layout is None`). The backend side maps logical → physical from its own
`Target`. If `SamplerQNN` sees a non-None `layout`, it reverse-maps counts
through the layout and silently produces wrong values.

## 5. Cross-vendor inference

A trained model is just a vector of weights — portable across clouds.

```python
train_backend = qr.create_provider("lingyun", url=..., token=...).backend("lingyun_001")
infer_backend = qr.create_provider("tianyan", token=...).backend("tianyan_sw")

# train with qr.Sampler(train_backend) ... then reuse `circuit` and `clf.weights`
infer_sampler = qr.Sampler(infer_backend)
infer_qnn = SamplerQNN(circuit=circuit.copy(), input_params=input_params,
                       weight_params=weight_params, interpret=parity,
                       output_shape=2, sampler=infer_sampler)
probs = infer_qnn.forward(X, clf.weights)
```

## 6. Hardware metadata (no submission)

Read the device's shape without running anything:

```python
backend.target                       # qiskit Target: coupling map + gate errors
backend.configuration.coupling_map   # [ [0,1], [1,2], ... ]
config = backend.fetch_configuration()   # full hardware/calibration dict
```

`submit_job` / `query_job` still exist for vendor-string access, but they take
the **vendor's** circuit format, not a Qiskit circuit — don't reach for them.
Submit through `backend.run(...)` (or `qr.Sampler` / `BackendEstimatorV2`) with
a `QuantumCircuit` and the backend serializes it for you.

## 7. Env-driven vendor switch

Read connection details from the environment (`.env`), so switching a vendor is
a change to env vars rather than code:

```python
import os
from dotenv import load_dotenv
import quantumrouter as qr

load_dotenv()
provider = qr.create_provider(
    backend="lingyun",
    url=os.environ.get("LINGYUN_URL") or "http://127.0.0.1:8000",
    token=os.environ.get("LINGYUN_TOKEN") or None,
)
```
