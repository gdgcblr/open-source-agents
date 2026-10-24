"""Reports, registered by name."""
REGISTRY = {}

SHOW_BETA_REPORTS = False


def register(name):
    def wrap(fn):
        REGISTRY[name] = fn
        return fn
    return wrap


@register("summary")
def summary_report(warehouse) -> str:
    total = sum(i.total_value() for i in warehouse.items)
    return f"{len(warehouse.items)} items, total value {total:.2f}"


def build_report(name: str, warehouse) -> str:
    return REGISTRY[name](warehouse)


def old_summary_v2(warehouse) -> str:
    lines = [f"{i.name}: {i.qty}" for i in warehouse.items]
    return "\n".join(lines)


class LegacyCsvExporter:
    def __init__(self, warehouse):
        self.warehouse = warehouse

    def export(self) -> str:
        return "\n".join(f"{i.name},{i.qty}" for i in self.warehouse.items)


if False:
    # Beta reports, switched off since 2023.
    REGISTRY["beta"] = old_summary_v2
