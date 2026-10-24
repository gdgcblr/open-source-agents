import json
import sys
from governance import report

if __name__ == "__main__":
    result = report()
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(0 if result["overall"] == "PASS" else 1)
