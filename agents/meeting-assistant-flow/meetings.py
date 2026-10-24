"""Meeting workflow: drafts -> MCP slots -> preview -> explicit approval -> Calendar."""

import asyncio
from datetime import datetime, timezone, timedelta
import secrets
import os
import time

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, session, url_for

from agent import prepare_agenda, interpret_request
from calendar_api import BookingUncertain, CalendarError
from guardrails import check_text, check_private_request, validate_meeting
from mcp_client import get_slots
from scheduling import aware_datetime
from chat import meeting_request

meetings = Blueprint("meetings", __name__, url_prefix="/meetings")


def store():
    return current_app.extensions["store"]


def calendar():
    return current_app.extensions["calendar"]


@meetings.before_request
def authenticated():
    if not g.user:
        abort(401, description="Sign in with Google to prepare a meeting.")


def draft(draft_id):
    try:
        return store().get(draft_id, g.user["id"])
    except LookupError:
        abort(404, description="Meeting draft not found.")


def matching_version(item):
    if request.form.get("version") != str(item["version"]):
        abort(409, description="This meeting changed. Reload and review the current version.")


def editable(item):
    matching_version(item)
    if item["status"] not in {"draft", "ready"} or item["data"].get("attempted"):
        abort(409, description="This invitation is locked. Check its operation status, or start a separate meeting.")


def show(item):
    session["draft_id"] = item["id"]
    return redirect(url_for("index") + "#meeting")


@meetings.post("/new")
def new():
    try:
        meeting = validate_meeting(request.form)
    except ValueError as error:
        abort(400, description=str(error))
    item = store().create(g.user["id"], {"meeting": meeting})
    current_app.logger.info("request=%s stage=draft status=created", g.request_id)
    return show(item)


@meetings.post("/chat")
def chat_message():
    if not store().calendar_connected(g.user["id"]):
        abort(400, description="Connect Google Calendar first. Then send your meeting request.")
    if os.getenv("GOOGLE_API_KEY"):
        return conversation_message()
    if session.get("draft_id"):
        abort(409, description="Use Start another meeting before sending a new request.")
    try:
        meeting = meeting_request(request.form.get("message", ""))
    except ValueError as error:
        abort(400, description=str(error))
    note = "A basic description and agenda were filled from your meeting name. Review or edit them before sending."
    if os.getenv("GOOGLE_API_KEY"):
        try:
            proposal = asyncio.run(prepare_agenda({"title": meeting["title"], "duration": meeting["duration"], "purpose": "", "agenda": ""},
                                                 "Prepare a complete description and agenda from the meeting name. Do not invent facts."))
            agenda_text = check_text(proposal["agenda"], 4000)
            purpose_text = check_text(proposal.get("purpose", ""), 2000)
            if not agenda_text:
                raise ValueError("Empty agenda")
            meeting["agenda"] = agenda_text
            meeting["purpose"] = purpose_text or meeting["purpose"]
            note = "I drafted the meeting details with Gemini. Review or edit before sending."
            current_app.logger.info("request=%s stage=automatic_agenda status=completed", g.request_id)
        except Exception:
            note = "Gemini was unavailable. A basic description and agenda were filled from the name; review or edit before sending."
            current_app.logger.warning("request=%s stage=automatic_agenda status=fallback", g.request_id)
    item = store().create(g.user["id"], {"meeting": meeting, "automatic": True, "preparation_note": note,
                                        "request": request.form["message"].strip()})
    session["draft_id"] = item["id"]
    current_app.logger.info("request=%s stage=planning status=prepared", g.request_id)
    return search_slots(item)


