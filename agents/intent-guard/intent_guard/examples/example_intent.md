# JIRA-1234: Add JWT Authentication to User API

## Summary

As a backend developer, I need to add JWT-based authentication to the
`/api/users` endpoints so that only authenticated users can access
protected resources.

## Acceptance Criteria

1. **Login Endpoint**: Create `POST /api/auth/login` accepting `email` and
   `password` in the request body.  Return a JWT token on success.

2. **JWT Algorithm**: Tokens MUST be signed using the **RS256** algorithm
   with an RSA key pair.  The private key path is configured via the
   `JWT_PRIVATE_KEY_PATH` environment variable.

3. **Token Validation Middleware**: Implement a middleware/decorator that
   validates the JWT on all protected routes and injects the authenticated
   user into the request context.

4. **Password Hashing**: All passwords MUST be hashed using **bcrypt** with
   a minimum work factor of 12 rounds.  Never store plaintext passwords.

5. **Rate Limiting**: Implement rate limiting on the login endpoint — max
   **5 attempts per IP address per 15-minute window**.  Return HTTP 429
   when exceeded.

6. **Error Responses**: Return `401 Unauthorized` with a clear JSON error
   message (`{"error": "Invalid credentials"}`) when login fails.

## Technical Notes

- Use the existing `User` SQLAlchemy model in `models/user.py`.
- Token expiry should be 1 hour.
- Refresh tokens are out of scope for this ticket.

