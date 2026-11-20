"""
KabQue Assistant — a read-only chatbot for freshers (free Groq API version).

Wire it up in urls.py:

    from .chatbot import ChatView
    path("chat/", ChatView.as_view(), name="chat"),

Env vars (backend/.env locally, Render dashboard in production — never in the frontend):
    GROQ_API_KEY=gsk_...
    CHATBOT_MODEL=openai/gpt-oss-120b     # optional; see console.groq.com/docs/models
"""

import json
import logging
import os

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import CampusSettings
from .notifications import required_documents_payload
from .views import (
    build_student_day_progress,
    get_queue_entry,
    has_batch_queue_number,
    waiting_ahead_count,
)

log = logging.getLogger(__name__)

MODEL = os.getenv("CHATBOT_MODEL", "openai/gpt-oss-120b")
MAX_HISTORY = 12          # messages kept from the browser
MAX_USER_CHARS = 1000     # per message
MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """You are KabQue Assistant, the help desk for KabQue — Kabale University's
digital queue for fresher registration at Kikungiri Campus.

How KabQue works:
1. The fresher creates an account with their registration number and completes their profile
   (full name, faculty, programme, email and phone).
2. They join the digital queue from campus — the browser checks GPS and they must be inside the
   campus zone.
3. They wait digitally. A University supervisor schedules students in batches by desk capacity.
4. Scheduled students get a date, queue number and secret code by SMS and/or email, and also see
   them on the dashboard.
5. On the day, they report to the desk, give the secret code, and staff verify documents.
6. Students who are not completed can be rescheduled without starting again.

Rules:
- Use the tools to look up the student's real status. Never guess positions, dates or outcomes.
- You cannot change anything. For leaving the queue, rescheduling or editing the profile, tell the
  student which button on their dashboard to use.
- Document approval, admission, fees and registration decisions belong to University staff only.
  Never promise an outcome. Refer those questions to the Academic Registrar's office.
- Never ask for or repeat passwords. The secret code is shown on the student's own dashboard;
  tell them to look there rather than reading it out.
- Keep answers short and simple; many students are on phones with limited data.
- If you don't know, say so and suggest the campus help desk."""

NO_ARGS = {"type": "object", "properties": {}}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_my_queue_status",
            "description": "Current queue status of the signed-in student: whether they are "
            "in the queue, status, students ahead, scheduled date, batch number, desk outcome.",
            "parameters": NO_ARGS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_required_documents",
            "description": "Checklist of documents to bring to the registration desk.",
            "parameters": NO_ARGS,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_campus_zone",
            "description": "Name and radius of the campus zone the student must be inside "
            "to join the queue.",
            "parameters": NO_ARGS,
        },
    },
]


def _queue_status(user) -> dict:
    """Same facts as StudentQueueStatusView, minus anything sensitive."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return {"error": "not_a_student"}

    entry = get_queue_entry(profile)
    data = {
        "profile_complete": profile.is_profile_complete,
        "first_name": (profile.full_name or "").split(" ")[0],
        "in_queue": bool(entry),
        "desk_outcome": profile.desk_outcome or None,
    }
    if entry:
        has_number = has_batch_queue_number(entry)
        data.update(
            {
                "status": entry.get_status_display(),
                "students_ahead_waiting": waiting_ahead_count(entry),
                "has_batch_number": has_number,
                "batch_queue_number": entry.position if has_number else None,
                "scheduled_date": entry.scheduled_date.isoformat()
                if entry.scheduled_date
                else None,
                "has_secret_code": bool(entry.secret_code),  # never the code itself
                "day_progress": build_student_day_progress(entry),
            }
        )
    return data


def _run_tool(name: str, user) -> dict:
    if name == "get_my_queue_status":
        return _queue_status(user)
    if name == "get_required_documents":
        return {"documents": required_documents_payload()}
    if name == "get_campus_zone":
        c = CampusSettings.get_solo()
        return {"campus": c.name, "radius_meters": c.radius_meters}
    return {"error": f"unknown tool {name}"}


def _clean_history(raw) -> list:
    """Accept only {role, content:str} pairs from the browser."""
    out = []
    for m in (raw or [])[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        text = m.get("content") or ""
        if role in ("user", "assistant") and isinstance(text, str) and text.strip():
            out.append({"role": role, "content": text[:MAX_USER_CHARS]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


class ChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat"

    def post(self, request):
        history = _clean_history(request.data.get("messages"))
        if not history or history[-1]["role"] != "user":
            return Response({"detail": "Send a message."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from groq import Groq
        except ImportError:
            log.error("Chat: the 'groq' package is not installed on this server.")
            return Response({"detail": "Chat is not configured."}, status=503)

        if not os.getenv("GROQ_API_KEY"):
            log.error("Chat: GROQ_API_KEY is not set on this server.")
            return Response({"detail": "Chat is not configured."}, status=503)

        client = Groq()  # reads GROQ_API_KEY
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    max_tokens=1500,
                    temperature=0.3,
                    # gpt-oss "thinks" before answering; keep that short and fast.
                    extra_body={"reasoning_effort": "low"},
                )
                msg = resp.choices[0].message
                if not msg.tool_calls:
                    break
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments or "{}",
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
                for tc in msg.tool_calls:
                    result = _run_tool(tc.function.name, request.user)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
        except Exception:
            log.exception("Chat: Groq call failed (model=%s)", MODEL)
            return Response(
                {"detail": "The assistant is busy. Please try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        reply = (msg.content or "").strip()
        return Response({"reply": reply or "Sorry, I couldn't answer that."})