def conversation_message():
    item = draft(session["draft_id"]) if session.get("draft_id") else None
    if item:
        editable(item)
    try:
        text = check_text(request.form.get("message", ""), 2000)
        check_private_request(text)
        if not text:
            raise ValueError("Enter a message.")
    except ValueError as error:
        abort(400, description=str(error))
    turns = item["data"].get("messages", []) if item else []
    if len(turns) >= 12:
        abort(400, description="Start a new chat to continue; this conversation has reached its limit.")
    turns = [*turns, {"role": "user", "text": text}]
    try:
        async def query_calendars(meeting):
            result = calendar().availability(g.user["id"], meeting)
            slots = await get_slots(meeting, result["busy"])
            current_app.logger.info("request=%s stage=agent_scheduling_tool status=completed unknown=%d", g.request_id, result["unknown"])
            return {"result": result, "slots": slots}
        plan = asyncio.run(interpret_request(turns, query_calendars))
    except Exception:
        current_app.logger.warning("request=%s stage=chat_interpretation status=failed", g.request_id)
        abort(502, description="Gemini could not understand the request. Check your API key, quota, or model access and try again.")
    question = plan.get("question", "")
    if not plan.get("attendees"):
        question = question or "What is the invitee's email address?"
    elif not plan.get("date"):
        question = "Which date should I check?"
    elif plan["intent"] == "check_time" and not plan.get("time"):
        question = "What time should I check, including AM or PM?"
    elif plan["intent"] == "clarify":
        question = question or "Would you like me to check availability or prepare a meeting?"
    meeting = {"title": "Meeting", "purpose": "", "agenda": "", "attendees": [], "duration": 30,
               "date_from": datetime.now(timezone.utc).date().isoformat(), "date_to": datetime.now(timezone.utc).date().isoformat(),
               "timezone": "Asia/Kolkata", "hour_start": 9, "hour_end": 17, "include_weekends": True}
    preferred = None
    if not question:
        try:
            meeting = validate_meeting({**meeting, "title": plan["title"] or "Call", "purpose": plan["purpose"],
                "agenda": plan["agenda"] or "Discuss goals, decisions, and next steps.",
                "attendees": ", ".join(plan["attendees"]), "date_from": plan["date"], "date_to": plan["date"],
                "duration": plan["duration"], "timezone": plan["timezone"]})
            if plan.get("time"):
                import re
                from zoneinfo import ZoneInfo
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", plan["time"]):
                    raise ValueError("Please specify the time with AM/PM, for example 3 PM.")
                start = datetime.fromisoformat(plan["date"] + "T" + plan["time"]).replace(tzinfo=ZoneInfo(meeting["timezone"]))
                if start <= datetime.now(timezone.utc) or (start + timedelta(minutes=meeting["duration"])).date() != start.date():
                    raise ValueError("Choose a future time with the meeting ending on the same date.")
                preferred = {"start": start.isoformat(), "end": (start + timedelta(minutes=meeting["duration"])).isoformat()}
        except (ValueError, KeyError) as error:
            question = str(error) if isinstance(error, ValueError) else "Please provide a date and invitee email."
    data = {"meeting": meeting, "automatic": True, "messages": turns, "intent": plan["intent"], "preferred": preferred}
    if question:
        data["messages"].append({"role": "assistant", "text": check_text(question, 2000)})
    if item:
        item = store().update(item["id"], g.user["id"], item["version"], data)
    else:
        item = store().create(g.user["id"], data)
    session["draft_id"] = item["id"]
    current_app.logger.info("request=%s stage=chat status=%s", g.request_id, "clarification" if question else "querying_calendars")
    if question:
        return show(item)
    verified = plan.get("_tool_result")
    keys = ("attendees", "date_from", "date_to", "timezone", "duration")
    if not verified or any(verified["meeting"][key] != meeting[key] for key in keys):
        abort(502, description="The agent did not complete a matching Calendar check. Ask again; no invitation was sent.")
    return search_slots(item, verified)


@meetings.get("/<draft_id>")
def open_draft(draft_id):
    return show(draft(draft_id))


@meetings.post("/<draft_id>/save")
def save(draft_id):
    item = draft(draft_id)
    editable(item)
    try:
        meeting = validate_meeting(request.form)
        updated = store().update(draft_id, g.user["id"], item["version"], {"meeting": meeting, "automatic": item["data"].get("automatic", False)})
    except ValueError as error:
        abort(400, description=str(error))
    current_app.logger.info("request=%s stage=draft status=updated", g.request_id)
    return search_slots(updated) if updated["data"].get("automatic") else show(updated)


@meetings.post("/<draft_id>/agenda")
def agenda(draft_id):
    item = draft(draft_id)
    editable(item)
    if request.form.get("ai_consent") != "yes":
        abort(400, description="Approve sending this draft's title, purpose, agenda, and instruction to Gemini first.")
    try:
        instruction = check_text(request.form.get("message", "Prepare a concise agenda."), 1000)
        proposal = asyncio.run(prepare_agenda(item["data"]["meeting"], instruction))
        # Never trust model output as storage-ready or as an instruction to act.
        meeting = dict(item["data"]["meeting"])
        meeting["title"] = check_text(proposal["title"], 120)
        meeting["agenda"] = check_text(proposal["agenda"], 4000)
        reply = check_text(proposal["reply"], 1000)
        if not meeting["title"] or not meeting["agenda"]:
            raise ValueError("The agent returned an incomplete agenda. Try again or enter one manually.")
        updated = store().update(draft_id, g.user["id"], item["version"], {"meeting": meeting, "reply": reply})
    except ValueError as error:
        # Only local guardrail messages are safe to display, never model/provider exceptions.
        if str(error).startswith(("Set GOOGLE_API_KEY", "Possible secret", "Other people's", "Use text", "The agent returned")):
            abort(400, description=str(error))
        abort(502, description="The agenda response could not be validated. Try again or enter the agenda manually.")
    except Exception:
        current_app.logger.warning("request=%s stage=agenda status=failed", g.request_id)
        abort(502, description="Gemini could not prepare the agenda. Check your local API key and model access, or enter it manually.")
    current_app.logger.info("request=%s stage=agenda status=completed", g.request_id)
    return show(updated)


