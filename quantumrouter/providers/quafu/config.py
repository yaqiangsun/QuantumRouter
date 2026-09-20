"""Endpoint paths for the Quafu quantum service.

Mirrors the upstream ``quafu/users/userapi.py`` constants (see
``tmp/pyquafu-master/``) so the same server can be reached without
importing the upstream package. All paths are relative to
:data:`BASE_URL`; the API is token-authenticated via the ``api_token``
form header (see :mod:`quantumrouter.providers.quafu.client`).
"""

from __future__ import annotations

# Official Quafu cloud base URL.
BASE_URL = "https://quafu.baqis.ac.cn/"

# List backends visible to the current token.
BACKENDS = "qbackend/get_backends/"

# Submit a circuit for asynchronous execution (returns a task id).
EXEC_ASYNC = "qbackend/scq_kit_asyc/"

# Recall the result of a previously submitted task id.
EXEC_RECALL = "qbackend/scq_task_recall/"
