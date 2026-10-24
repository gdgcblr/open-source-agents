"""Enable ``python -m src "<task>"``."""

import sys

from .agent import main

sys.exit(main())
