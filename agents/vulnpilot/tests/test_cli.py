from main import main

def test_cli_mock_report(tmp_path):
    report = tmp_path / "report.md"
    code = main([str(tmp_path), "--mock", "--report", str(report)])
    assert code == 0 and report.exists()
    assert "VulnPilot Scan Report" in report.read_text()

def test_cli_mock_ai(tmp_path, capsys):
    code = main([str(tmp_path), "--mock", "--mock-ai"])
    assert code == 0
    assert "Offline mock analysis" in capsys.readouterr().out

def test_cli_invalid_path(tmp_path):
    assert main([str(tmp_path / "missing")]) == 2
