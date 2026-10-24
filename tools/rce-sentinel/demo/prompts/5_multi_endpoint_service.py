"""A small internal admin API. Five endpoints, five different RCE patterns."""
import os
import pickle
import subprocess

import yaml
from flask import Flask, request

app = Flask(__name__)


@app.route("/ping")
def ping():
    host = request.args.get("host", "")
    os.system("ping -c 1 " + host)
    return "ok"


@app.route("/backup", methods=["POST"])
def backup():
    target = request.json["target"]
    subprocess.run(f"tar czf /backups/{target}.tgz /data", shell=True)
    return "started"


@app.route("/restore", methods=["POST"])
def restore():
    state = pickle.loads(request.data)
    return str(state)


@app.route("/calc")
def calc():
    return str(eval(request.args["expr"]))


@app.route("/config", methods=["POST"])
def config():
    return yaml.load(request.data, Loader=yaml.FullLoader)
