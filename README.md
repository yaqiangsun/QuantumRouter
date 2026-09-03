<p align="center">
  <img src="assets/quantumrouter-logo.svg" alt="QuantumRouter logo" width="200">
</p>

<h1 align="center">QuantumRouter</h1>

<p align="center">
Unified interface for quantum cloud providers. One API, any backend.
</p>

<p align="center">
  <a href="https://pypi.org/project/quantumrouter/">
    <img src="https://img.shields.io/pypi/v/quantumrouter?style=flat-square&logo=pypi&logoColor=white" alt="PyPI version">
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/pypi/pyversions/quantumrouter?style=flat-square&logoColor=white&logo=python" alt="Python versions">
  </a>
  <a href="https://pypi.org/project/quantumrouter/">
    <img src="https://img.shields.io/pypi/dm/quantumrouter?style=flat-square&logo=pypi&logoColor=white" alt="PyPI Downloads">
  </a>
  <a href="https://github.com/yaqiangsun/QuantumRouter/issues">
    <img src="https://img.shields.io/github/issues/yaqiangsun/QuantumRouter?style=flat-square" alt="Issues">
  </a>
  <a href="https://github.com/yaqiangsun/QuantumRouter/commits/main">
    <img src="https://img.shields.io/github/last-commit/yaqiangsun/QuantumRouter?style=flat-square&logo=github" alt="Last Commit">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/yaqiangsun/QuantumRouter?style=flat-square" alt="License">
  </a>
  <img src="https://img.shields.io/badge/Quantum-Computing-blue?style=flat-square&logo=ibm" alt="Quantum Computing">
  <br>
  <a href="#quick-start">Quick start</a> •
  <a href="#examples">Examples</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#adding-a-vendor">Adding a vendor</a> •
  <a href="#license">License</a>
</p>

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

## Adding a vendor

Drop a `quantumrouter/providers/<vendor>/` subpackage that self-registers
via `ProviderRegistry.register(...)`. The transport and backend layers
stay untouched.

## License

[LICENSE](LICENSE)
