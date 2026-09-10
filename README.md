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
    <img src="https://img.shields.io/pypi/dm/quantumrouter?style=flat-square&logo=pypi" alt="PyPI Downloads">
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
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick start</a> •
  <a href="#examples">Examples</a> •
  <a href="#adding-a-vendor">Adding a vendor</a> •
  <a href="#license">License</a>
</p>

## Introduction

QuantumRouter is a Python library that provides a **unified interface** to
multiple quantum cloud providers. Switching from one vendor (LingYun, IBM
Quantum, TianYan, WuYue, ...) to another is a one-line change — the calling
code stays identical.

The library exposes a vendor-agnostic `Provider` / `Backend` / `Transport`
abstraction. Each concrete vendor lives under
`quantumrouter/providers/<vendor>/` and self-registers with a process-wide
registry on import. Vendor subpackages are imported **lazily**, so installing
one vendor never forces you to install another's dependencies.

## Installation

### From PyPI (recommended)

```bash
pip install quantumrouter
```

This installs the core package plus its base dependencies
(`qiskit`, `requests`). Vendor-specific third-party dependencies are **not**
pulled in by default — install the extras you need:

```bash
pip install "quantumrouter[lingyun]"   # LingYun deps only (numpy)
pip install "quantumrouter[ibm]"       # IBM Quantum deps (qiskit-ibm-provider)
pip install "quantumrouter[tianyan]"   # TianYan deps (cqlib-adapter)
pip install "quantumrouter[wuyue]"     # WuYue deps (wuyue)

pip install "quantumrouter[all]"       # every vendor's deps at once
```

Multiple extras can be combined, e.g. `pip install "quantumrouter[lingyun,ibm]"`.

> **Note** — quote the extras argument (`"quantumrouter[all]"`) so your shell
> doesn't interpret the brackets.



## Quick start

```python
import quantumrouter

provider = quantumrouter.create_provider(
    backend="lingyun",                   # change this to switch vendors
    url="http://xx.xxxx.xx:8000",        # cloud / simulation server
    token="...",                         # optional for the simulation server
)

backends = provider.backends(online=True)
backend = backends[0]

task_ids = backend.submit_job(["QINIT 4\nH 0"], shots=1024)
results  = backend.query_job(task_ids)
config   = backend.fetch_configuration()
```

Use `backend.run(...)` instead of `submit_job(...)` to build a quantum circuit
with qiskit, run it, and fetch a `Result` object (including measurement
counts) in one call — see `examples/basic_usage.py`.

The same entry point selects a **PCIe transport** when the URL scheme is
`pcie://` — the calling code does not change:

```python
provider = quantumrouter.create_provider(
    backend="lingyun",
    url="pcie:///dev/quantum0",
)
```

## Examples

The `examples/` directory contains runnable, vendor-specific demos:

| Example | Vendor | What it shows |
|---|---|---|
| [basic_usage_lingyun.py](examples/basic_usage_lingyun.py) | LingYun | LingYun-specific flow |
| [basic_usage_tianyan.py](examples/basic_usage_tianyan.py) | TianYan | TianYan-specific flow with transpile |
| [basic_usage_wuyue.py](examples/basic_usage_wuyue.py) | WuYue | WuYue mobile cloud flow |
| [multi_vendor.py](examples/multi_vendor.py) | LingYun + IBM | switch vendors with one parameter |
| [pcie_transport.py](examples/pcie_transport.py) | LingYun | select a PCIe transport via URL scheme |

Run any of them with, for example:

```bash
python examples/basic_usage.py
```

Most examples accept connection details from environment variables
(`LINGYUN_TOKEN`, `LINGYUN_URL`, `IBM_QUANTUM_TOKEN`, ...) — set the ones you
need before running.

## Architecture

```
quantumrouter/
├── transport/                  # generic wire layer (HTTP, PCIe, …)
├── backend/                    # generic backend contract
├── provider/                   # Provider abstract base + registry + factory
└── providers/                  # one subpackage per cloud vendor
    ├── base.py / registry.py   #   shared abstraction + registry
    ├── __init__.py             #   lazy __getattr__ for vendor subpackages
    ├── ibm/                    #   IBM Quantum (qiskit-ibm-provider)
    ├── lingyun/                #   LingYun — HTTP / PCIe, QCIS & OpenQASM3
    ├── tianyan/                #   TianYan — cqlib-adapter
    └── wuyue/                  #   WuYue — wuyue SDK
```

Three layers, top-down:

- **Transport** (`transport/`) — owns the wire bytes. HTTP and PCIe
  implementations live here behind a common `Transport` interface.
- **Backend** (`backend/`) — wraps one quantum computer or simulator. Exposes
  the operations users care about: listing, submitting, querying, fetching
  calibration.
- **Provider** (`provider/`) — the per-vendor entry point. Builds a transport
  from a `ConnectionConfig`, hands it to a transport-backed client, and lists
  backends.

A single factory, `create_provider(backend=..., url=..., token=...)`, ties the
layers together. The transport type (HTTP or PCIe) is inferred from the URL
scheme via `ConnectionConfig.from_url()`.

## Adding a vendor

1. Create `quantumrouter/providers/<vendor>/` with:
   - `provider.py` — a `Provider` subclass implementing `backends()` and
     `backend(name)`, self-registering with
     `ProviderRegistry.register(<YourProvider>)` at import time.
   - `client.py` — a transport-backed API client for the vendor's REST surface.
   - `backend/` — `Backend` subclasses binding the generic contract to the
     vendor's response format.
2. Add the vendor id to `_VENDOR_PACKAGES` in
   `quantumrouter/providers/__init__.py` so the lazy `__getattr__` picks it up.
3. Add an optional-dependencies group (e.g. `[<vendor>]`) in `pyproject.toml`
   for the vendor's third-party deps, and include it in the `[all]` aggregate.

Vendor packages self-register once their subpackage is imported, which the
registry triggers automatically the first time
`create_provider("<vendor>", ...)` is called. Use only the vendors you have
deps for; the others stay unloaded.

## License

[LICENSE](LICENSE)
