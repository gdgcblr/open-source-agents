import os

# Keep LiteLLM offline: by default it downloads a model price list from GitHub at import.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from . import agent  # noqa: E402
