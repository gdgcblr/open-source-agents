import sys
from pathlib import Path

from murphy.proxy.server import build_proxy

if len(sys.argv) != 2:
    raise SystemExit("usage: python -m murphy.proxy <run_dir>")
build_proxy(Path(sys.argv[1]).resolve()).run(show_banner=False)
