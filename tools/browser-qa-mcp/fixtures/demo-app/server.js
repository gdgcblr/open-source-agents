// A tiny, dependency-free demo signup app used as a fixture for the browser
// QA agent's example test plan. It contains ONE deliberate bug (see
// isValidEmail below) so the example run demonstrates a real, detected
// application defect rather than only passing tests.
const http = require("http");
const { URL } = require("url");

const PORT = Number(process.env.PORT || 4000);

function isValidEmail(email) {
  // BUG: only checks a minimum length, never that the value actually looks
  // like an email address (no "@", no domain). A correct implementation
  // would require something like /^[^\s@]+@[^\s@]+\.[^\s@]+$/.
  return typeof email === "string" && email.trim().length > 3;
}

const INDEX_HTML = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><title>Demo App</title></head>
<body>
  <h1>Demo App</h1>
  <p><a href="/signup">Go to signup</a></p>
</body>
</html>`;

const SIGNUP_HTML = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><title>Sign up</title></head>
<body>
  <h1>Create your account</h1>
  <form id="signup-form">
    <label>Name <input name="name" type="text" /></label>
    <label>Email <input name="email" type="text" /></label>
    <label>Password <input name="password" type="password" /></label>
    <button type="submit">Sign up</button>
  </form>
  <div id="result" aria-live="polite"></div>
  <script>
    var form = document.getElementById("signup-form");
    var result = document.getElementById("result");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      result.innerHTML = "";
      var data = Object.fromEntries(new FormData(form).entries());
      fetch("/api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
        .then(function (res) { return res.json(); })
        .then(function (body) {
          if (body.success) {
            result.innerHTML =
              '<div id="signup-success">Welcome, ' + body.name + '! Your account was created.</div>';
          } else {
            result.innerHTML = '<div role="alert" id="signup-error">' + body.errors.join(", ") + "</div>";
          }
        });
    });
  </script>
</body>
</html>`;

function send(res, status, headers, body) {
  res.writeHead(status, headers);
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (chunk) => { data += chunk; });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);

  if (req.method === "GET" && url.pathname === "/") {
    return send(res, 200, { "Content-Type": "text/html" }, INDEX_HTML);
  }

  if (req.method === "GET" && url.pathname === "/signup") {
    return send(res, 200, { "Content-Type": "text/html" }, SIGNUP_HTML);
  }

  if (req.method === "GET" && url.pathname === "/favicon.ico") {
    // Avoids a spurious 404 console error on every page load that has
    // nothing to do with the application under test, which would otherwise
    // show up as noise in every run's captured evidence.
    return send(res, 204, {}, "");
  }

  if (req.method === "POST" && url.pathname === "/api/signup") {
    let payload;
    try {
      payload = JSON.parse((await readBody(req)) || "{}");
    } catch {
      return send(res, 400, { "Content-Type": "application/json" }, JSON.stringify({ success: false, errors: ["Invalid JSON body"] }));
    }

    const { name, email, password } = payload;
    const errors = [];
    if (!name || !String(name).trim()) errors.push("Name is required");
    if (!email || !String(email).trim()) errors.push("Email is required");
    if (!password || String(password).length < 6) errors.push("Password must be at least 6 characters");
    if (email && String(email).trim() && !isValidEmail(email)) errors.push("Email is not valid");

    if (errors.length > 0) {
      return send(res, 400, { "Content-Type": "application/json" }, JSON.stringify({ success: false, errors }));
    }

    return send(res, 200, { "Content-Type": "application/json" }, JSON.stringify({ success: true, name }));
  }

  send(res, 404, { "Content-Type": "text/plain" }, "Not found");
});

server.listen(PORT, () => {
  console.log(`Demo signup app listening on http://127.0.0.1:${PORT}`);
});

module.exports = server;