@meetings.post("/<draft_id>/slots")
def slots(draft_id):
    item = draft(draft_id)
    editable(item)
    return search_slots(item)


def search_slots(item, verified=None):
    if not store().calendar_connected(g.user["id"]):
        abort(400, description="Connect Google Calendar before looking for times.")
    try:
        validate_meeting({**item["data"]["meeting"], "attendees": ", ".join(item["data"]["meeting"]["attendees"])})
        result = verified["result"] if verified else calendar().availability(g.user["id"], item["data"]["meeting"])
        candidates = verified["slots"] if verified else asyncio.run(get_slots(item["data"]["meeting"], result["busy"]))
        data = {**{key: item["data"][key] for key in ("automatic", "preparation_note", "request", "messages", "intent", "preferred") if key in item["data"]},
                "meeting": item["data"]["meeting"], "slots": candidates,
                "unknown": result["unknown"], "checks": result.get("checks", []), "checked_at": time.time()}
        preferred = data.get("preferred")
        available = False
        if preferred:
            start, end = aware_datetime(preferred["start"]), aware_datetime(preferred["end"])
            conflict = any(start < aware_datetime(period["end"]) and end > aware_datetime(period["start"]) for period in result["busy"])
            available = not conflict and start > datetime.now(timezone.utc)
            answer = ("That time conflicts with a busy period on a checked calendar." if conflict else
                      "I cannot confirm that time: some invitee availability is unknown." if result["unknown"] else
                      "The checked calendars are free for the requested time.")
            if available:
                data["slots"] = [preferred, *[slot for slot in candidates if slot != preferred]][:6]
        else:
            answer = ("Some invitee availability is unknown. These slots are tentative." if result["unknown"] else
                      "Here are shared free slots." if candidates else "No shared free slots were found in the working hours.")
        if data.get("messages") is not None:
            data["messages"].append({"role": "assistant", "text": answer})
        status = "draft"
        if data.get("intent") == "schedule" and preferred and available and not result["unknown"]:
            data["selected"] = preferred
            data["review_token"] = secrets.token_urlsafe(32)
            status = "ready"
        updated = store().update(item["id"], g.user["id"], item["version"], data, status)
    except CalendarError as error:
        abort(502, description=str(error))
    except Exception:
        current_app.logger.warning("request=%s stage=slot_search status=failed", g.request_id)
        abort(502, description="Slot search failed. Check the date range, working hours, and Calendar connection.")
    current_app.logger.info("request=%s stage=slot_search status=completed candidates=%d unknown=%d",
                            g.request_id, len(candidates), result["unknown"])
    return show(updated)


@meetings.post("/<draft_id>/preview")
def preview(draft_id):
    item = draft(draft_id)
    editable(item)
    data = item["data"]
    if time.time() - data.get("checked_at", 0) > 1800:
        abort(409, description="Time suggestions expired. Find available times again.")
    try:
        index = int(request.form.get("slot", ""))
        if index < 0:
            raise ValueError
        selected = data["slots"][index]
        if aware_datetime(selected["start"]) <= datetime.now(timezone.utc):
            raise ValueError
    except (ValueError, KeyError, IndexError):
        abort(400, description="Choose one of the current future time suggestions.")
    if not data["meeting"]["agenda"].strip():
        abort(400, description="Write or generate an agenda, save it, then find times again.")
    data["selected"] = selected
    data["review_token"] = secrets.token_urlsafe(32)
    item = store().update(draft_id, g.user["id"], item["version"], data, "ready")
    current_app.logger.info("request=%s stage=preview status=ready", g.request_id)
    return redirect(url_for("meetings.review", draft_id=draft_id))


@meetings.get("/<draft_id>/review")
def review(draft_id):
    item = draft(draft_id)
    if not item["data"].get("selected"):
        return show(item)
    session["draft_id"] = item["id"]
    return current_app.view_functions["index"]()


