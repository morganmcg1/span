"""Claude Code integration for running claude CLI from Telegram."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from rich.console import Console

console = Console()

# Timeout for Claude Code execution (5 minutes)
EXECUTION_TIMEOUT = 300


@dataclass
class FileChange:
    """A single file change made by Claude Code."""

    path: str
    action: str  # "edited", "created", "deleted"
    summary: str  # Brief description of what changed


@dataclass
class CCExecutionResult:
    """Result of Claude Code execution."""

    success: bool
    session_id: str  # For --resume if follow-up needed
    output: str  # Truncated progress for display
    error: str | None
    changes: list[FileChange] = field(default_factory=list)
    full_output: str = ""  # Complete text content for log file


class ClaudeCodeRunner:
    """Runs claude CLI and manages code changes."""

    def __init__(self, working_dir: str, require_clean_worktree: bool = False):
        self.working_dir = working_dir
        self.require_clean_worktree = require_clean_worktree
        self._current_process: asyncio.subprocess.Process | None = None

    async def execute(
        self,
        prompt: str,
        session_id: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> CCExecutionResult:
        """Execute claude CLI with streaming output.

        Args:
            prompt: The prompt to send to Claude Code
            session_id: Optional session ID to resume a previous session
            on_progress: Callback for progress updates

        Returns:
            CCExecutionResult with success status, session_id, output, and changes
        """
        # Add context prefix for first-time prompts (not resuming)
        if not session_id:
            context_prefix = (
                "You are making live, on-the-fly updates to the `span` repo, "
                "a Mexican Spanish language learning app with voice calls and Telegram bot. "
                "Make the requested changes. The user will review and decide whether to deploy.\n\n"
                "User request: "
            )
            full_prompt = context_prefix + prompt
        else:
            full_prompt = prompt

        # Starting a fresh Claude Code session on a dirty worktree is dangerous because it can
        # mix unrelated local edits into the session and make discard/push operations unsafe.
        if not session_id and self.require_clean_worktree:
            status_proc = await asyncio.create_subprocess_exec(
                "git",
                "status",
                "--porcelain",
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            status_out, _ = await status_proc.communicate()
            if status_out.strip():
                return CCExecutionResult(
                    success=False,
                    session_id="",
                    output="",
                    error=(
                        "Working tree has uncommitted changes. Commit/stash them before starting a new "
                        "Claude Code session (or push/discard the previous session)."
                    ),
                )

        # Build command
        # Note: --output-format stream-json requires --verbose when using -p
        # Use Opus model for best quality code changes
        cmd = [
            "claude", "-p", full_prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--model", "claude-opus-4-5-20251101", "--dangerously-skip-permissions",
        ]
        if session_id:
            cmd.extend(["--resume", session_id])

        display_cmd = ["claude", "-p", "<prompt>", "--output-format", "stream-json"]
        if "--verbose" in cmd:
            display_cmd.append("--verbose")
        if session_id:
            display_cmd.extend(["--resume", session_id])
        console.print(f"[blue]Running: {' '.join(display_cmd)}[/blue]")

        stderr_task: asyncio.Task[None] | None = None
        stderr_buf = bytearray()

        try:
            # Use high limit (10MB) to handle large JSON lines from Claude Code
            self._current_process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=10 * 1024 * 1024,
            )

            async def drain_stderr() -> None:
                stderr_stream = self._current_process.stderr
                if not stderr_stream:
                    return
                while True:
                    chunk = await stderr_stream.read(4096)
                    if not chunk:
                        break
                    stderr_buf.extend(chunk)
                    if len(stderr_buf) > 64_000:
                        stderr_buf[:] = stderr_buf[-64_000:]

            stderr_task = asyncio.create_task(drain_stderr())

            output_lines: list[str] = []  # Truncated progress for display
            full_text_blocks: list[str] = []  # Full text content for log file
            new_session_id = ""
            last_progress_time = 0.0
            start_time = time.monotonic()

            while True:
                try:
                    remaining = max(0.0, EXECUTION_TIMEOUT - (time.monotonic() - start_time))
                    line = await asyncio.wait_for(
                        self._current_process.stdout.readline(),
                        timeout=remaining,
                    )
                except asyncio.TimeoutError:
                    try:
                        self._current_process.kill()
                    except ProcessLookupError:
                        pass
                    try:
                        await self._current_process.wait()
                    except Exception:
                        pass
                    stderr_str = stderr_buf.decode(errors="replace").strip()
                    if stderr_str:
                        stderr_str = stderr_str[-200:]
                        error = f"Execution timed out after 5 minutes: {stderr_str}"
                    else:
                        error = "Execution timed out after 5 minutes"
                    return CCExecutionResult(
                        success=False,
                        session_id=new_session_id,
                        output="",
                        error=error,
                    )
                except ValueError as e:
                    # Line too long even with increased limit - skip it
                    console.print(f"[yellow]Skipping oversized line: {e}[/yellow]")
                    continue

                if not line:
                    break

                line_str = line.decode(errors="replace").strip()
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                    progress_text = self._extract_progress(event)
                    full_text = self._extract_full_text(event)

                    # Extract session ID from various event types
                    if event.get("session_id"):
                        new_session_id = event["session_id"]
                        console.print(f"[green]Captured session_id: {new_session_id[:20]}...[/green]")

                    # Also check nested structures
                    if event.get("type") == "result":
                        if event.get("result"):
                            output_lines.append(event["result"])
                            full_text_blocks.append(event["result"])

                    # Capture full text content (untruncated)
                    if full_text:
                        full_text_blocks.append(full_text)

                    if progress_text:
                        output_lines.append(progress_text)
                        # Rate-limit progress callbacks
                        now = time.time()
                        if on_progress and (now - last_progress_time) >= 1.0:
                            last_progress_time = now
                            await on_progress(progress_text)

                except json.JSONDecodeError:
                    # Non-JSON output, might be plain text
                    output_lines.append(line_str)

            await self._current_process.wait()
            if stderr_task:
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass
            stderr_str = stderr_buf.decode(errors="replace").strip()
            returncode = self._current_process.returncode
            success = returncode == 0

            # Log for debugging
            console.print(f"[blue]Claude Code exit code: {returncode}[/blue]")
            if stderr_str:
                console.print(f"[yellow]stderr: {stderr_str[:500]}[/yellow]")

            # Parse changes from git diff
            changes = await self._detect_changes()

            # Build error message if failed
            error_msg = None
            if not success:
                error_msg = f"Exit code {returncode}"
                if stderr_str:
                    # Truncate stderr for display
                    error_msg += f": {stderr_str[:200]}"

            return CCExecutionResult(
                success=success,
                session_id=new_session_id,
                output="\n".join(output_lines),  # Truncated progress for display
                error=error_msg,
                changes=changes,
                full_output="\n".join(full_text_blocks),  # Complete text for log
            )

        except Exception as e:
            console.print(f"[red]Claude Code error: {e}[/red]")
            return CCExecutionResult(
                success=False,
                session_id="",
                output="",
                error=str(e),
            )
        finally:
            if stderr_task:
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass
            self._current_process = None

    def _extract_progress(self, event: dict) -> str | None:
        """Extract human-readable progress from stream-json event."""
        event_type = event.get("type")

        if event_type == "assistant":
            content = event.get("message", {}).get("content", [])
            for block in content:
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})

                    # Extract relevant info based on tool
                    if tool_name in ("Read", "Glob", "Grep"):
                        path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("pattern", "")
                        return f"Reading: {Path(path).name}" if path else f"Using: {tool_name}"
                    elif tool_name == "Edit":
                        path = tool_input.get("file_path", "")
                        return f"Editing: {Path(path).name}" if path else "Editing file"
                    elif tool_name == "Write":
                        path = tool_input.get("file_path", "")
                        return f"Writing: {Path(path).name}" if path else "Writing file"
                    elif tool_name == "Bash":
                        cmd = tool_input.get("command", "")
                        # Truncate long commands
                        if len(cmd) > 50:
                            cmd = cmd[:50] + "..."
                        return f"Running: {cmd}"
                    else:
                        return f"Using: {tool_name}"

                elif block.get("type") == "text":
                    text = block.get("text", "")
                    if len(text) > 100:
                        return text[:100] + "..."
                    return text if text else None

        return None

    def _extract_full_text(self, event: dict) -> str | None:
        """Extract complete text content from stream-json event (no truncation)."""
        event_type = event.get("type")

        if event_type == "assistant":
            content = event.get("message", {}).get("content", [])
            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "")
                    return text if text else None

        return None

    async def _detect_changes(self) -> list[FileChange]:
        """Detect file changes using git diff and status."""
        changes: list[FileChange] = []

        # Unified view across staged + unstaged changes.
        status_proc = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        status_out, _ = await status_proc.communicate()

        for line in status_out.decode().strip().split("\n"):
            if not line:
                continue
            status_code = line[:2]
            file_path = line[3:]

            # Rename format: "R  old -> new"
            if " -> " in file_path:
                file_path = file_path.split(" -> ", 1)[1].strip()

            if status_code.startswith("??") or "A" in status_code:
                changes.append(FileChange(
                    path=file_path,
                    action="created",
                    summary="New file",
                ))
            elif "D" in status_code:
                changes.append(FileChange(
                    path=file_path,
                    action="deleted",
                    summary="Deleted",
                ))
            else:
                changes.append(FileChange(
                    path=file_path,
                    action="edited",
                    summary=await self._get_diff_summary(file_path),
                ))

        return changes

    async def _get_diff_summary(self, file_path: str) -> str:
        """Get a brief summary of changes to a file."""
        # Get diff stats (prefer unstaged; fall back to staged)
        stat_proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--shortstat", "--", file_path,
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stat_out, _ = await stat_proc.communicate()

        stat_line = stat_out.decode().strip().split("\n")[-1] if stat_out.strip() else ""
        if not stat_line:
            stat_proc = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                "--cached",
                "--shortstat",
                "--",
                file_path,
                cwd=self.working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stat_out, _ = await stat_proc.communicate()
            stat_line = stat_out.decode().strip().split("\n")[-1] if stat_out.strip() else ""

        # Parse insertions/deletions
        if "insertion" in stat_line or "deletion" in stat_line:
            # Extract numbers like "5 insertions(+), 2 deletions(-)"
            parts = stat_line.split(",")
            summary_parts = []
            for part in parts:
                if "insertion" in part:
                    num = part.strip().split()[0]
                    summary_parts.append(f"+{num}")
                elif "deletion" in part:
                    num = part.strip().split()[0]
                    summary_parts.append(f"-{num}")
            return " ".join(summary_parts) if summary_parts else "Modified"

        return "Modified"

    async def discard_changes(self) -> None:
        """Revert all uncommitted changes."""
        # Reset tracked changes (including staged changes)
        reset_proc = await asyncio.create_subprocess_exec(
            "git",
            "reset",
            "--hard",
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await reset_proc.wait()

        # Remove untracked files/directories (respects .gitignore)
        clean_proc = await asyncio.create_subprocess_exec(
            "git", "clean", "-fd",
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await clean_proc.wait()

        console.print("[yellow]Changes reverted[/yellow]")

    async def push_changes(self, commit_message: str) -> bool:
        """Commit and push all changes.

        Returns:
            True if successful, False otherwise
        """
        # Stage all changes
        add_proc = await asyncio.create_subprocess_exec(
            "git", "add", "-A",
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await add_proc.wait()

        # Nothing to commit (avoid failing the UI flow on a no-op)
        diff_proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--cached",
            "--quiet",
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await diff_proc.wait()
        if diff_proc.returncode == 0:
            console.print("[yellow]No staged changes to commit[/yellow]")
            return True

        # Commit
        commit_proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", commit_message,
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, commit_err = await commit_proc.communicate()

        if commit_proc.returncode != 0:
            console.print(f"[red]Commit failed: {commit_err.decode()}[/red]")
            return False

        # Push
        push_proc = await asyncio.create_subprocess_exec(
            "git", "push",
            cwd=self.working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, push_err = await push_proc.communicate()

        if push_proc.returncode != 0:
            console.print(f"[red]Push failed: {push_err.decode()}[/red]")
            return False

        console.print("[green]Changes committed and pushed[/green]")
        return True

    def cancel(self) -> None:
        """Cancel the current execution if running."""
        if self._current_process:
            try:
                self._current_process.kill()
            except ProcessLookupError:
                pass
            console.print("[yellow]Claude Code execution cancelled[/yellow]")
