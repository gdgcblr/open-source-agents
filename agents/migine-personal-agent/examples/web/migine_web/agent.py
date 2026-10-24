"""Expose the existing agent to ADK Web. No app reads occur during import."""

import os

from migine.adapters import adapter_for
from migine.agent import build_agent
from migine.config import Settings
from migine.storage import Store

os.umask(0o077)
os.environ["LITELLM_TELEMETRY"] = "False"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["OTEL_SDK_DISABLED"] = "true"

settings = Settings.load()
root_agent = build_agent(settings, Store(settings.data_dir), adapter_for(settings))
