"""Route incoming hook events to the right handler logic."""

from __future__ import annotations

import re
import time
from pathlib import Path

from agentdiff.models.changes import ChangeRecord
from agentdiff.models.tasks import TaskState
from agentdiff.models.session import SessionState
from agentdiff.store.change_log import append_change
from agentdiff.store.session_store import (
    SessionLock, ensure_session_dir, load_session_state, save_session_state,
    load_task_state, save_task_state,
)
from agentdiff.capture.reasoning import extract_reasoning
from agentdiff.capture.scope import infer_scope_files, is_in_scope
from agentdiff.capture.spec_linker import link_to_spec


def handle_event(payload: dict, project_root: str) -> None:
    """Dispatch on hook_event_name."""
    event = payload.get("hook_event_name", "")
    session_id = payload.get("session_id", "")

    if not session_id:
        return

    if event == "PostToolUse":
        _handle_post_tool_use(payload, project_root)
    elif event == "SessionStart":
        _handle_session_start(payload, project_root)
    elif event == "SubagentStart":
        _handle_subagent_start(payload, project_root)
    elif event == "SubagentStop":
        _handle_subagent_stop(payload, project_root)
    elif event == "TaskCompleted":
        _handle_task_completed(payload, project_root)
    elif event == "Stop":
        _handle_stop(payload, project_root)


def _handle_post_tool_use(payload: dict, project_root: str) -> None:
    """Record a file change with full context."""
    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return

    session_id = payload["session_id"]
    tool_input = payload.get("tool_input", {})

    # Get transcript_path: prefer payload, fall back to session state
    transcript_path = payload.get("transcript_path", "")
    if not transcript_path:
        state_for_transcript = load_session_state(project_root, session_id)
        transcript_path = state_for_transcript.transcript_path

    # Extract reasoning outside the lock (reads transcript, may be slow)
    reasoning = extract_reasoning(transcript_path) if transcript_path else ""

    # Extract user prompt from transcript when no active task
    user_prompt = ""

    with SessionLock(project_root, session_id):
        state = load_session_state(project_root, session_id)
        current_task = None
        if state.active_tasks:
            current_task = load_task_state(project_root, session_id, state.active_tasks[-1])

        # If no active task, extract the user's prompt from the transcript
        if not current_task and transcript_path:
            user_prompt = _extract_last_user_prompt(transcript_path)

        file_path = tool_input.get("file_path", "")
        # Store relative path to keep change log portable
        try:
            rel = str(Path(file_path).relative_to(project_root))
        except ValueError:
            rel = file_path
        record = ChangeRecord(
            session_id=session_id,
            file_path=rel,
            tool_name=tool_name,
            content=tool_input.get("content"),
            old_string=tool_input.get("old_string"),
            new_string=tool_input.get("new_string"),
            prompt=current_task.prompt if current_task else user_prompt,
            reasoning=reasoning,
            task_id=current_task.task_id if current_task else "",
            task_subject=current_task.task_subject if current_task else "",
            task_description=current_task.task_description if current_task else "",
            spec_section=current_task.spec_section if current_task else "",
            provenance="agent",
            in_scope=_check_scope(file_path, current_task),
            scope_files=current_task.scope_files if current_task else [],
        )

        append_change(project_root, session_id, record)

        state.change_count += 1
        state.last_event_at = time.time()
        save_session_state(project_root, session_id, state)


def _handle_session_start(payload: dict, project_root: str) -> None:
    """Create session store directory and initial state."""
    session_id = payload["session_id"]
    cwd = payload.get("cwd", "")

    with SessionLock(project_root, session_id):
        # Preserve existing change_count if session already has state
        existing = load_session_state(project_root, session_id)
        state = SessionState(
            session_id=session_id,
            transcript_path=payload.get("transcript_path", ""),
            cwd=cwd,
            started_at=time.time(),
            status="active",
            change_count=existing.change_count,
            active_tasks=existing.active_tasks,
        )
        save_session_state(project_root, session_id, state)


