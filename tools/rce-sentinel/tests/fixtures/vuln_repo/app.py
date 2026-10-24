"""Intentionally vulnerable demo app. Do not deploy."""
import os

import yaml
from flask import Flask, request

from utils import run_cmd

app = Flask(__name__)


@app.route("/ping")
def ping():
    host = request.args.get("host", "")
    cmd = f"ping -c 1 {host}"
    os.system(cmd)
    return "ok"


@app.route("/config", methods=["POST"])
def load_config():
    cfg = yaml.load(request.data, Loader=yaml.FullLoader)
    return str(cfg)


@app.route("/run")
def run():
    return run_cmd(request.args["task"])


def disk_usage():
    os.system("df -h")
