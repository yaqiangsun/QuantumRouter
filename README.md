# QuantumRouter

Unified interface for quantum cloud providers. One API, any backend.

Switching cloud vendors is a one-parameter change — the calling code
stays identical.

## Quick start

```python
import quantumrouter

provider = quantumrouter.create_provider(
    backend="lingyun",                     # change this to switch vendors
    url="http://xx.xxxx.xx:xxxx",       # cloud / simulation server
    token="...",                           # optional for the simulation server
)

backends = provider.backends(online=True)
backend = backends[0]

task_ids = backend.submit_job(["QINIT 4\nH 0"], shots=1024)
results  = backend.query_job(task_ids)
config   = backend.fetch_configuration()
```

PCIe-direct (same entry point, different URL scheme):

```python
provider = quantumrouter.create_provider(
    backend="lingyun",
    url="pcie:///dev/quantum0",
)
```

## Examples

- `examples/basic_usage.py` — list backends, submit a job, query results.
- `examples/multi_vendor.py` — switch between LingYun and IBM Quantum
  with a single parameter.
- `examples/pcie_transport.py` — use a PCIe transport instead of HTTP.

Run with:

```
python examples/basic_usage.py
```

## Architecture

```
quantumrouter/
├── transport/                  # generic wire layer (HTTP, PCIe, …)
├── backend/                    # generic backend contract
└── providers/                  # one subdir per cloud vendor
    ├── base.py / registry.py   #   shared abstraction + registry
    └── lingyun/                #   LingYun (凌云), self-contained
```

Adding a vendor: drop a `quantumrouter/providers/<vendor>/` subpackage
that self-registers via `ProviderRegistry.register(...)`. The
transport and backend layers stay untouched.
