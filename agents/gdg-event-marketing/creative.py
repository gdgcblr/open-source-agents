import html
import textwrap
from typing import Dict, List


SLIDE_COLORS = ("#174EA6", "#137333", "#A142F4", "#B06000")


def _wrap(value: str, width: int, max_lines: int) -> List[str]:
    lines = textwrap.wrap(
        value.strip(),
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
    )
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,;:") + "…"
    return lines


def _draft_paragraphs(draft: str) -> List[str]:
    paragraphs = []
    for paragraph in draft.splitlines():
        value = paragraph.strip()
        if not value or value.startswith("#") or value.lower().startswith(
            ("subject:", "preheader:", "when:", "where:", "with:", "speaker:")
        ):
            continue
        if "http://" in value or "https://" in value:
            value = value.split("http://", 1)[0].split("https://", 1)[0].strip()
        value = value.strip(" -*")
        if value:
            paragraphs.append(value)
    return paragraphs


def build_carousel_slides(event: dict, draft: str) -> List[Dict[str, str]]:
    """Create a four-card story using only the selected draft and event facts."""
    paragraphs = _draft_paragraphs(draft)
    title = event.get("title", "").strip() or "Community event"
    hook = paragraphs[0] if paragraphs else title
    context = paragraphs[1] if len(paragraphs) > 1 else event.get("description", "")
    date_time = event.get("date_time", "").strip()
    location = event.get("location", "").strip()
    speakers = event.get("speakers", "").strip()
    details = [fact for fact in (date_time, location, speakers) if fact]
    details_text = "\n".join(details) if details else "Check the event details in the original post."
    call_to_action = paragraphs[-1] if len(paragraphs) > 2 else "Join the conversation."
    event_url = event.get("url", "").strip()
    if event_url:
        call_to_action = "{}\n{}".format(call_to_action, event_url)

    return [
        {
            "eyebrow": "COMMUNITY EVENT",
            "title": title,
            "body": hook,
            "alt": "Carousel cover for {}".format(title),
        },
        {
            "eyebrow": "THE BIG IDEA",
            "title": "What you’ll explore",
            "body": context or hook,
            "alt": "Event overview: {}".format(context or hook),
        },
        {
            "eyebrow": "SAVE THE DETAILS",
            "title": "Make a date for it",
            "body": details_text,
            "alt": "Event details: {}".format(details_text.replace("\n", ", ")),
        },
        {
            "eyebrow": "YOUR NEXT STEP",
            "title": "Come curious. Leave connected.",
            "body": call_to_action,
            "alt": "Invitation and event link for {}".format(title),
        },
    ]


def _render_slide(slide: Dict[str, str], index: int) -> str:
    accent = SLIDE_COLORS[index % len(SLIDE_COLORS)]
    title_lines = _wrap(slide["title"], 22, 4)
    body_lines = []
    for paragraph in slide["body"].splitlines():
        body_lines.extend(_wrap(paragraph, 34, 5 - len(body_lines)))
        if len(body_lines) >= 5:
            break

    title_svg = "".join(
        '<text x="88" y="{}" class="title">{}</text>'.format(
            490 + line_index * 88, html.escape(line)
        )
        for line_index, line in enumerate(title_lines)
    )
    body_start = 910 if index in (0, 3) else 850
    body_svg = "".join(
        '<text x="92" y="{}" class="body">{}</text>'.format(
            body_start + line_index * 47, html.escape(line)
        )
        for line_index, line in enumerate(body_lines)
    )
    safe_alt = html.escape(slide["alt"], quote=True)
    return (
        '<svg class="carousel-slide" viewBox="0 0 1080 1350" role="img" '
        'aria-label="{}" xmlns="http://www.w3.org/2000/svg">'
        '<defs><linearGradient id="bg{}" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#101828"/><stop offset="1" stop-color="#202B43"/>'
        '</linearGradient></defs>'
        '<rect width="1080" height="1350" rx="44" fill="url(#bg{})"/>'
        '<circle cx="970" cy="135" r="230" fill="{}" opacity=".20"/>'
        '<circle cx="45" cy="1260" r="300" fill="{}" opacity=".16"/>'
        '<rect x="78" y="76" width="924" height="1198" rx="32" fill="none" '
        'stroke="#FFFFFF" stroke-opacity=".13" stroke-width="2"/>'
        '<text x="88" y="190" class="eyebrow" fill="{}">{}</text>'
        '<rect x="88" y="232" width="112" height="9" rx="4" fill="{}"/>'
        '{}{}'
        '<text x="88" y="1198" class="footer">A COMMUNITY INVITATION</text>'
        '<text x="930" y="1198" class="footer">{:02d} / 04</text>'
        '<style>text{{font-family:Arial,Helvetica,sans-serif;fill:#F8FAFD}}'
        '.eyebrow{{font-size:27px;font-weight:700;letter-spacing:5px;fill:#D2E3FC}}'
        '.title{{font-size:68px;font-weight:700;letter-spacing:-2px}}'
        '.body{{font-size:34px;font-weight:400;fill:#DDE5F2}}'
        '.footer{{font-size:19px;font-weight:700;letter-spacing:3px;fill:#AAB8CC}}</style>'
        '</svg>'
    ).format(
        safe_alt,
        index,
        index,
        accent,
        accent,
        accent,
        html.escape(slide["eyebrow"]),
        accent,
        title_svg,
        body_svg,
        index + 1,
    )


