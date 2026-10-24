from governance import report


def test_offline_governance_harness_passes():
    result = report()
    assert result["overall"] == "PASS"
    assert result["summary"]["failed"] == 0