@meetings.post("/<draft_id>/confirm")
def confirm(draft_id):
    item = draft(draft_id)
    if item["status"] in {"created", "cancelled"}:
        return redirect(url_for("meetings.review", draft_id=draft_id))
    matching_version(item)
    data = item["data"]
    token = request.form.get("review_token", "")
    if (item["status"] != "ready" or not token or not data.get("review_token")
            or not secrets.compare_digest(token, data["review_token"]) or request.form.get("approved") != "yes"):
        abort(409, description="Review the current invitation and explicitly approve sending it.")
    if not store().calendar_connected(g.user["id"]) or not store().calendar_writable(g.user["id"]):
        abort(403, description="Enable scheduling and approve Calendar event access first.")
    if data.get("unknown", 0) and request.form.get("ack_unknown") != "yes":
        abort(400, description="Acknowledge that some attendees' availability is unknown before sending invitations.")
    try:
        store().claim(draft_id, g.user["id"], item["version"])
    except ValueError:
        abort(409, description="Creation is already in progress. Check this meeting's status.")
    try:
        selected = data["selected"]
        start, end = aware_datetime(selected["start"]), aware_datetime(selected["end"])
        result = calendar().availability(g.user["id"], data["meeting"])
        conflict = start <= datetime.now(timezone.utc) or any(
            start < aware_datetime(period["end"]) and end > aware_datetime(period["start"]) for period in result["busy"])
        if conflict or result["unknown"] > data.get("unknown", 0):
            if data.get("attempted"):
                store().finish(draft_id, g.user["id"], data, "unknown")
            else:
                store().finish(draft_id, g.user["id"], {"meeting": data["meeting"]}, "draft")
            abort(409, description="Availability changed or the time passed. Check status or find new times before approving again.")
    except CalendarError as error:
        store().finish(draft_id, g.user["id"], data, "ready")
        abort(502, description=str(error))
    except Exception as error:
        from werkzeug.exceptions import HTTPException
        if isinstance(error, HTTPException):
            raise
        store().finish(draft_id, g.user["id"], data, "ready")
        abort(502, description="Could not recheck availability. No creation request was sent.")

    # Persist that a write is being attempted before crossing the network boundary.
    data["attempted"] = True
    try:
        store().begin_submission(draft_id, g.user["id"], item["version"], data)
    except ValueError:
        abort(409, description="Operation status changed during recheck. Review its current status before retrying.")
    try:
        event = calendar().create(g.user["id"], draft_id, data["meeting"], selected)
    except BookingUncertain:
        store().finish(draft_id, g.user["id"], data, "unknown")
        current_app.logger.warning("request=%s stage=calendar_create status=unknown", g.request_id)
        return redirect(url_for("meetings.review", draft_id=draft_id))
    except CalendarError as error:
        # A definite provider rejection allows re-review/retry of the same immutable invitation.
        store().finish(draft_id, g.user["id"], data, "ready")
        abort(502, description=str(error))
    except Exception:
        store().finish(draft_id, g.user["id"], data, "unknown")
        current_app.logger.warning("request=%s stage=calendar_create status=unknown", g.request_id)
        return redirect(url_for("meetings.review", draft_id=draft_id))
    data["event"] = event
    store().finish(draft_id, g.user["id"], data, "cancelled" if event.get("cancelled") else "created")
    current_app.logger.info("request=%s stage=calendar_create status=confirmed", g.request_id)
    return redirect(url_for("meetings.review", draft_id=draft_id))


@meetings.post("/<draft_id>/reconcile")
def reconcile(draft_id):
    item = draft(draft_id)
    if item["status"] == "creating" and time.time() - item["updated"] < 60:
        abort(409, description="Creation is still in progress. Wait a moment before checking status.")
    if item["status"] not in {"unknown", "creating"}:
        return redirect(url_for("meetings.review", draft_id=draft_id))
    try:
        event = calendar().lookup(g.user["id"], draft_id)
    except Exception:
        abort(502, description="Could not verify the calendar operation. Keep this draft and check status again later.")
    data = item["data"]
    if event:
        data["event"] = event
        status = "cancelled" if event.get("cancelled") else "created"
    else:
        # Keep the snapshot locked; retries use exactly the same Google event ID.
        data["attempted"] = True
        data["review_token"] = secrets.token_urlsafe(32)
        status = "ready"
    store().finish(draft_id, g.user["id"], data, status)
    current_app.logger.info("request=%s stage=calendar_reconcile status=%s", g.request_id, status)
    return redirect(url_for("meetings.review", draft_id=draft_id))
