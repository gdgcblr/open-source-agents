"""Offline tests: no API key and no Gemini calls needed.

Run from agents/resume-jd-match-agent/:
    python -m unittest discover -s tests -v
"""

import asyncio
import io
import os
import stat
import sys
import tempfile
import time
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from google.adk.models import LlmRequest, LlmResponse  # noqa: E402
from google.genai import types  # noqa: E402

os.environ["RESUME_JD_CACHE"] = "off"  # tests never touch the real report cache
os.environ["RESUME_JD_OCR"] = "off"  # and never call Gemini

from resume_jd_agent import cache, config, documents, guardrails, tools  # noqa: E402


def before(ctx, request):
    return asyncio.run(guardrails.before_model_guardrail(ctx, request))


def after(ctx, response):
    return asyncio.run(guardrails.after_model_guardrail(ctx, response))


RESUME = os.path.join(ROOT, "samples", "sample_resume.txt")
JD = os.path.join(ROOT, "samples", "sample_jd.txt")


def read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def fake_context(state=None):
    """Stands in for ADK's ToolContext / CallbackContext (only .state is used)."""
    return SimpleNamespace(state=state if state is not None else {}, invocation_id="test")


class ToolTests(unittest.TestCase):
    def test_read_resume_txt_path(self):
        result = tools.read_resume(RESUME)
        self.assertEqual(result["status"], "success")
        self.assertIn("PRIYA RAMAN", result["text"])

    def test_read_resume_missing_pdf(self):
        self.assertEqual(tools.read_resume("missing.pdf")["status"], "error")

    def test_long_paste_is_truncated(self):
        result = tools.read_resume("x" * (tools.MAX_DOC_CHARS + 50))
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["text"]), tools.MAX_DOC_CHARS)

    def test_unsupported_upload_type(self):
        self.assertEqual(tools.uploaded_file_to_text(b"x", "image/png")["status"], "error")

    def test_keyword_aliases_and_false_positives(self):
        self.assertEqual(
            tools.extract_keywords("Designed REST endpoints in TS with K8s")["skills"],
            ["kubernetes", "rest api", "typescript"],
        )
        self.assertEqual(tools.extract_keywords("the rest of the learning budget")["skills"], [])

    def test_overlap_on_samples(self):
        overlap = tools.keyword_overlap(tools.read_resume(RESUME)["text"], read(JD))
        self.assertIn("sql", overlap["matched"])
        self.assertIn("a/b testing", overlap["missing"])
        self.assertGreater(overlap["overlap_percent"], 30)


class AnalyzeMatchTests(unittest.TestCase):
    def test_paths_return_text_for_model(self):
        ctx = fake_context()
        result = tools.analyze_match(RESUME, JD, ctx)
        self.assertEqual(result["status"], "success")
        self.assertIn("resume_text", result)  # model has not seen file contents yet
        self.assertIn(tools.RESUME_STATE_KEY, ctx.state)

    def test_upload_reference_does_not_echo_text(self):
        ctx = fake_context({tools.UPLOADS_STATE_KEY: {"cv.pdf": read(RESUME)}})
        result = tools.analyze_match("upload:cv.pdf", read(JD), ctx)
        self.assertEqual(result["status"], "success")
        self.assertNotIn("resume_text", result)  # model already saw the upload
        self.assertNotIn("jd_text", result)

    def test_unknown_upload_name(self):
        result = tools.analyze_match("upload:nope.pdf", read(JD), fake_context())
        self.assertEqual(result["status"], "error")

    def test_jd_without_skills_is_rejected(self):
        result = tools.analyze_match(RESUME, "Hello, how are you today?", fake_context())
        self.assertEqual(result["status"], "error")


def user_request(*parts):
    return LlmRequest(contents=[types.Content(role="user", parts=list(parts))])


def report(after_line):
    text = (
        "\n".join(guardrails.REQUIRED_HEADINGS[:3])
        + f"\n## 4. Bullet Rewrites\n{after_line}\n## 5. Top 3 Fixes Before Applying\n1. a"
    )
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


