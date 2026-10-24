"""pytest plugin for projects that use this package.

Other projects enable it with `-p inventory.testing`.
"""


def pytest_report_header(config):
    return "inventory test helpers enabled"
