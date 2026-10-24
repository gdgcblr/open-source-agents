## 🛡️ IntentGuard Audit Scorecard

**Verdict:** 🔴 FAIL &nbsp;|&nbsp; **Confidence:** `1.00`

> The pull request fails verification due to multiple critical security flaws and requirement misinterpretations. Password hashing uses fast SHA-256 instead of bcrypt (REQ-4), JWT token signing uses symmetric HS256 instead of RS256 (REQ-2), rate limiting is completely absent (REQ-5), and wrong error status codes are returned on login failure (REQ-6). Furthermore, the diff contains critical scope creep in app/admin/router.py, creating an unauthenticated endpoint that sets all user passwords to plaintext.

### 📋 Requirements Traceability Matrix

| ID | Requirement | Status | Evidence | Finding |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-1** | Create POST /api/auth/login accepting email and password in request body and returning a JWT token on success. | ✅ Implemented | `app/auth/router.py:42` | The login endpoint POST /api/auth/login is defined and accepts LoginRequest containing email and password, returning a JWT token response. |
| **REQ-2** | Tokens MUST be signed using RS256 algorithm with RSA key pair from JWT_PRIVATE_KEY_PATH. | 🔄 Misinterpreted | `app/auth/router.py:18` | The code uses symmetric HS256 signing with a fallback JWT_SECRET_KEY rather than RS256 signing loaded from JWT_PRIVATE_KEY_PATH. |
| **REQ-3** | Implement token validation middleware/decorator that validates JWT on protected routes and injects authenticated user into context. | ⚠️ Partial | `app/auth/middleware.py:15` | Middleware get_current_user is implemented, but it verifies tokens using HS256 instead of RS256 and returns raw payload dictionary rather than fetching and injecting the authenticated User model instance. |
| **REQ-4** | All passwords MUST be hashed using bcrypt with a minimum work factor of 12 rounds. | 🔄 Misinterpreted | `app/auth/router.py:32` | The code uses SHA-256 (hashlib.sha256) for password hashing without salt or work factor instead of bcrypt with >= 12 rounds. |
| **REQ-5** | Implement rate limiting on login endpoint (max 5 attempts per IP per 15 minutes, HTTP 429 when exceeded). | ❌ Missing | — | No rate limiting mechanism is present on the login endpoint or in the application. |
| **REQ-6** | Return 401 Unauthorized with error message {"error": "Invalid credentials"} when login fails. | 🔄 Misinterpreted | `app/auth/router.py:48` | The endpoint raises HTTP 403 Forbidden with detail 'Access denied' instead of 401 Unauthorized with {"error": "Invalid credentials"}. |

### 🚨 Scope Creep & Unmatched Changes

| Location | Unrequested Change | Risk Assessment |
| :--- | :--- | :--- |
| `app/admin/router.py:12` | Added an admin endpoint POST /api/admin/reset that resets all user passwords to a default plaintext value 'changeme123'. | This unrequested feature introduces severe security vulnerabilities by allowing unauthenticated password resets and storing passwords in plaintext. |

### ⚠️ Issues & Actionable Fixes

| Severity | Category | Description | Suggested Fix |
| :--- | :--- | :--- | :--- |
| 🛑 Critical | `security_concern` | Passwords are hashed using un-salted SHA-256 instead of bcrypt with a minimum work factor of 12 rounds. | Use passlib or bcrypt library with a work factor of 12 (e.g. CryptContext(schemes=['bcrypt'])) to hash and verify passwords. |
| 🛑 Critical | `misinterpretation` | JWT tokens are signed and verified using symmetric HS256 instead of asymmetric RS256 with key files. | Load the private key specified in JWT_PRIVATE_KEY_PATH to sign tokens using RS256, and use the corresponding public key in middleware to decode and verify. |
| 🛑 Critical | `scope_creep` | Unrequested admin endpoint introduced in app/admin/router.py that resets all user passwords to plaintext 'changeme123' without authentication. | Delete app/admin/router.py entirely as it is out of scope and creates a severe security flaw. |
| 🟧 Major | `missing_requirement` | Rate limiting (5 attempts per IP per 15 minutes) is missing on POST /api/auth/login. | Add rate-limiting middleware or decorator (e.g., using slowapi) configured for 5 requests per 15 minutes per IP returning HTTP 429. |
| 🟨 Minor | `misinterpretation` | Login error response returns 403 Forbidden instead of 401 Unauthorized with requested JSON body format. | Change status_code to 401 and structure exception detail as {"error": "Invalid credentials"}. |
| 🟨 Minor | `incomplete_implementation` | Middleware decodes token with HS256 and returns payload dictionary rather than fetching User model. | Update get_current_user to decode with RS256 and fetch/inject the database User object into request state. |

---
*Generated automatically by [IntentGuard](https://github.com/gdgcblr/open-source-agents/tree/main/agents/intent-guard)*