from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, unquote

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry

from claimcheck.ledger import Claim, Result
from claimcheck.safety import bounded_body, http_client

METHODS = {"get", "head", "options", "post", "put", "patch", "delete", "trace"}


def discover(text: str, source: str = "openapi.yaml") -> list[Claim]:
    depth = nodes = 0
    for event in yaml.parse(text):
        if isinstance(event, yaml.AliasEvent):
            raise ValueError("YAML aliases are unsupported; use OpenAPI local $ref instead")
        if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
            depth += 1
            nodes += 1
        elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
            depth -= 1
        elif isinstance(event, yaml.ScalarEvent):
            nodes += 1
        if depth > 64 or nodes > 10_000:
            raise ValueError("OpenAPI document exceeds nesting/node limit")
    document = yaml.safe_load(text)
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3."):
        raise ValueError("Expected an OpenAPI 3.x document")
    if not isinstance(document.get("paths"), dict):
        raise ValueError("OpenAPI paths must be an object")
    claims: list[Claim] = []
    for path, item in document["paths"].items():
        if not isinstance(path, str) or not isinstance(item, dict):
            raise ValueError("Invalid OpenAPI path item")
        line = next(
            (i for i, raw in enumerate(text.splitlines(), 1) if raw.strip() == f"{path}:"),
            1,
        )
        for method, operation in item.items():
            if method not in METHODS:
                continue
            if not isinstance(operation, dict):
                raise ValueError(f"Invalid operation: {method} {path}")
            responses = operation.get("responses")
            if not isinstance(responses, dict) or not all(
                isinstance(response, dict) for response in responses.values()
            ):
                raise ValueError(f"Responses must be objects: {method} {path}")
            parameters = (
                [*item.get("parameters", []), *operation.get("parameters", [])]
                if isinstance(item.get("parameters", []), list)
                and isinstance(operation.get("parameters", []), list)
                else None
            )
            if parameters is None or not all(isinstance(param, dict) for param in parameters):
                raise ValueError("OpenAPI parameters must be an array of objects")
            claims.append(
                Claim.create(
                    "openapi.operation",
                    source,
                    line,
                    f"{method.upper()} {path} matches its contract",
                    path=path,
                    method=method,
                    parameters=parameters,
                    operation=operation,
                    document=document,
                )
            )
    return claims


def has_external_ref(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "$ref" and (not isinstance(item, str) or not item.startswith("#/")))
            or has_external_ref(item)
            for key, item in value.items()
        )
    return isinstance(value, list) and any(has_external_ref(item) for item in value)


def normalize_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: normalize_schema(item) for key, item in value.items() if key != "nullable"}
    if value.get("nullable") and isinstance(result.get("type"), str):
        result["type"] = [result["type"], "null"]
    return result


def check(claim: Claim, base_url: str) -> Result:
    data = claim.data
    method, path = data["method"], data["path"]
    if method not in {"get", "head", "options"}:
        return Result(
            claim.id, "not_verified", "Mutating or TRACE operations are never auto-probed."
        )
    if has_external_ref(data["document"]):
        return Result(claim.id, "not_verified", "External $ref resolution is disabled.")
    if not path.startswith("/") or path.startswith("//") or any(c in path for c in "?#"):
        raise ValueError("OpenAPI paths must be origin-relative paths without query or fragment")
    if any(segment in {".", ".."} for segment in unquote(path).split("/")):
        raise ValueError("Path traversal in OpenAPI path")
    params: dict[str, str] = {}
    for parameter in data["parameters"]:
        if "$ref" in parameter:
            return Result(claim.id, "not_verified", "Referenced parameters need explicit examples.")
        location, name = parameter.get("in"), parameter.get("name")
        example = parameter.get("example", parameter.get("schema", {}).get("example"))
        if example is None:
            if parameter.get("required") or location == "path":
                return Result(
                    claim.id, "not_verified", f"No example for required parameter {name}."
                )
            continue
        if location == "path":
            path = path.replace("{" + name + "}", quote(str(example), safe=""))
        elif location == "query":
            params[name] = str(example)
        elif parameter.get("required"):
            return Result(
                claim.id, "not_verified", "Required header/cookie parameters unsupported."
            )
    if re.search(r"\{[^}]+\}", path):
        return Result(claim.id, "not_verified", "Path parameters need explicit examples.")
    operation = data["operation"]
    if operation.get("security", data["document"].get("security")):
        return Result(claim.id, "not_verified", "Authenticated operations need manual checks.")
    with (
        http_client() as client,
        client.stream(
            method.upper(), base_url + path, params=params, headers={"Accept": "application/json"}
        ) as response,
    ):
        body = bounded_body(response)
        status = response.status_code
        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    responses = {str(key): value for key, value in operation.get("responses", {}).items()}
    evidence: dict[str, Any] = {
        "method": method.upper(),
        "path": path,
        "status": status,
        "content_type": media_type,
    }
    # Probe a valid example: an error response is not proof of normal success.
    if status >= 400:
        return Result(claim.id, "failed", f"Valid-example probe returned HTTP {status}.", evidence)
    response_contract = responses.get(str(status), responses.get(f"{status // 100}XX"))
    if response_contract is None:
        response_contract = responses.get("default")
    if response_contract is None:
        return Result(claim.id, "failed", f"Undocumented HTTP status {status}.", evidence)
    if "$ref" in response_contract:
        return Result(
            claim.id, "not_verified", "Referenced response objects unsupported.", evidence
        )
    content = response_contract.get("content", {})
    if method == "head" or not content:
        return Result(
            claim.id, "passed", f"HTTP {status} matches the documented response.", evidence
        )
    media_contract = content.get(media_type)
    if media_contract is None:
        return Result(claim.id, "failed", f"Undocumented Content-Type: {media_type!r}.", evidence)
    schema = media_contract.get("schema")
    if schema is None or not (media_type == "application/json" or media_type.endswith("+json")):
        return Result(claim.id, "not_verified", "No supported JSON response schema.", evidence)
    try:
        instance = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return Result(claim.id, "failed", "Response is not valid JSON.", evidence)
    root_schema = normalize_schema(
        {
            **data["document"],
            "x-claimcheck-response": schema,
            "$ref": "#/x-claimcheck-response",
        }
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(root_schema, registry=Registry())
    errors = list(validator.iter_errors(instance))
    # Retain locations and validator names, not arbitrary response bodies or secrets.
    evidence["schema_errors"] = [
        {"path": list(error.absolute_path), "validator": error.validator} for error in errors[:20]
    ]
    return Result(
        claim.id,
        "failed" if errors else "passed",
        f"HTTP {status}; JSON schema {'mismatch' if errors else 'matched'}.",
        evidence,
    )
