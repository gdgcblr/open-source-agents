import cli


def run(sample, extra=()):
    base = [f"--junit=samples/{sample}/junit.xml", f"--log=samples/{sample}/ci.log", "--mock"]
    return cli.main(base + list(extra))


def test_all_samples_run(capsys):
    assert run("flaky") == 0
    assert "FLAKY" in capsys.readouterr().out
    assert run("regression", ["--history=samples/regression/history.json"]) == 0
    assert "REGRESSION" in capsys.readouterr().out
    assert run("infra") == 0
    assert "INFRA" in capsys.readouterr().out
    assert run("unknown") == 0
    assert "UNKNOWN" in capsys.readouterr().out
