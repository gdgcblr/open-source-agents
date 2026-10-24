"""Bounded, read-only download of public GitHub repository archives."""

from __future__ import annotations

import http.client
import io
import json
import re
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator

API_HOST = "api.github.com"
ALLOWED_REDIRECT_HOSTS = {"api.github.com", "github.com", "codeload.github.com"}
REQUEST_TIMEOUT_SECONDS = 20
MAX_METADATA_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 50_000_000
MAX_ARCHIVE_FILES = 10_000
MAX_ARCHIVE_FILE_BYTES = 20_000_000
MAX_UNPACKED_BYTES = 150_000_000
REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")


@dataclass(frozen=True)
class GitHubRepository:
    owner: str
    name: str
    url: str


@dataclass(frozen=True)
class DownloadedRepository:
    path: Path
    url: str
    ref: str


def parse_github_url(repository_url: str) -> GitHubRepository:
    """Accept only canonical HTTPS URLs for public github.com repositories."""
    parsed = urllib.parse.urlsplit(repository_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Only public repository URLs in the form "
            "https://github.com/owner/repository are supported."
        )

    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise ValueError(
            "GitHub URL must point directly to a repository: "
            "https://github.com/owner/repository"
        )
    owner, name = parts
    if name.lower().endswith(".git"):
        name = name[:-4]
    if (
        not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", owner)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name)
        or name in {".", ".."}
    ):
        raise ValueError("GitHub URL contains an invalid owner or repository name.")

    return GitHubRepository(owner=owner, name=name, url=f"https://github.com/{owner}/{name}")


def _validate_ref(ref: str) -> str:
    if (
        not REF_PATTERN.fullmatch(ref)
        or any(segment in {"", ".", ".."} for segment in ref.split("/"))
        or ref.endswith(".lock")
    ):
        raise ValueError(
            "Invalid GitHub ref. Use a branch, tag, or commit name with letters, "
            "numbers, dots, underscores, hyphens, or slashes."
        )
    return ref


class _GitHubRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        parsed = urllib.parse.urlsplit(new_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_REDIRECT_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
        ):
            raise ValueError("GitHub returned an unsafe archive redirect.")
        return super().redirect_request(
            request, response, code, message, headers, new_url
        )


