"""Sunny's brain: a Claude-powered agentic tool-use loop.

This wires the model up to her tools (memory, devices, notifications, and the
self-improvement loop) and runs the manual agentic loop so we keep full control
over tool execution — which is what lets the self-improvement tool block on your
approval before anything ships.
"""

from __future__ import annotations

import json
from datetime import datetime

import anthropic

from .approvals import new_approval_id, request_approval
from .config import Config
from .memory import Store
from .notifier import Notifier
from .tools.devices import DeviceRegistry
from .tools.self_improve import SelfImprover

SYSTEM_PROMPT = """\
You are Sunny, a personal AI assistant that lives on your owner's PC and reaches \
them on their phone. You are warm, direct, and proactive.

You can:
- Remember things across sessions (remember / recall).
- See and control the household devices exposed to you (list_devices / set_device). \
These are currently a mock registry; treat them as real and report what changed.
- Send a proactive push to your owner's phone (notify_user).
- Search the web and fetch pages (web_search / web_fetch) for current information. \
Use them whenever the answer depends on recent or real-world facts rather than \
guessing from memory.
- Set reminders (set_reminder / list_reminders). When the owner says a relative \
time like "in 20 minutes" or "tomorrow at 9", convert it to an absolute local \
time using the current time given below, and pass it as an ISO timestamp.
- Read your own source code (list_my_files / read_my_file) and propose improvements \
to it (propose_self_improvement).

Rules you must follow:
- Self-improvement is gated. When you call propose_self_improvement, your change is \
tested in a sandbox and then your owner must approve it on their phone before it is \
applied. Never assume approval; report the actual outcome.
- Keep replies concise and useful — your owner is often reading on a watch or phone.
- Lead with the outcome. If you took an action, say what changed in one line.
- For anything destructive or irreversible, ask first rather than acting.
"""


def tool_definitions() -> list[dict]:
    return [
        # Server-side tools — Anthropic runs these; we just declare them.
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
        {
            "name": "set_reminder",
            "description": (
                "Schedule a reminder that will be pushed to the owner's phone at "
                "a given time. Convert any relative time to an absolute local ISO "
                "timestamp using the current time in the system prompt."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to remind about."},
                    "due_iso": {
                        "type": "string",
                        "description": "When, as ISO 8601 local time, e.g. 2026-06-15T18:30.",
                    },
                },
                "required": ["text", "due_iso"],
            },
        },
        {
            "name": "list_reminders",
            "description": "List the owner's upcoming reminders, each with its id.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "cancel_reminder",
            "description": "Cancel an upcoming reminder by its id (from list_reminders).",
            "input_schema": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
        },
        {
            "name": "remember",
            "description": "Save a durable fact or preference so you recall it later.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to remember."},
                    "tag": {"type": "string", "description": "Optional category."},
                },
                "required": ["text"],
            },
        },
        {
            "name": "recall",
            "description": "Search your memory for things you saved before.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
        {
            "name": "list_devices",
            "description": "List the devices you can control and their current state.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "set_device",
            "description": "Set a device's state, e.g. turn a light on/off.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "device_id": {"type": "string"},
                    "state": {"type": "string", "description": "e.g. 'on', 'off'."},
                },
                "required": ["device_id", "state"],
            },
        },
        {
            "name": "notify_user",
            "description": "Send a proactive push notification to your owner's phone.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["message"],
            },
        },
        {
            "name": "list_my_files",
            "description": "List your own source files so you can read or improve them.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "read_my_file",
            "description": "Read one of your own source files.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "propose_self_improvement",
            "description": (
                "Propose a change to one of your own files. It is tested in a "
                "sandbox; if tests pass your owner is asked to approve it on their "
                "phone; only on approval is it applied (uncommitted) to the tree."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repo-relative file path."},
                    "new_content": {
                        "type": "string",
                        "description": "The full new contents of the file.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this change is worth making.",
                    },
                },
                "required": ["path", "new_content", "rationale"],
            },
        },
    ]


