# API Change Checklist

Before releasing an API change:

1. Confirm the request and response schema.
2. Check required fields, collection types, and nullable properties.
3. Add or update automated tests for valid and invalid payloads.
4. Verify authentication and authorization behavior.
5. Review backward compatibility for existing clients.
6. Capture representative success and failure responses.
7. Update API documentation and release notes.
8. Test in a non-production environment before release.

If a request fails, inspect the HTTP status, response body, server-side logs, and the API schema. Do not assume the status code alone proves the root cause.
