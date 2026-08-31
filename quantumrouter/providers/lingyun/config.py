"""Endpoint paths for the LingYun quantum service.

Kept as constants in one place so the xx.xx.xx.xx simulation
server and qc.zdxlz.com cloud can be swapped without editing client
methods.
"""

from __future__ import annotations

# Backend listing (filters by user token)
BACKENDS = "/qccp-quantum/experiments/quantum/computer/by/user"

# Per-computer configuration overview
COMPUTER_CONFIG = "/qccp-quantum/experiments/quantum/computer/config"

# Physical machine calibration download
MACHINE_CONFIG = "/qccp-quantum/sdk/experiment/download/config"

# Experiment submission
SUBMIT = "/qccp-quantum/sdk/experiment/submit"

# Experiment result query
QUERY_RESULT = "/qccp-quantum/sdk/experiment/result/find"
