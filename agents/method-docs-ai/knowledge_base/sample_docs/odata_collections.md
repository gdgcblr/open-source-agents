# OData Collection Properties

When an API schema defines a property as a collection of strings, the JSON representation is an array of strings, even if the array contains only one value.

Example:

```json
{
  "productClasses": ["24", "25"]
}
```

When troubleshooting an OData request:

1. Confirm the property name and type in the API metadata or schema.
2. Confirm whether the endpoint expects a full entity representation or a partial update.
3. Validate the JSON syntax and value types.
4. Check the HTTP method and endpoint-specific update rules.
5. Inspect the response body for validation details.

Do not assume every OData service uses identical update semantics. Follow the endpoint's documented contract.
