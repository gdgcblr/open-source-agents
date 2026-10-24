# Knowledge Base Samples

This folder contains fictional sample documents used to demonstrate and
test the Method Documents AI Agent.

Add documents here only when you have permission to process them.
Supported file formats are `.md`, `.txt`, `.pdf`, and `.docx`.

After adding or updating documents, rebuild the local index:

``` bash
python -m knowflow.cli index
```

The generated index is stored under `.knowflow_index/` by default and
should not be committed.

**Do not add confidential company documents, customer data, restricted
CAD files, or proprietary engineering drawings to the public
repository.** Questions and retrieved excerpts are sent to the
configured Gemini API when an answer is generated. Use synthetic or
public examples for repository demonstrations.
