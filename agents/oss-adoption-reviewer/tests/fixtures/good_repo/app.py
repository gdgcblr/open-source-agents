import os

def greet(name):
    return os.environ.get("GREETING", "Hi") + ", " + name
