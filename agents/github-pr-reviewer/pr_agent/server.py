import http.server
import json
import os
import urllib.parse
from .reviewer import PRReviewerAgent
from .github_client import load_diff_from_file, fetch_pr_diff
from .html_reporter import generate_html_dashboard


HTML_FORM_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous PR Reviewer Council</title>
    <style>
        :root {
            --bg: #0f172a; --card: #1e293b; --text: #f8fafc;
            --muted: #94a3b8; --accent: #6366f1; --border: #334155;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg); color: var(--text); padding: 30px;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        header { margin-bottom: 24px; text-align: center; }
        h1 { font-size: 28px; font-weight: 800; margin-bottom: 8px; color: #fff; }
        p.subtitle { color: var(--muted); font-size: 15px; }
        .card {
            background: var(--card); border: 1px solid var(--border);
            border-radius: 12px; padding: 24px; margin-bottom: 24px;
        }
        label { display: block; font-weight: 600; margin-bottom: 8px; font-size: 14px; }
        input[type="text"], textarea {
            width: 100%; background: #0f172a; border: 1px solid var(--border);
            border-radius: 8px; color: #f8fafc; padding: 12px; font-family: monospace;
            font-size: 13px; margin-bottom: 16px;
        }
        textarea { height: 200px; resize: vertical; }
        .btn-row { display: flex; gap: 12px; flex-wrap: wrap; }
        button {
            background: var(--accent); color: #fff; border: none;
            padding: 10px 20px; border-radius: 8px; font-weight: 700;
            cursor: pointer; font-size: 14px;
        }
        button.secondary { background: #334155; }
        button:hover { opacity: 0.9; }
        #results-container { margin-top: 30px; }
        iframe {
            width: 100%; height: 800px; border: 1px solid var(--border);
            border-radius: 12px; background: #0f172a;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏛️ Autonomous PR Reviewer & Triage Council</h1>
            <p class="subtitle">Multi-agent security audit, performance analysis, automated test synthesis, and self-healing patches.</p>
        </header>

        <div class="card">
            <label for="pr-url">Option A: GitHub PR URL or Slug</label>
            <input type="text" id="pr-url" placeholder="https://github.com/owner/repo/pull/123 or owner/repo#123" />

            <label for="diff-text">Option B: Unified Git Diff / Patch</label>
            <textarea id="diff-text" placeholder="Paste git diff here..."></textarea>

            <div class="btn-row">
                <button onclick="analyze()">🚀 Run Council Review</button>
                <button class="secondary" onclick="loadSample('vulnerable')">Load Insecure Sample Diff</button>
                <button class="secondary" onclick="loadSample('clean')">Load Clean Bug Fix Diff</button>
            </div>
        </div>

        <div id="results-container" style="display: none;">
            <iframe id="results-frame"></iframe>
        </div>
    </div>

    <script>
        async function loadSample(type) {
            const resp = await fetch('/api/sample?type=' + type);
            const data = await resp.json();
            document.getElementById('diff-text').value = data.diff;
            document.getElementById('pr-url').value = '';
        }

        async function analyze() {
            const pr = document.getElementById('pr-url').value;
            const diff = document.getElementById('diff-text').value;

            document.getElementById('results-container').style.display = 'block';
            const frame = document.getElementById('results-frame');
            frame.srcdoc = '<p style="color:white;padding:20px;font-family:sans-serif;">⏳ The Multi-Agent Council is auditing your code changes...</p>';

            const resp = await fetch('/api/review', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pr: pr, diff: diff })
            });
            const html = await resp.text();
            frame.srcdoc = html;
        }
    </script>
</body>
</html>
"""


class PRReviewHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = os.path.normpath(parsed.path)
        if ".." in parsed.path or clean_path.startswith("..") or "\0" in self.path:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid path.")
            return

        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_FORM_PAGE.encode("utf-8"))
        elif parsed.path == "/api/sample":
            query = urllib.parse.parse_qs(parsed.query)
            sample_type = query.get("type", ["vulnerable"])[0]
            if sample_type not in ("vulnerable", "clean"):
                sample_type = "vulnerable"
            samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples")
            sample_file = "sample_pr_diff.patch" if sample_type == "vulnerable" else "sample_bug_fix.patch"
            diff_text, _ = load_diff_from_file(os.path.join(samples_dir, sample_file))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"diff": diff_text}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/review":
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self.send_response(400)
                self.end_headers()
                return

            # Security limit: max 5MB upload size to prevent memory exhaustion DoS
            if length > 5 * 1024 * 1024:
                self.send_response(413)
                self.end_headers()
                self.wfile.write(b"Payload Too Large: Max size is 5MB.")
                return

            try:
                body = self.rfile.read(length).decode("utf-8", errors="replace")
                data = json.loads(body)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Malformed JSON: {e}".encode("utf-8"))
                return

            diff_text = data.get("diff", "")
            pr_url = data.get("pr", "")
            source_title = "Web Submission"

            if pr_url:
                try:
                    diff_text, source_title = fetch_pr_diff(pr_url)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Error fetching PR: {e}".encode("utf-8"))
                    return

            if not diff_text.strip():
                # Default to sample diff if empty
                samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples")
                diff_text, _ = load_diff_from_file(os.path.join(samples_dir, "sample_pr_diff.patch"))
                source_title = "Bundled Sample Diff"

            agent = PRReviewerAgent(offline=True)
            report = agent.analyze(diff_text, source_title)
            html = generate_html_dashboard(report)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def start_server(port: int = 8080):
    """Start local zero-dependency interactive dashboard server with port collision fallback."""
    from .exceptions import ServerPortError
    server_address = ("", port)
    try:
        httpd = http.server.HTTPServer(server_address, PRReviewHandler)
    except OSError as e:
        if getattr(e, "errno", None) in (48, 98):  # Address already in use (macOS 48, Linux 98)
            alt_port = port + 1
            print(f"⚠️ Port {port} is already in use. Trying alternative port {alt_port}...")
            try:
                httpd = http.server.HTTPServer(("", alt_port), PRReviewHandler)
                port = alt_port
            except OSError:
                raise ServerPortError(
                    f"Port {port} and {alt_port} are currently in use by another process.",
                    tip="Specify an unused port: python main.py --serve 9000."
                )
        else:
            raise ServerPortError(f"Failed to bind web server to port {port}: {e}")

    print(f"\n🚀 Interactive PR Reviewer Council Server running at: http://localhost:{port}")
    print("Press Ctrl+C to terminate.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server cleanly.")
        httpd.server_close()