def _request_bytes(url: str, *, limit: int, accept: str) -> bytes:
    opener = urllib.request.build_opener(_GitHubRedirectHandler())
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "First-PR-Compass/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError as error:
                    raise ValueError("GitHub returned an invalid content length.") from error
                if declared_length > limit:
                    raise ValueError(f"GitHub response exceeds the {limit} byte limit.")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(min(64_000, limit + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ValueError(f"GitHub response exceeds the {limit} byte limit.")
                chunks.append(chunk)
            return b"".join(chunks)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError(
                "Repository or ref was not found. Check that it is public and the URL/ref is correct."
            ) from error
        if error.code == 403 or error.code == 429:
            raise ValueError(
                "GitHub rate-limited this request. Wait and try again; public unauthenticated "
                "requests have a limited hourly quota."
            ) from error
        raise ValueError(f"GitHub request failed with HTTP {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError) as error:
        raise ValueError(f"Could not reach GitHub: {error}") from error


def _repository_metadata(repository: GitHubRepository) -> dict[str, object]:
    owner = urllib.parse.quote(repository.owner, safe="")
    name = urllib.parse.quote(repository.name, safe="")
    url = f"https://{API_HOST}/repos/{owner}/{name}"
    payload = _request_bytes(
        url,
        limit=MAX_METADATA_BYTES,
        accept="application/vnd.github+json",
    )
    try:
        metadata = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("GitHub returned invalid repository metadata.") from error
    if not isinstance(metadata, dict) or not isinstance(metadata.get("default_branch"), str):
        raise ValueError("GitHub response did not include a default branch.")
    return metadata


def _safe_extract(archive: bytes, destination: Path) -> Path:
    try:
        zipped = zipfile.ZipFile(io.BytesIO(archive))
    except (OSError, EOFError, zipfile.BadZipFile) as error:
        raise ValueError("GitHub returned an invalid repository archive.") from error

    with zipped:
        infos = zipped.infolist()
        if not infos or len(infos) > MAX_ARCHIVE_FILES:
            raise ValueError(
                f"Repository archive must contain between 1 and {MAX_ARCHIVE_FILES} entries."
            )

        validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        archive_root: str | None = None
        unpacked_size = 0
        seen_paths: set[str] = set()
        for info in infos:
            raw_name = info.filename
            if "\\" in raw_name or raw_name.startswith("/"):
                raise ValueError("Repository archive contains an unsafe file path.")
            parts = raw_name.rstrip("/").split("/")
            if (
                not parts
                or any(part in {"", ".", ".."} for part in parts)
                or any(":" in part or part.endswith((" ", ".")) for part in parts)
                or re.match(r"^[A-Za-z]:", parts[0])
            ):
                raise ValueError("Repository archive contains an unsafe file path.")
            if archive_root is None:
                archive_root = parts[0]
            if parts[0] != archive_root:
                raise ValueError("Repository archive contains multiple root directories.")
            relative_parts = parts[1:]
            if not relative_parts:
                continue

            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if stat.S_ISLNK(mode) or (
                file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR}
            ):
                raise ValueError("Repository archive contains a link or special file.")
            if info.flag_bits & 0x1:
                raise ValueError("Encrypted repository archives are not supported.")
            if info.is_dir():
                continue
            if info.file_size > MAX_ARCHIVE_FILE_BYTES:
                raise ValueError("Repository archive contains an oversized file.")

            relative_path = PurePosixPath(*relative_parts)
            path_key = relative_path.as_posix().casefold()
            if path_key in seen_paths:
                raise ValueError("Repository archive contains duplicate file paths.")
            seen_paths.add(path_key)
            unpacked_size += info.file_size
            if unpacked_size > MAX_UNPACKED_BYTES:
                raise ValueError("Repository archive exceeds the uncompressed size limit.")
            validated.append((info, relative_path))

        if not validated:
            raise ValueError("Repository archive contains no files to analyze.")

        extracted_size = 0
        for info, relative_path in validated:
            target = destination.joinpath(*relative_path.parts)
            resolved = target.resolve()
            if not resolved.is_relative_to(destination.resolve()):
                raise ValueError("Repository archive contains an unsafe file path.")
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                bytes_written = 0
                with zipped.open(info) as source, target.open("xb") as output:
                    while True:
                        chunk = source.read(64_000)
                        if not chunk:
                            break
                        bytes_written += len(chunk)
                        if (
                            bytes_written > MAX_ARCHIVE_FILE_BYTES
                            or extracted_size + bytes_written > MAX_UNPACKED_BYTES
                        ):
                            raise ValueError(
                                "Repository archive exceeded its uncompressed size limit."
                            )
                        output.write(chunk)
                if bytes_written != info.file_size:
                    raise ValueError("Repository archive file size did not match its index.")
                extracted_size += bytes_written
            except ValueError:
                raise
            except (OSError, EOFError, RuntimeError, zipfile.BadZipFile) as error:
                raise ValueError("Could not safely extract the GitHub archive.") from error

    return destination


@contextmanager
def download_github_repository(
    repository_url: str, ref: str | None = None
) -> Iterator[DownloadedRepository]:
    """Fetch a public GitHub archive into a temporary directory and clean it up."""
    repository = parse_github_url(repository_url)
    metadata = _repository_metadata(repository)
    selected_ref = _validate_ref(ref) if ref else str(metadata["default_branch"])
    if not _validate_ref(selected_ref):
        raise ValueError("GitHub repository returned an invalid default branch.")
    quoted_ref = urllib.parse.quote(selected_ref, safe="/-._")
    archive_url = (
        f"https://{API_HOST}/repos/{urllib.parse.quote(repository.owner, safe='')}/"
        f"{urllib.parse.quote(repository.name, safe='')}/zipball/{quoted_ref}"
    )
    archive = _request_bytes(
        archive_url,
        limit=MAX_ARCHIVE_BYTES,
        accept="application/vnd.github+json",
    )
    with tempfile.TemporaryDirectory(prefix="first-pr-compass-") as temporary:
        root = _safe_extract(archive, Path(temporary))
        yield DownloadedRepository(
            path=root,
            url=repository.url,
            ref=selected_ref,
        )
