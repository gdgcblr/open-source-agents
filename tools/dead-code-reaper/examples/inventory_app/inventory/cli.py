"""Command-line entry point (installed as `inventory`)."""
import json
import sys

from .encoding import DecimalEncoder
from .exporters import export
from .pricing import apply_discount, calculate_tax, price_for
from .reports import build_report
from .sample_data import make_sample_warehouse


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "summary"
    wh = make_sample_warehouse()
    if command == "export":
        print(export(wh, argv[1] if len(argv) > 1 else "json"))
    elif command == "quote":
        subtotal = sum(price_for(i) * i.qty for i in wh.items)
        net = apply_discount(subtotal, float(argv[1]) if len(argv) > 1 else 0)
        print(json.dumps({"net": net, "tax": calculate_tax(net)}, cls=DecimalEncoder))
    else:
        print(build_report(command, wh))
    return 0
