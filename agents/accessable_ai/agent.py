
import asyncio
import ipaddress
import os
import socket
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from google import genai
from google.genai import types

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools.tool_context import ToolContext

from playwright.async_api import async_playwright

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
)


# ---------------------------------------------------------
# 1. Project paths and model configuration
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
SCREENSHOT_DIR = REPORTS_DIR / "screenshots"

MODEL_NAME = "gemma-4-26b-a4b-it"


# ---------------------------------------------------------
# 2. URL validation
# ---------------------------------------------------------

def validate_public_url(url: str) -> str:
    """Validate a public HTTP or HTTPS website URL."""

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(
            "Please provide a valid URL starting with https:// or http://."
        )

    hostname = parsed.hostname

    if hostname.lower() == "localhost":
        raise ValueError("Localhost URLs are not supported.")

    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(
            "Could not resolve the website hostname."
        ) from exc

    if not addresses:
        raise ValueError("Could not resolve the website hostname.")

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])

        if not ip.is_global:
            raise ValueError(
                "Private or non-public network addresses are not allowed."
            )

    return url


# ---------------------------------------------------------
# 3. Website inspection and accessibility analysis
# ---------------------------------------------------------

async def review_website_url(url: str) -> dict:
    """
    Open a public website, capture a screenshot, collect page
    observations, and ask Gemma to identify potential issues.
    """

    try:
        url = validate_public_url(url)

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        screenshot_path = SCREENSHOT_DIR / "website.png"

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)

            try:
                page = await browser.new_page(
                    viewport={"width": 1440, "height": 1000},
                    device_scale_factor=1,
                )

                # Block requests to non-public IP addresses.
                async def guard_request(route):
                    request_url = route.request.url
                    parsed_request = urlparse(request_url)

                    if parsed_request.scheme in ("data", "blob"):
                        await route.continue_()
                        return

                    if parsed_request.scheme not in ("http", "https"):
                        await route.abort()
                        return

                    hostname = parsed_request.hostname

                    if not hostname:
                        await route.abort()
                        return

                    try:
                        addresses = await asyncio.to_thread(
                            socket.getaddrinfo, hostname, None
                        )

                        if not addresses or any(
                            not ipaddress.ip_address(item[4][0]).is_global
                            for item in addresses
                        ):
                            await route.abort()
                            return

                    except (socket.gaierror, ValueError):
                        await route.abort()
                        return

                    await route.continue_()

                await page.route("**/*", guard_request)

                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                await page.wait_for_timeout(1000)

                screenshot_bytes = await page.screenshot(
                    full_page=False
                )

                screenshot_path.write_bytes(screenshot_bytes)

                page_summary = await page.evaluate(
                    """() => ({
                        title: document.title,
                        url: location.href,

                        headings: Array.from(
                            document.querySelectorAll('h1, h2, h3')
                        ).slice(0, 30).map(el => ({
                            tag: el.tagName,
                            text: (el.innerText || '').trim()
                        })),

                        images: Array.from(
                            document.querySelectorAll('img')
                        ).slice(0, 50).map(el => ({
                            alt: el.getAttribute('alt'),
                            hasAlt: el.hasAttribute('alt')
                        })),

                        buttons: Array.from(
                            document.querySelectorAll(
                                'button, input[type=button], input[type=submit]'
                            )
                        ).slice(0, 50).map(el => ({
                            text: (el.innerText || el.value || '').trim(),
                            ariaLabel: el.getAttribute('aria-label')
                        })),

                        links: Array.from(
                            document.querySelectorAll('a')
                        ).slice(0, 50).map(el => ({
                            text: (el.innerText || '').trim(),
                            ariaLabel: el.getAttribute('aria-label')
                        }))
                    })"""
                )

            finally:
                await browser.close()

        api_key = os.environ.get("GOOGLE_API_KEY")

        if not api_key:
            return {
                "error": "GOOGLE_API_KEY is missing from the environment."
            }

        client = genai.Client(api_key=api_key)

        prompt = f"""
You are AccessAble AI, an accessibility detective.

Review the supplied website screenshot and page observations.

Website observations:
{page_summary}

Identify up to three important potential accessibility issues.

For each finding provide:
1. Issue
2. Evidence visible in the screenshot or page observations
3. Potential impact on users
4. Priority: High, Medium, or Low
5. A practical suggested fix
6. How to verify the fix

Important rules:
- Distinguish observed evidence from assumptions.
- Do not invent contrast ratios.
- Do not claim to know keyboard or screen-reader behavior
  from a screenshot alone.
- Missing image alt attributes may warrant inspection, but
  whether an image needs alternative text depends on its purpose.
- Do not claim WCAG compliance based on this review.
- Recommend additional browser or manual testing when needed.
"""

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(
                    data=screenshot_bytes,
                    mime_type="image/png",
                ),
            ],
        )

        findings = response.text or "No findings were returned."

        return {
            "website_url": url,
            "page_title": page_summary["title"],
            "page_observations": page_summary,
            "screenshot_path": str(screenshot_path),
            "findings": findings,
            "note": (
                "This is a preliminary accessibility review. "
                "Validate findings with appropriate tests."
            ),
        }

    except Exception as exc:
        return {
            "error": (
                f"Website review failed: {type(exc).__name__}: {exc}"
            )
        }


# ---------------------------------------------------------
# 4. PDF report generation
# ---------------------------------------------------------

