import json
from pathlib import Path

Path("report.json").write_text(json.dumps({"status": "complete", "items": ["example"]}))
print("Report created successfully")