def render_carousel_html(event: dict, draft: str) -> str:
    """Return a self-contained preview/export page; it makes no network calls."""
    slides = build_carousel_slides(event, draft)
    rendered_slides = "\n".join(
        _render_slide(slide, index) for index, slide in enumerate(slides)
    )
    page_title = html.escape(event.get("title", "Event carousel"))
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f8fafd;color:#202124;font:16px Arial,sans-serif}}
main{{max-width:1100px;margin:28px auto;padding:0 18px}}h1{{font-size:24px}}
.note{{color:#5f6368;line-height:1.5}}.stage{{display:flex;align-items:center;justify-content:center;min-height:64vh}}
.carousel-slide{{display:none;width:min(100%,540px);height:auto;box-shadow:0 12px 40px #20212430;border-radius:22px}}
.carousel-slide.active{{display:block}}.controls{{display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap;margin:18px 0}}
button{{border:0;border-radius:8px;padding:11px 16px;background:#1a73e8;color:white;font-weight:700;cursor:pointer}}
button.secondary{{background:#e8f0fe;color:#174ea6}}button:hover{{filter:brightness(.95)}}
#counter{{min-width:70px;text-align:center;color:#5f6368}}.privacy{{font-size:13px;color:#5f6368}}
@media print{{body{{background:white}}main{{margin:0;max-width:none}}h1,.note,.controls,.privacy{{display:none}}.stage{{display:block}}
.carousel-slide{{display:block;width:7.5in;height:9.375in;box-shadow:none;border-radius:0;page-break-after:always}}}}
</style>
</head>
<body><main>
<h1>Event visual carousel</h1>
<p class="note">A four-card story built from your selected LinkedIn draft and event details. Review every card before sharing. Nothing is posted.</p>
<div class="stage">{}</div>
<div class="controls"><button class="secondary" id="previous">Previous</button>
<span id="counter"></span><button class="secondary" id="next">Next</button>
<button id="download">Download this card as PNG</button><button id="print">Print / Save as PDF</button></div>
<p class="privacy">Generated locally from the draft. This page does not upload your event details.</p>
</main>
<script>
const slides=[...document.querySelectorAll(".carousel-slide")];let current=0;
function show(index){{current=(index+slides.length)%slides.length;slides.forEach((s,i)=>s.classList.toggle("active",i===current));document.querySelector("#counter").textContent=`Card ${{current+1}} of ${{slides.length}}`;}}
document.querySelector("#previous").onclick=()=>show(current-1);
document.querySelector("#next").onclick=()=>show(current+1);
document.querySelector("#print").onclick=()=>window.print();
document.querySelector("#download").onclick=()=>{{
 const svg=slides[current],source=new XMLSerializer().serializeToString(svg);
 const image=new Image(),url=URL.createObjectURL(new Blob([source],{{type:"image/svg+xml;charset=utf-8"}}));
 image.onload=()=>{{const canvas=document.createElement("canvas");canvas.width=1080;canvas.height=1350;
 canvas.getContext("2d").drawImage(image,0,0);URL.revokeObjectURL(url);
 const link=document.createElement("a");link.download=`event-carousel-card-${{current+1}}.png`;
 link.href=canvas.toDataURL("image/png");link.click();}};
 image.onerror=()=>{{URL.revokeObjectURL(url);alert("Could not render this card. Try Print / Save as PDF.");}};
 image.src=url;
}};
show(0);
</script></body></html>""".format(page_title, rendered_slides)
