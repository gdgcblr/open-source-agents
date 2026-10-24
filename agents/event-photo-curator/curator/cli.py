"""Small, non-destructive event photo pipeline."""

from pathlib import Path
import shutil
import os
import math
from enum import Enum
from typing import Annotated

from dotenv import load_dotenv
import imagehash
from rich.console import Console
from rich.progress import track
from rich.table import Table
import typer

from .dedupe import group_duplicates, select_diverse
from .filters import exposure_flag, sharpness
from .loader import SUPPORTED, read_photo
from .providers import GeminiProvider, MockProvider, OllamaProvider
from .ranker import rank
from .report import write_csv, write_html

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
console = Console()


class Provider(str, Enum):
    ollama = "ollama"
    gemini = "gemini"
    mock = "mock"


@app.callback()
def main():
    """Curate event photos without changing originals."""


@app.command()
def run(
    photos: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, readable=True)
    ],
    out: Annotated[Path, typer.Option(help="New or empty output directory.")] = Path(
        "picks"
    ),
    top: Annotated[int, typer.Option(min=1)] = 15,
    provider: Annotated[Provider, typer.Option()] = Provider.ollama,
    model: Annotated[
        str | None,
        typer.Option(
            help="Defaults to local Gemma 4, or Gemini 2.5 Flash for --provider gemini."
        ),
    ] = None,
    batch_size: Annotated[int, typer.Option(min=1, max=16)] = 1,
    cache_dir: Annotated[Path, typer.Option()] = Path(".cache"),
    blur_threshold: Annotated[float, typer.Option(min=0)] = 100,
    dup_distance: Annotated[int, typer.Option(min=0, max=64)] = 6,
    exposure_percent: Annotated[float, typer.Option(min=0, max=100)] = 20,
    caption_style: Annotated[
        str, typer.Option()
    ] = "Casual event Instagram, no hashtag spam",
):
    """Filter, rank and copy the best photos; scan the input folder non-recursively."""
    if not math.isfinite(blur_threshold) or not math.isfinite(exposure_percent):
        raise typer.BadParameter("Thresholds must be finite numbers")
    load_dotenv(Path.cwd() / ".env")
    source, destination = photos.resolve(), out.resolve()
    if (
        source == destination
        or source in destination.parents
        or destination in source.parents
    ):
        raise typer.BadParameter("--out must be separate from the input tree")
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise typer.BadParameter(
            "--out must be a new or empty directory; existing files are never overwritten"
        )
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if provider == Provider.gemini and (not key or key == "your-key-here"):
        console.print(
            "WARNING: GEMINI_API_KEY is unset or a placeholder; using mock ranking. No AI visual judgment.",
            style="yellow",
        )
        provider = Provider.mock
    model = model or (
        "gemini-2.5-flash" if provider == Provider.gemini else "gemma4:e2b-it-q4_K_M"
    )
    scorer = (
        OllamaProvider(model)
        if provider == Provider.ollama
        else (
            GeminiProvider(key, model)
            if provider == Provider.gemini
            else MockProvider()
        )
    )
    console.print(f"Provider: {scorer.name} | Model: {scorer.model}", markup=False)
    paths = sorted(
        p
        for p in source.iterdir()
        if p.is_file() and not p.is_symlink() and p.suffix.lower() in SUPPORTED
    )
    if not paths:
        raise typer.BadParameter("No supported photos found in the input folder")
    records = []
    for path in track(paths, description="Inspecting photos", console=console):
        photo, image = read_photo(path)
        if image is not None:
            photo.sharpness = sharpness(image)
            photo.exposure = exposure_flag(image, exposure_percent)
            photo.phash = imagehash.phash(image)
            if photo.sharpness < blur_threshold:
                photo.flags.append(
                    f"Blurry: {photo.sharpness:.2f} < {blur_threshold:g}"
                )
            if photo.exposure:
                photo.flags.append(photo.exposure)
        records.append(photo)
    duplicates = group_duplicates(records, dup_distance)
    try:
        tokens, cache_hits = rank(
            records, scorer, caption_style, cache_dir, batch_size, console
        )
    except (RuntimeError, OSError) as exc:
        console.print(
            (
                str(exc)
                if isinstance(exc, RuntimeError)
                else "Cannot read/write the local cache directory."
            ),
            style="red",
            markup=False,
        )
        raise typer.Exit(1) from None
    finally:
        if isinstance(scorer, GeminiProvider):
            scorer.client.close()
    selected = select_diverse(records, top)
    destination.mkdir(parents=True, exist_ok=True)
    for photo in selected:
        # Exclusive creation prevents replacing anything, even after preflight.
        with photo.path.open("rb") as src, (destination / photo.path.name).open(
            "xb"
        ) as dst:
            shutil.copyfileobj(src, dst)
        photo.picked = True
    for photo in records:
        if photo.assessment and not photo.picked:
            photo.reasons.append(
                f"Outside top {top} after AI ranking and diversity preference; "
                + photo.assessment["reason"]
            )
    write_csv(records, destination)
    write_html(records, destination, scorer.name, scorer.model)
    table = Table(title="AfterClick")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for label, count in [
        ("Scanned", len(records)),
        ("Blurry", sum(p.sharpness < blur_threshold for p in records if p.preview)),
        ("Dupes", duplicates),
        ("Exposure issues", sum(bool(p.exposure) for p in records)),
        ("Unreadable", sum(not p.preview for p in records)),
        ("Picked", sum(p.picked for p in records)),
        ("Cache hits", cache_hits),
        ("Estimated tokens used", tokens),
    ]:
        table.add_row(label, str(count))
    console.print(table)
    console.print(f"Output: {destination}", markup=False)


