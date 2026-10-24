# Documentation Access and Handling

Only index documents that the current user is authorized to access. A local document index may preserve text after a source file is moved or permissions change, so rebuild the index after access changes.

Do not place credentials, access tokens, personal data, production logs, or confidential customer information in demo repositories. Use synthetic examples for public demonstrations.

For production use, retrieval must enforce source-system permissions before passages are sent to a model. A local folder ingestion process does not automatically reproduce SharePoint permissions.
