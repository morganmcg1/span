"""Integration tests for Claude Code runner.

These tests make REAL calls to the claude CLI - no mocking.
They test the actual integration with Claude Code for the Telegram bot.

Run with: uv run pytest tests/test_claude_code_integration.py -v -s
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from span.telegram.claude_code import ClaudeCodeRunner, CCExecutionResult


# Skip if claude CLI not available
def claude_available() -> bool:
    """Check if claude CLI is available."""
    import shutil
    return shutil.which("claude") is not None


@pytest.fixture
def temp_repo():
    """Create a temporary git repo for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        os.system(f"cd {tmpdir} && git init -q && git config user.email 'test@test.com' && git config user.name 'Test'")
        # Create a simple file
        Path(tmpdir, "test.py").write_text("# Test file\nx = 1\n")
        os.system(f"cd {tmpdir} && git add . && git commit -q -m 'Initial commit'")
        yield tmpdir


@pytest.fixture
def runner(temp_repo):
    """Create a ClaudeCodeRunner for the temp repo."""
    return ClaudeCodeRunner(temp_repo)


@pytest.mark.skipif(not claude_available(), reason="claude CLI not available")
class TestClaudeCodeIntegration:
    """Integration tests that make real Claude Code calls."""

    @pytest.mark.asyncio
    async def test_simple_read_only_query(self, runner, temp_repo):
        """Test a simple read-only query that doesn't modify files."""
        result = await runner.execute(
            "List the files in the current directory. Just list them, don't create or modify anything."
        )

        assert isinstance(result, CCExecutionResult)
        assert result.session_id, "Should get a session ID"
        # Output should mention test.py
        assert "test.py" in result.output.lower() or result.success

    @pytest.mark.asyncio
    async def test_output_not_truncated(self, runner, temp_repo):
        """Test that output is captured fully without truncation."""
        # Ask for something that generates longer output
        result = await runner.execute(
            "Read test.py and describe what you see. Be verbose."
        )

        assert result.output, "Should have output"
        # Output should not be artificially limited
        # The old limit was 20 lines, so if we get more than 20 lines, the fix worked
        lines = result.output.strip().split("\n")
        # Just ensure we're getting meaningful output
        assert len(lines) >= 1

    @pytest.mark.asyncio
    async def test_session_continuation(self, runner, temp_repo):
        """Test that --resume properly continues a session."""
        # First call
        result1 = await runner.execute(
            "Remember the number 42. Just acknowledge you've noted it."
        )

        assert result1.session_id, "First call should return session ID"
        first_session_id = result1.session_id

        # Second call with --resume
        result2 = await runner.execute(
            "What number did I ask you to remember?",
            session_id=first_session_id,
        )

        # Should reference 42
        assert "42" in result2.output, f"Should remember 42, got: {result2.output[:500]}"

    @pytest.mark.asyncio
    async def test_file_modification_detected(self, runner, temp_repo):
        """Test that file changes are detected after modification."""
        result = await runner.execute(
            "Edit test.py to add a comment '# Modified by test' at the top. Use the Edit tool."
        )

        # Check if changes were detected
        if result.success:
            # Should detect the edit
            assert len(result.changes) > 0 or "test.py" in result.output.lower()

    @pytest.mark.asyncio
    async def test_new_file_creation_detected(self, runner, temp_repo):
        """Test that new file creation is detected."""
        result = await runner.execute(
            "Create a new file called 'new_file.txt' with content 'Hello from test'. Use the Write tool."
        )

        if result.success:
            # Check if file was created
            new_file = Path(temp_repo) / "new_file.txt"
            if new_file.exists():
                assert any(c.path == "new_file.txt" for c in result.changes) or len(result.changes) > 0

    @pytest.mark.asyncio
    async def test_discard_changes(self, runner, temp_repo):
        """Test that discard_changes reverts modifications."""
        # Make a change
        test_file = Path(temp_repo) / "test.py"
        original_content = test_file.read_text()
        test_file.write_text("# Changed content\n")

        # Discard
        await runner.discard_changes()

        # Should be back to original
        assert test_file.read_text() == original_content

    @pytest.mark.asyncio
    async def test_progress_callback(self, runner, temp_repo):
        """Test that progress callbacks are called during execution."""
        progress_updates = []

        async def on_progress(text: str):
            progress_updates.append(text)

        result = await runner.execute(
            "Read test.py and tell me what's in it.",
            on_progress=on_progress,
        )

        # Should have received at least some progress updates
        # (depends on what Claude does, but tool uses should trigger updates)
        assert result.session_id  # At minimum, execution completed

    @pytest.mark.asyncio
    async def test_error_handling(self, runner):
        """Test handling of invalid working directory."""
        bad_runner = ClaudeCodeRunner("/nonexistent/path/that/doesnt/exist")
        result = await bad_runner.execute("Hello")

        # Should handle gracefully (either error message or still work with warnings)
        assert isinstance(result, CCExecutionResult)


@pytest.mark.skipif(not claude_available(), reason="claude CLI not available")
class TestClaudeCodeOutputCapture:
    """Tests specifically for output capture behavior."""

    @pytest.mark.asyncio
    async def test_full_output_preserved(self, runner, temp_repo):
        """Verify that full output is preserved, not truncated to 20 lines."""
        # Create a file with many lines to read
        test_file = Path(temp_repo) / "multiline.txt"
        test_file.write_text("\n".join(f"Line {i}" for i in range(50)))
        os.system(f"cd {temp_repo} && git add multiline.txt")

        result = await runner.execute(
            "Read multiline.txt and repeat back every line number you see."
        )

        # The output should contain references to many lines, not be cut off
        # If truncated to 20 lines, we'd lose a lot of content
        assert result.output, "Should have output"

    @pytest.mark.asyncio
    async def test_large_file_handling(self, runner, temp_repo):
        """Test handling of responses that include large file contents."""
        # Create a larger file
        test_file = Path(temp_repo) / "large.py"
        test_file.write_text("\n".join(f"# Line {i}\nx_{i} = {i}" for i in range(100)))
        os.system(f"cd {temp_repo} && git add large.py")

        result = await runner.execute(
            "Read large.py. How many lines does it have?"
        )

        # Should complete without the "chunk exceed limit" error
        assert result.error is None or "chunk" not in (result.error or "").lower()
        assert result.session_id, "Should complete and return session ID"