async def create_accessibility_report(
    report_text: str,
    tool_context: ToolContext,
) -> str:
    """
    Generate a PDF report, save it locally, and attempt to save
    a second copy as an ADK artifact.
    """

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    filename = "accessibility_report.pdf"
    pdf_path = REPORTS_DIR / filename
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="AccessAble AI Accessibility Review",
        author="AccessAble AI",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "AccessAbleTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17365D"),
        spaceAfter=12,
    )

    body_style = ParagraphStyle(
        "AccessAbleBody",
        parent=styles["BodyText"],
        leading=15,
        spaceAfter=8,
    )

    story = [
        Paragraph("AccessAble AI", title_style),
        Paragraph(
            "Website Accessibility Review",
            styles["Heading2"],
        ),
        Paragraph(
            "AI-assisted visual screening. Findings require verification.",
            body_style,
        ),
        Spacer(1, 10),
        HRFlowable(
            width="100%",
            color=colors.HexColor("#17365D"),
        ),
        Spacer(1, 12),
    ]

    # Escape user/model-generated text before passing it to ReportLab.
    # Preserve basic heading structure for readability.
    for raw_line in report_text.splitlines():
        line = raw_line.strip()

        if not line:
            story.append(Spacer(1, 5))
            continue

        if line.startswith("### "):
            story.append(
                Paragraph(escape(line[4:]), styles["Heading3"])
            )
        elif line.startswith("## "):
            story.append(
                Paragraph(escape(line[3:]), styles["Heading2"])
            )
        elif line.startswith("# "):
            story.append(
                Paragraph(escape(line[2:]), styles["Heading1"])
            )
        else:
            story.append(
                Paragraph(escape(line), body_style)
            )

    # Build the PDF in memory.
    document.build(story)
    pdf_bytes = buffer.getvalue()

    # Save locally FIRST. This does not depend on ADK artifacts.
    pdf_path.write_bytes(pdf_bytes)

    # Artifact saving is optional: local PDF creation has already succeeded.
    try:
        artifact = types.Part.from_bytes(
            data=pdf_bytes,
            mime_type="application/pdf",
        )

        version = await tool_context.save_artifact(
            filename=filename,
            artifact=artifact,
        )

        artifact_status = (
            f"ADK artifact saved: {filename}, version {version}."
        )

    except Exception as exc:
        artifact_status = (
            "The local PDF was saved, but ADK artifact saving failed: "
            f"{type(exc).__name__}: {exc}"
        )

    return (
        "PDF created successfully. "
        f"Local path: {pdf_path.resolve()}. "
        f"{artifact_status}"
    )


# ---------------------------------------------------------
# 5. Main AccessAble AI agent
# ---------------------------------------------------------

root_agent = LlmAgent(
    name="accessable_ai",
    model=Gemini(model=MODEL_NAME),
    description=(
        "Reviews website screenshots or public website URLs "
        "for potential accessibility issues and generates PDF reports."
    ),
    instruction="""
You are AccessAble AI, a website accessibility review assistant.

Your job is to review websites using a screenshot or a public URL.

CONVERSATION FLOW:

If the user has not provided a screenshot or URL and has not
selected an input method, say:

"Welcome to AccessAble AI!

I'm your AI-powered website accessibility detective.

How would you like to review your website?

1. Screenshot — upload a screenshot of your website.
2. Website URL — paste your public website URL.

Reply Screenshot or URL to begin."

If the user says "URL", "Website URL", or "2", ask them to
paste their public website URL.

If the user says "Screenshot" or "1", ask them to upload
their screenshot.

If the user provides a URL, call review_website_url with
that URL immediately.

If the user uploads a screenshot, analyze that screenshot
directly. Do not ask for a URL.

For screenshot reviews, provide up to three important findings.
Distinguish visible observations from assumptions. Do not invent
contrast ratios or claim WCAG compliance from a screenshot alone.

ACCESSIBILITY FINDINGS:

For each finding, provide:
- Issue
- Evidence
- Potential impact on users
- Priority: High, Medium, or Low
- Suggested fix
- How to verify the fix

PDF REPORTS — IMPORTANT:

After EVERY successful accessibility review, generate a PDF
automatically, even when the user does not explicitly ask for one.

For a website URL review:
1. Call review_website_url with the URL.
2. Check its result. If it contains an error, explain the error
   and do not generate a report claiming the review succeeded.
3. Use the returned findings and page details to create a
   complete report.
4. Call create_accessibility_report with the complete report text.
5. Wait for the tool result.
6. Tell the user whether the PDF was created and give its local path.

For a screenshot review:
1. Analyze the uploaded screenshot.
2. Produce the findings.
3. Call create_accessibility_report with the complete findings.
4. Wait for the tool result.
5. Tell the user whether the PDF was created and give its local path.

Never claim a PDF was created unless the tool confirms it.
If PDF creation fails, explain the error returned by the tool.

IMPORTANT LIMITATIONS:

- Distinguish observed evidence from assumptions.
- Never invent contrast ratios.
- Do not claim to know keyboard or screen-reader behavior
  from a screenshot alone.
- Do not claim WCAG compliance based only on visual inspection.
- Recommend browser-based and manual testing where appropriate.
- If the user has already provided a URL or screenshot,
  do not ask them to choose an input method again.
""",
    tools=[
        review_website_url,
        create_accessibility_report,
    ],
)