class GuardrailTests(unittest.TestCase):
    def test_short_first_message_skips_gemini(self):
        response = before(fake_context(), user_request(types.Part(text="hi")))
        self.assertIsNotNone(response)  # answered locally, no API request

    def test_file_path_message_goes_to_gemini(self):
        request = user_request(types.Part(text="Resume: samples/sample_resume.txt"))
        self.assertIsNone(before(fake_context(), request))

    def test_upload_is_converted_and_stored(self):
        ctx = fake_context()
        blob = types.Blob(mime_type="text/plain", data=read(RESUME, "rb"), display_name="cv.txt")
        request = user_request(types.Part(text="see file"), types.Part(inline_data=blob))
        self.assertIsNone(before(ctx, request))
        self.assertIn("<<<DOCUMENT cv.txt>>>", request.contents[0].parts[1].text)
        self.assertIn("cv.txt", ctx.state[tools.UPLOADS_STATE_KEY])

    def test_loop_guard(self):
        ctx = fake_context()
        request = user_request(types.Part(text="x" * 400))
        for _ in range(guardrails.MAX_MODEL_CALLS_PER_TURN):
            self.assertIsNone(before(ctx, request))
        self.assertIsNotNone(before(ctx, request))

    def test_invented_numbers_are_replaced(self):
        ctx = fake_context({tools.RESUME_STATE_KEY: "Reduced overdue invoices by 18% for 6 engineers"})
        line = "**After:** Cut overdue invoices by 18% and grew revenue 35% for 1,200 users, 3x faster"
        out = after(ctx, report(line)).content.parts[0].text
        self.assertIn("by 18%", out)  # real number kept
        self.assertIn("[X%]", out)
        self.assertNotIn("35%", out)
        self.assertNotIn("1,200", out)
        self.assertIn("[N]x", out)

    def test_unsupported_skill_claim_is_flagged(self):
        ctx = fake_context({tools.MISSING_STATE_KEY: ["okrs", "kpis"]})
        text = (
            "## 1. Match Score\n## 4. Bullet Rewrites\n"
            "**Before:** Tracked metrics in Mixpanel.\n**After:** Tracked metrics in Mixpanel for [N] features.\n"
            "**Before:** Shared weekly updates.\n**After:** Defined OKRs and KPIs and shared weekly updates.\n"
        )
        response = LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
        out = after(ctx, response).content.parts[0].text
        self.assertIn("Rewrite 2 adds kpis, okrs", out)
        self.assertNotIn("Rewrite 1 adds", out)

    def test_missing_section_is_flagged(self):
        response = LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="## 1. Match Score\n**80/100**")])
        )
        out = after(fake_context(), response).content.parts[0].text
        self.assertIn("missing sections", out)


def request_with_tool(*parts):
    """A first-turn request that still has the analyze_match tool attached."""
    request = user_request(*parts)
    request.config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(name="analyze_match")])]
    )
    return request


def upload(name, path):
    return types.Part(inline_data=types.Blob(mime_type="text/plain", data=read(path, "rb"), display_name=name))