@app.command()
def models(folder: Annotated[Path, typer.Option()] = Path(".cache/models")):
    """Download and verify the two OpenCV face models (about 39 MB)."""
    from .faces import download_models

    download_models(folder)
    console.print("Face models ready. Selfie queries stay on this laptop.")


@app.command()
def serve(
    data: Annotated[Path, typer.Option()] = Path(".local-event"),
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8787,
):
    """Open the single-event local pilot; binds to this laptop only."""
    import uvicorn
    from .web import create_app

    console.print(f"Local event gallery: http://127.0.0.1:{port}")
    uvicorn.run(create_app(data), host="127.0.0.1", port=port, log_level="warning")


@app.command()
def doctor():
    """Check the local runtime without loading a model or sending any image."""
    from .runtime import runtime_status

    status = runtime_status()
    table = Table(title="Local runtime")
    table.add_column("Check")
    table.add_column("Status")
    for label, value in status.items():
        table.add_row(label.replace("_", " ").title(), str(value))
    console.print(table)
    if not status["default_model_ready"]:
        console.print("To prepare vision AI: ollama pull gemma4:e2b-it-q4_K_M")


@app.command()
def ask(
    query: Annotated[str, typer.Argument(help="Natural-language photo request.")],
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8787,
):
    """Ask the local tool-calling agent; the gallery server must be running."""
    import http.cookiejar
    import json
    import time
    from urllib.request import build_opener, HTTPCookieProcessor, Request
    from urllib.error import URLError, HTTPError

    base = f"http://127.0.0.1:{port}"
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, payload=None):
        headers = {"X-Curator-Request": "local"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = Request(
            base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers,
        )
        with opener.open(req, timeout=30) as response:
            return response.read()

    try:
        request("/")
        request("/api/agent", {"query": query})
        started = time.monotonic()
        with console.status("Local agent is choosing and running tools…") as status:
            while True:
                result = json.loads(request("/api/agent"))
                status.update(result["job"]["phase"])
                if not result["job"]["running"]:
                    break
                if time.monotonic() - started > 660:
                    raise ValueError(
                        "Waiting timed out; inspect the local gallery job."
                    )
                time.sleep(0.5)
        if result["job"]["error"]:
            raise ValueError(result["job"]["error"])
        answer = result["result"]
        console.print(answer["answer"], markup=False)
        for step in answer["trace"]:
            console.print(
                f"Tool: {step['tool']} | {step['count']} photos | {step['summary']}",
                markup=False,
            )
        for photo in answer["photos"]:
            console.print(photo["filename"], markup=False)
        console.print(f"Steps: {answer['steps']} | Local tokens: {answer['tokens']}")
    except (URLError, HTTPError, ValueError) as exc:
        console.print(f"Agent request failed: {exc}", markup=False)
        raise typer.Exit(1) from None
