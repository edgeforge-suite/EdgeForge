"""Keep assertion-based Batch evidence invalidation effective in every caller."""

import sys


def require_unoptimized_python():
    if sys.flags.optimize != 0:
        raise RuntimeError(
            "Batch proof requires unoptimized Python: remove -O/-OO and disable "
            "effective PYTHONOPTIMIZE before generating apps or touching services/databases."
        )


require_unoptimized_python()