class FastPathTests(unittest.TestCase):
    """The 1-request path: analysis done in Python, tool removed from the request."""

    def assert_fast_path(self, request, ctx):
        self.assertIsNone(before(ctx, request))
        self.assertIsNone(request.config.tools)  # Gemini cannot call the tool again
        self.assertIn("<<<ANALYSIS>>>", request.contents[-1].parts[-1].text)
        self.assertIn(tools.RESUME_STATE_KEY, ctx.state)  # number guardrail has the resume

    def test_upload_plus_pasted_jd(self):
        ctx = fake_context()
        self.assert_fast_path(request_with_tool(types.Part(text=read(JD)), upload("cv.txt", RESUME)), ctx)

    def test_labelled_file_paths(self):
        ctx = fake_context()
        request = request_with_tool(types.Part(text=f"Resume: {RESUME}\nJob description: {JD}"))
        self.assert_fast_path(request, ctx)
        texts = [p.text for p in request.contents[-1].parts]
        self.assertTrue(any("<<<DOCUMENT resume>>>" in t for t in texts))  # model gets file text once
        self.assertTrue(any("<<<DOCUMENT job_description>>>" in t for t in texts))

    def test_two_uploads_named_by_role(self):
        ctx = fake_context()
        request = request_with_tool(
            types.Part(text="see files"), upload("my_cv.txt", RESUME), upload("job_post.txt", JD)
        )
        self.assert_fast_path(request, ctx)

    def test_missing_file_answered_locally(self):
        request = request_with_tool(types.Part(text="Resume: nope.pdf Job description: nope.txt"))
        response = before(fake_context(), request)
        self.assertIn("couldn't read", response.content.parts[0].text)  # 0 Gemini requests

    def test_ambiguous_message_keeps_tool(self):
        request = request_with_tool(types.Part(text=read(RESUME) + "\n\n" + read(JD)))
        self.assertIsNone(before(fake_context(), request))
        self.assertIsNotNone(request.config.tools)  # model decides via the tool

    def test_follow_up_gets_documents_again(self):
        ctx = fake_context({tools.RESUME_STATE_KEY: "Resume body", tools.JD_STATE_KEY: "JD body"})
        request = request_with_tool(types.Part(text="Resume: a.txt Job description: b.txt"))
        request.contents.append(types.Content(role="model", parts=[types.Part(text="## 1. Match Score")]))
        request.contents.append(
            types.Content(role="user", parts=[types.Part(text="Write a cover letter for this job.")])
        )
        self.assertIsNone(before(ctx, request))
        texts = " ".join(p.text for p in request.contents[-1].parts)
        self.assertIn("<<<DOCUMENT resume>>>\nResume body", texts)
        self.assertIn("<<<DOCUMENT job_description>>>\nJD body", texts)

    def test_upload_parsed_once(self):
        guardrails._upload_text.cache_clear()
        for _ in range(3):
            before(fake_context(), user_request(types.Part(text="x"), upload("cv.txt", RESUME)))
        self.assertEqual(guardrails._upload_text.cache_info().misses, 1)