def _handle_subagent_start(payload: dict, project_root: str) -> None:
    """Task boundary start. Extract intent and scope."""
    session_id = payload["session_id"]
    agent_id = payload.get("agent_id", "")
    agent_type = payload.get("agent_type", "")
    transcript_path = payload.get("transcript_path", "")

    prompt = _extract_last_user_prompt(transcript_path)

    task = TaskState(
        task_id=agent_id,
        session_id=session_id,
        agent_type=agent_type,
        prompt=prompt,
        scope_files=infer_scope_files(prompt),
        spec_section=link_to_spec(project_root, prompt),
    )
    save_task_state(project_root, session_id, task)

    with SessionLock(project_root, session_id):
        state = load_session_state(project_root, session_id)
        if agent_id not in state.active_tasks:
            state.active_tasks.append(agent_id)
        save_session_state(project_root, session_id, state)


def _handle_subagent_stop(payload: dict, project_root: str) -> None:
    """Task boundary end."""
    session_id = payload["session_id"]
    agent_id = payload.get("agent_id", "")

    task = load_task_state(project_root, session_id, agent_id)
    if task:
        task.last_assistant_message = payload.get("last_assistant_message", "")
        task.completed_at = time.time()
        save_task_state(project_root, session_id, task)

    with SessionLock(project_root, session_id):
        state = load_session_state(project_root, session_id)
        state.active_tasks = [t for t in state.active_tasks if t != agent_id]
        save_session_state(project_root, session_id, state)


def _handle_task_completed(payload: dict, project_root: str) -> None:
    """Captures task_subject + task_description."""
    session_id = payload["session_id"]
    task_id = payload.get("task_id", "")

    task = load_task_state(project_root, session_id, task_id)
    if task:
        task.task_subject = payload.get("task_subject", "")
        task.task_description = payload.get("task_description", "")
        task.completed_at = time.time()
        if task.task_description:
            task.spec_section = link_to_spec(project_root, task.task_description)
        save_task_state(project_root, session_id, task)
    else:
        task = TaskState(
            task_id=task_id,
            session_id=session_id,
            task_subject=payload.get("task_subject", ""),
            task_description=payload.get("task_description", ""),
            completed_at=time.time(),
            scope_files=infer_scope_files(payload.get("task_description", "")),
            spec_section=link_to_spec(project_root, payload.get("task_description", "")),
        )
        save_task_state(project_root, session_id, task)


def _handle_stop(payload: dict, project_root: str) -> None:
    """Session stop. Finalize open tasks and backfill reasoning."""
    session_id = payload["session_id"]

    with SessionLock(project_root, session_id):
        state = load_session_state(project_root, session_id)
        state.status = "stopped"
        state.last_event_at = time.time()

        for task_id in list(state.active_tasks):
            task = load_task_state(project_root, session_id, task_id)
            if task and not task.completed_at:
                task.completed_at = time.time()
                task.last_assistant_message = payload.get("last_assistant_message", "")
                save_task_state(project_root, session_id, task)

        state.active_tasks.clear()
        save_session_state(project_root, session_id, state)

    # Generate reasoning summaries via Claude CLI
    _enrich_reasoning(project_root, session_id)


