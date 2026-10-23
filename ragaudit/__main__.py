# -*- coding: utf-8 -*-
"""允许 `python -m ragaudit`。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
