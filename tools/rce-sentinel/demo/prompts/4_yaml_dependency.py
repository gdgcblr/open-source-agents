import yaml
from flask import request


def load_config():
    return yaml.load(request.data, Loader=yaml.FullLoader)
