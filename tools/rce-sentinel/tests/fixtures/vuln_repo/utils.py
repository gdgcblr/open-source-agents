import subprocess


def run_cmd(task):
    return subprocess.run(task, shell=True, capture_output=True).stdout
