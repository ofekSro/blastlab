"""The old import path of the remap-chain helpers, which live in
`services/chain.py` since Phase 3 of docs/ARCHITECTURE_REVIEW.md. Every
name is re-exported as the same object, so `gui/chain_panel.py`,
`ui/chain_panel.py` and `solvers/foam/writer.py` keep importing it
here."""

# services/chain.py has no underscore names, so `*` covers all of it
from ..services.chain import *                  # noqa: F401,F403