def _enrich_reasoning(project_root: str, session_id: str) -> None:
    """Use Claude CLI to generate summaries for all changes in the session.

    At Stop time:
    1. Backfills missing prompts from the transcript (handles long sessions
       where the tail-read missed the user prompt at capture time).
    2. Sends all changes to Claude CLI to generate reasoning summaries.
    """
    from agentdiff.store.change_log import read_changes, update_changes
    from agentdiff.shared.claude_cli import ask_claude

    changes = read_changes(project_root, session_id)
    if not changes:
        return

    # Backfill missing prompts from transcript
    state = load_session_state(project_root, session_id)
    transcript_prompt = ""
    if state.transcript_path:
        transcript_prompt = _extract_last_user_prompt(state.transcript_path)

    prompt_updates = {}
    for c in changes:
        if not c.prompt and transcript_prompt:
            c.prompt = transcript_prompt
            prompt_updates[c.change_id] = {"prompt": transcript_prompt}
    if prompt_updates:
        update_changes(project_root, prompt_updates)

    # Build one prompt covering all changes
    parts = [
        "You are a code change summarizer. Your ONLY job is to describe the "
        "code changes listed below based on the diffs and file contents provided. "
        "Do NOT reference any other instructions, README files, or project context. "
        "For each change, write a concise 1-2 sentence summary "
        "describing WHAT was changed and WHY, based solely on the diff.\n"
    ]
    for i, c in enumerate(changes):
        parts.append(f"--- Change {i + 1} ---")
        parts.append(f"File: {c.file_path}")
        parts.append(f"Action: {c.tool_name}")
        if c.prompt:
            parts.append(f"User asked: \"{c.prompt}\"")
        if c.tool_name == "Edit" and c.old_string and c.new_string:
            parts.append(f"Before: {c.old_string[:300]}")
            parts.append(f"After:  {c.new_string[:300]}")
        elif c.tool_name == "Write" and c.content:
            parts.append(f"File content:\n{c.content[:800]}")
        parts.append("")

    if len(changes) == 1:
        parts.append("Respond with ONLY the summary, no numbering or prefixes.")
    else:
        parts.append(
            "Respond with one summary per change, each on its own line, "
            "prefixed with the change number like: 1. summary here"
        )

    response = ask_claude("\n".join(parts), model="haiku", timeout=30)
    if not response:
        return

    # Parse response into per-change summaries
    summaries = _parse_summaries(response, len(changes))

    updates = {}
    for change, summary in zip(changes, summaries):
        if summary:
            updates[change.change_id] = {"reasoning": summary}

    if updates:
        update_changes(project_root, updates)


def _parse_summaries(response: str, expected_count: int) -> list[str]:
    """Parse Claude's response into a list of summaries.

    Handles both single-summary and numbered-list formats.
    """
    if expected_count == 1:
        return [response.strip()]

    lines = [l.strip() for l in response.strip().split("\n") if l.strip()]
    summaries: list[str] = []

    for line in lines:
        # Strip numbering: "1. summary" or "1) summary" or "Change 1: summary"
        cleaned = re.sub(r"^(?:\d+[.)]\s*|change\s+\d+[:.]\s*)", "", line, flags=re.IGNORECASE)
        if cleaned:
            summaries.append(cleaned)

    # Pad or trim to expected count
    while len(summaries) < expected_count:
        summaries.append("")
    return summaries[:expected_count]


def _check_scope(file_path: str, task: TaskState | None) -> bool | None:
    """Check if file_path is in the task's declared scope."""
    if not task or not task.scope_files:
        return None
    return is_in_scope(file_path, task.scope_files)


def _extract_last_user_prompt(transcript_path: str) -> str:
    """Read the user's prompt from the transcript JSONL.

    In long agentic sessions the user types one prompt then Claude does
    100+ tool calls.  Short follow-up prompts like "do it" or "yes,
    modify it" are technically the trigger but useless for blame —
    we prefer the initial descriptive prompt in that case.
    """
    from agentdiff.capture.reasoning import read_transcript_tail, read_transcript_head

    tail_prompt = _find_user_text_in_entries(
        read_transcript_tail(transcript_path, max_lines=200)
    )
    head_prompt = _find_user_text_in_entries(
        read_transcript_head(transcript_path, max_lines=30)
    )

    if not tail_prompt:
        return head_prompt
    if not head_prompt:
        return tail_prompt

    # If the tail prompt is a short confirmation, prefer the descriptive head prompt
    if len(tail_prompt) < 40 and len(head_prompt) > len(tail_prompt):
        return head_prompt

    return tail_prompt


def _find_user_text_in_entries(entries: list[dict]) -> str:
    """Scan entries (newest first) for a real user-typed message.

    Skips tool_result entries (which also have type "user").
    """
    for entry in reversed(entries):
        if entry.get("type") not in ("user", "human"):
            continue
        content = entry.get("message", {}).get("content", "")
        # Plain string content = actual user prompt
        if isinstance(content, str) and content.strip():
            return content[:500]
        # List content: skip if it's only tool_results
        if isinstance(content, list):
            text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
            text = " ".join(text_parts).strip()
            if text:
                return text[:500]
    return ""