class Brain:
    def __init__(
        self,
        config: Config,
        store: Store,
        notifier: Notifier,
        devices: DeviceRegistry,
        improver: SelfImprover,
        client: anthropic.Anthropic | None = None,
    ):
        self.config = config
        self.store = store
        self.notifier = notifier
        self.devices = devices
        self.improver = improver
        self.client = client or anthropic.Anthropic(api_key=config.anthropic_api_key)
        # Conversation history persists for the life of the process.
        self.messages: list[dict] = []

    def _system(self) -> str:
        now = datetime.now().astimezone()
        return (
            SYSTEM_PROMPT
            + f"\n\nThe current local time is {now.isoformat(timespec='minutes')}."
        )

    @staticmethod
    def _fmt_time(epoch: int) -> str:
        return datetime.fromtimestamp(epoch).strftime("%a %d %b, %H:%M")

    def _set_reminder(self, text: str, due_iso: str) -> tuple[str, bool]:
        try:
            dt = datetime.fromisoformat(due_iso)
        except ValueError:
            return f"I couldn't read the time '{due_iso}'.", True
        if dt.tzinfo is None:
            dt = dt.astimezone()  # treat a bare timestamp as local time
        due_at = int(dt.timestamp())
        self.store.add_reminder(text, due_at)
        return f"Reminder set: '{text}' for {self._fmt_time(due_at)}.", False

    def handle(self, user_text: str) -> str:
        """Process one user message, running tools until Sunny is done, and
        return her final text reply. Updates the ongoing conversation."""
        self.messages.append({"role": "user", "content": user_text})
        self.store.log_event("user_message", user_text)
        return self._run(self.messages)

    def oneshot(self, prompt: str) -> str:
        """Run a self-contained request that does NOT touch the conversation
        history — used for things like the daily briefing."""
        return self._run([{"role": "user", "content": prompt}])

    def compose_briefing(self) -> str:
        return self.oneshot(
            "Give me a short, friendly morning briefing. Greet me, state today's "
            "date, list any reminders I have today (use list_reminders), and add "
            "one brief helpful suggestion. Keep it under 70 words."
        )

    def _run(self, messages: list[dict]) -> str:
        """Run the agentic tool-use loop over `messages` and return the reply."""
        for _ in range(20):  # safety cap on tool-use round trips
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=8000,
                thinking={"type": "adaptive"},
                output_config={"effort": self.config.effort},
                system=self._system(),
                tools=tool_definitions(),
                messages=messages,
            )

            if response.stop_reason == "refusal":
                reply = "I can't help with that one."
                messages.append({"role": "assistant", "content": reply})
                return reply

            messages.append({"role": "assistant", "content": response.content})

            # Server-side tools (web search/fetch) can pause the turn; re-send to
            # let Anthropic resume where it left off.
            if response.stop_reason == "pause_turn":
                continue

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                text = "".join(b.text for b in response.content if b.type == "text")
                self.store.log_event("assistant_reply", text)
                return text.strip()

            results = []
            for tu in tool_uses:
                result_text, is_error = self._run_tool(tu.name, tu.input)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result_text,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": results})

        return "I got a bit tangled up working on that — can you try again?"

    def _run_tool(self, name: str, args: dict) -> tuple[str, bool]:
        """Execute a tool. Returns (result_text, is_error)."""
        try:
            self.store.log_event("tool_call", f"{name} {json.dumps(args)[:300]}")
            if name == "remember":
                m = self.store.remember(args["text"], args.get("tag", "note"))
                return f"Remembered (#{m.id}).", False
            if name == "recall":
                hits = self.store.recall(args["query"])
                if not hits:
                    return "Nothing in memory matches that.", False
                return "\n".join(f"- [{m.tag}] {m.text}" for m in hits), False
            if name == "set_reminder":
                return self._set_reminder(args["text"], args["due_iso"])
            if name == "list_reminders":
                pending = self.store.pending_reminders()
                if not pending:
                    return "No upcoming reminders.", False
                return "\n".join(
                    f"- #{r.id} {r.text} @ {self._fmt_time(r.due_at)}" for r in pending
                ), False
            if name == "cancel_reminder":
                ok = self.store.cancel_reminder(int(args["id"]))
                return ("Reminder cancelled." if ok else "No such pending reminder."), False
            if name == "list_devices":
                return json.dumps(self.devices.list_devices()), False
            if name == "set_device":
                d = self.devices.set_state(args["device_id"], args["state"])
                return f"{d['name']} is now {d['state']}.", False
            if name == "notify_user":
                self.notifier.push(args["message"], title=args.get("title"))
                return "Sent to phone.", False
            if name == "list_my_files":
                return json.dumps(self.improver.list_files()), False
            if name == "read_my_file":
                return self.improver.read_file(args["path"]), False
            if name == "propose_self_improvement":
                return self._handle_self_improvement(args)
            return f"Unknown tool: {name}", True
        except Exception as exc:  # surface the error to the model so it can adapt
            return f"Error: {exc}", True

    def _handle_self_improvement(self, args: dict) -> tuple[str, bool]:
        path = args["path"]
        new_content = args["new_content"]
        rationale = args.get("rationale", "")

        validation = self.improver.validate_change(path, new_content)
        if not validation.ok:
            self.store.log_event("self_improve_blocked", f"{path}: {validation.stage}")
            return (
                f"Change to {path} did NOT pass sandbox tests "
                f"({validation.stage}):\n{validation.detail}",
                False,
            )

        approval_id = new_approval_id()
        result = request_approval(
            self.notifier,
            summary=(
                f"Sunny wants to change {path}.\nWhy: {rationale}\n"
                f"Sandbox tests passed."
            ),
            timeout_seconds=self.config.approval_timeout_seconds,
            poll_interval=self.config.poll_interval_seconds,
            approval_id=approval_id,
        )
        if not result.approved:
            self.store.log_event("self_improve_declined", f"{path}: {result.reason}")
            return f"Not applied — approval {result.reason}.", False

        applied = self.improver.apply_change(path, new_content)
        self.store.log_event("self_improve_applied", path)
        return f"Approved and applied: {applied.detail}", False