def make_docx(paragraphs, preamble=""):
    """Builds a minimal .docx in memory (a zip with word/document.xml)."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        doc_xml = f'{preamble}<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
        archive.writestr("word/document.xml", doc_xml)
    return buffer.getvalue()


class DocumentTests(unittest.TestCase):
    def test_docx_upload(self):
        result = tools.uploaded_file_to_text(make_docx(["Jane Doe", "Built React apps"]), documents.DOCX_MIME)
        self.assertEqual(result["text"], "Jane Doe\nBuilt React apps")

    def test_docx_path(self):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(make_docx(["Python and SQL"]))
        self.addCleanup(os.remove, f.name)
        self.assertIn("python", tools.extract_keywords(tools.read_resume(f.name)["text"])["skills"])

    def test_legacy_doc_rejected_not_read_as_text(self):
        result = tools.read_resume("old_cv.doc")
        self.assertEqual(result["status"], "error")
        self.assertIn("Unsupported file type", result["error_message"])

    def test_broken_docx(self):
        self.assertEqual(tools.uploaded_file_to_text(b"not a zip", documents.DOCX_MIME)["status"], "error")

    def test_pdf_text_repair(self):
        repaired = documents.repair_pdf_text("de\x1cning work\x1dows o\x1fine e\x1bort, T esting W ebpack. I am A team")
        self.assertEqual(repaired, "defining workflows offline effort, Testing Webpack. I am A team")

    def test_scanned_pdf_without_ocr(self):
        blank = documents.markdown_to_pdf("")  # a PDF with no body text
        result = documents.read_pdf_bytes(blank)
        self.assertEqual(result["status"], "error")
        self.assertIn("scanned", result["error_message"])

    def test_pdf_export_round_trip(self):
        from pypdf import PdfReader

        pdf = documents.markdown_to_pdf("## 1. Match Score\n**80/100** - good fit\n- React → Next.js")
        text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
        self.assertIn("1. Match Score", text)
        self.assertIn("80/100 - good fit", text)
        self.assertIn("React -> Next.js", text)

    def test_long_report_paginates(self):
        from pypdf import PdfReader

        pdf = documents.markdown_to_pdf("\n".join(f"- line {i}" for i in range(200)))
        self.assertGreater(len(PdfReader(io.BytesIO(pdf)).pages), 1)


class JdTermTests(unittest.TestCase):
    def test_terms_outside_skill_list(self):
        jd = (
            "About us\n- Experience with Stripe or Razorpay.\n"
            "- Hands-on AWS (EC2, IAM, RDS).\n- HIPAA and SOC 2 exposure."
        )
        terms = tools.jd_specific_terms(jd)
        for expected in ["Stripe", "Razorpay", "EC2", "IAM", "RDS", "HIPAA", "SOC"]:
            self.assertIn(expected, terms)
        self.assertNotIn("AWS", terms)  # already a known skill
        self.assertNotIn("Experience", terms)  # sentence-case first word

    def test_missing_terms_in_overlap(self):
        overlap = tools.keyword_overlap(read(RESUME), read(JD))
        self.assertEqual(overlap["jd_terms_not_in_resume"], ["Razorpay", "Stripe"])


class RankingTests(unittest.TestCase):
    def test_rank_puts_best_first_and_analyses_it(self):
        frontend = os.path.join(ROOT, "samples", "sample_jd_frontend.txt")
        ctx = fake_context()
        result = tools.rank_job_descriptions(RESUME, [frontend, JD], ctx)
        self.assertEqual(result["best_jd"], "sample_jd.txt")
        self.assertEqual([r["rank"] for r in result["ranking"]], [1, 2])
        self.assertEqual(result["best"]["status"], "success")
        self.assertIn(tools.RESUME_STATE_KEY, ctx.state)

    def test_rank_needs_two_jds(self):
        self.assertEqual(tools.rank_job_descriptions(RESUME, [JD], fake_context())["status"], "error")


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_dir, cache.CACHE_DIR = cache.CACHE_DIR, self.tmp
        os.environ["RESUME_JD_CACHE"] = "on"

    def tearDown(self):
        cache.CACHE_DIR = self.old_dir
        os.environ["RESUME_JD_CACHE"] = "off"

    def test_round_trip_and_whitespace_insensitive_key(self):
        key = cache.key_for("Resume  text\n", "JD text")
        self.assertEqual(key, cache.key_for("Resume text", "JD   text"))
        cache.put(key, "## 1. Match Score")
        self.assertEqual(cache.get(key), "## 1. Match Score")

    def test_cached_report_skips_gemini(self):
        ctx = fake_context()
        tools.analyze_match(RESUME, JD, ctx)
        cache.put(ctx.state[tools.CACHE_KEY_STATE], "## 1. Match Score\n**70/100** - cached")
        request = request_with_tool(types.Part(text=f"Resume: {RESUME}\nJob description: {JD}"))
        response = before(fake_context(), request)
        self.assertIn("cached", response.content.parts[0].text)  # answered with 0 requests

    def test_disabled(self):
        os.environ["RESUME_JD_CACHE"] = "off"
        cache.put("k", "report")
        self.assertIsNone(cache.get("k"))

    def test_cache_file_permissions(self):
        key = cache.key_for("Test permissions", "JD text")
        cache.put(key, "Report with sensitive data")
        path = cache._path(key)
        self.assertTrue(os.path.exists(path))
        mode = stat.S_IMODE(os.stat(path).st_mode)
        self.assertEqual(mode, 0o600)  # readable and writable only by user

    def test_cache_pruning(self):
        key = cache.key_for("Old resume", "Old JD")
        cache.put(key, "Old report")
        path = cache._path(key)
        self.assertTrue(os.path.exists(path))
        # Set file modification time to 31 days ago
        old_time = time.time() - (31 * 24 * 3600)
        os.utime(path, (old_time, old_time))
        pruned = cache.prune(max_age_seconds=30 * 24 * 3600)
        self.assertGreaterEqual(pruned, 1)
        self.assertFalse(os.path.exists(path))

    def test_cache_key_includes_model(self):
        k1 = cache.key_for("Resume text", "JD text", model="gemini-3.8-flash")
        k2 = cache.key_for("Resume text", "JD text", model="gemini-1.5-pro")
        self.assertNotEqual(k1, k2)


class OutputGuardrailTests(unittest.TestCase):
    def test_numbers_compared_by_value(self):
        ctx = fake_context({tools.RESUME_STATE_KEY: "Served 1,500 users and cut costs by $2M"})
        out = after(ctx, report("**After:** Served 1.5k users, saved $2 million and $3M")).content.parts[0].text
        self.assertIn("1.5k users", out)  # same value as 1,500
        self.assertIn("$2 million", out)  # same value as $2M
        self.assertNotIn("$3M", out)

    def test_cover_letter_numbers_scrubbed(self):
        ctx = fake_context({tools.RESUME_STATE_KEY: "Reduced overdue invoices by 18%"})
        letter = "## Cover Letter\nDear [Hiring Manager],\nI reduced overdue invoices by 18% and grew revenue 40%."
        response = LlmResponse(content=types.Content(role="model", parts=[types.Part(text=letter)]))
        out = after(ctx, response).content.parts[0].text
        self.assertIn("by 18%", out)
        self.assertIn("[X%]", out)
        self.assertNotIn("40%", out)


class SecurityTests(unittest.TestCase):
    def test_file_paths_disabled(self):
        with patch.dict(os.environ, {config.ALLOW_FILE_PATHS_ENV: "off"}):
            result = tools.read_resume(RESUME)
            self.assertEqual(result["status"], "error")
            self.assertIn("disabled", result["error_message"].lower())

    def test_allowed_folders_permitted(self):
        samples_dir = os.path.dirname(RESUME)
        with patch.dict(os.environ, {config.ALLOWED_DIRS_ENV: samples_dir}):
            result = tools.read_resume(RESUME)
            self.assertEqual(result["status"], "success")

    def test_allowed_folders_rejected(self):
        with tempfile.TemporaryDirectory() as safe_dir:
            with patch.dict(os.environ, {config.ALLOWED_DIRS_ENV: safe_dir}):
                result = tools.read_resume(RESUME)
                self.assertEqual(result["status"], "error")
                self.assertIn("outside allowed folders", result["error_message"])

    def test_path_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as safe_dir:
            traversal_path = os.path.join(safe_dir, "..", "..", os.path.basename(RESUME))
            with patch.dict(os.environ, {config.ALLOWED_DIRS_ENV: safe_dir}):
                self.assertFalse(documents.is_path_allowed(traversal_path))

    def test_docx_entity_guard(self):
        xxe_preamble = '<!DOCTYPE test [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>'
        malicious_docx = make_docx(["Testing"], preamble=xxe_preamble)
        result = tools.uploaded_file_to_text(malicious_docx, documents.DOCX_MIME)
        self.assertEqual(result["status"], "error")
        self.assertIn("entity declarations", result["error_message"].lower())


class ReliabilityTests(unittest.TestCase):
    def test_before_guardrail_exception_resilience(self):
        ctx = fake_context()
        request = user_request(types.Part(text="Resume: a.txt Job description: b.txt"))
        with patch("resume_jd_agent.guardrails._convert_uploads", side_effect=RuntimeError("Unexpected")):
            # Must not raise; should return None and let request proceed
            response = before(ctx, request)
            self.assertIsNone(response)

    def test_after_guardrail_exception_resilience(self):
        ctx = fake_context()
        raw_response = LlmResponse(content=types.Content(role="model", parts=[types.Part(text="## 1. Match Score")]))
        with patch("resume_jd_agent.guardrails._scrub_invented_numbers", side_effect=RuntimeError("Unexpected")):
            # Must not raise; should return raw_response
            response = after(ctx, raw_response)
            self.assertEqual(response, raw_response)

    def test_analyze_match_exception_resilience(self):
        ctx = fake_context()
        with patch("resume_jd_agent.tools._resolve_document", side_effect=Exception("Disk failure")):
            result = tools.analyze_match(RESUME, JD, ctx)
            self.assertEqual(result["status"], "error")
            self.assertIn("Unable to analyze match", result["error_message"])

    def test_rank_job_descriptions_exception_resilience(self):
        ctx = fake_context()
        with patch("resume_jd_agent.tools._resolve_document", side_effect=Exception("Disk failure")):
            result = tools.rank_job_descriptions(RESUME, [JD, JD], ctx)
            self.assertEqual(result["status"], "error")
            self.assertIn("Unable to rank", result["error_message"])


if __name__ == "__main__":
    unittest.main()
