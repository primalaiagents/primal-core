"""Built-in policies for Guardian — six concrete policies + DSL registration.

Importing this module registers every built-in's DSL name with the
parser in :mod:`primal_ai.guardian._dsl`. The classes are also
re-exported here for direct use:

    from primal_ai.guardian._builtins import RateLimit, DollarCap, ...
"""

from __future__ import annotations

from primal_ai.guardian._builtins.allow_list import AllowList
from primal_ai.guardian._builtins.allow_list import factory as _allow_list_factory
from primal_ai.guardian._builtins.block_list import BlockList
from primal_ai.guardian._builtins.block_list import factory as _block_list_factory
from primal_ai.guardian._builtins.block_list import (
    no_external_network_factory as _no_external_network_factory,
)
from primal_ai.guardian._builtins.dollar_cap import DollarCap
from primal_ai.guardian._builtins.dollar_cap import factory as _dollar_cap_factory
from primal_ai.guardian._builtins.pii_redact import PIIRedact
from primal_ai.guardian._builtins.pii_redact import factory as _pii_redact_factory
from primal_ai.guardian._builtins.rate_limit import RateLimit
from primal_ai.guardian._builtins.rate_limit import factory as _rate_limit_factory
from primal_ai.guardian._builtins.schema_validator import SchemaValidator
from primal_ai.guardian._builtins.schema_validator import factory as _schema_factory
from primal_ai.guardian._dsl import register_policy

# Wire DSL names → factories. Names match the public, README-friendly forms.
register_policy("rate_limit", _rate_limit_factory)
register_policy("max_cost", _dollar_cap_factory)
register_policy("allow_list", _allow_list_factory)
register_policy("block_list", _block_list_factory)
register_policy("schema", _schema_factory)
register_policy("pii_redact", _pii_redact_factory)
register_policy("no_external_network", _no_external_network_factory)

__all__ = [
    "AllowList",
    "BlockList",
    "DollarCap",
    "PIIRedact",
    "RateLimit",
    "SchemaValidator",
]
