from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from rangkai.pi_rpc_harness import main


def test_pi_rpc_harness_success() -> None:
    # 1. Setup mock process streams
    mock_stdin = MagicMock()

    # We will simulate the JSON events streamed by Pi's stdout
    events = [
        {"type": "response", "command": "prompt", "success": True},
        {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "Hello "}},
        {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "world!"}},
        {"type": "tool_execution_start", "toolName": "bash", "args": {"command": "ls"}},
        {"type": "tool_execution_end", "toolName": "bash", "isError": False},
        {"type": "message_end", "message": {"content": [{"type": "text", "text": "Hello world!"}]}},
        {"type": "agent_end"},
    ]
    stdout_lines = [json.dumps(event) + "\n" for event in events] + [""]

    mock_stdout = MagicMock()
    mock_stdout.readline.side_effect = stdout_lines

    mock_proc = MagicMock()
    mock_proc.stdin = mock_stdin
    mock_proc.stdout = mock_stdout
    mock_proc.wait.return_value = 0

    # 2. Patch Popen and sys.argv
    test_args = ["pi_rpc_harness.py", "--issue-number", "8", "--prompt", "solve issue 8"]
    captured_stdout = StringIO()

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("sys.argv", test_args), \
         patch("sys.stdout", captured_stdout):
        exit_code = main()

    # 3. Assertions
    assert exit_code == 0

    # Verify that initial prompt was written to stdin
    mock_stdin.write.assert_any_call('{"id": "prompt-8", "type": "prompt", "message": "solve issue 8"}\n')

    output = captured_stdout.getvalue()

    # Verify we streamed the text deltas
    assert "Hello world!" in output
    # Verify the codex formatting at the end
    assert "codex\nHello world!\n--------" in output
    # Verify tool execution logs
    assert "🛠️ [Tool Executing] bash" in output
    assert "✅ [Tool Finished] bash" in output


def test_pi_rpc_harness_ui_request() -> None:
    # 1. Setup mock process streams
    mock_stdin = MagicMock()

    # We will simulate a confirm request and a select request
    events = [
        {"type": "response", "command": "prompt", "success": True},
        {"type": "extension_ui_request", "id": "req-confirm", "method": "confirm", "title": "Run build?"},
        {
            "type": "extension_ui_request",
            "id": "req-select",
            "method": "select",
            "title": "Pick a tool",
            "options": ["npm", "pip"],
        },
        {"type": "agent_end"},
    ]
    stdout_lines = [json.dumps(event) + "\n" for event in events] + [""]

    mock_stdout = MagicMock()
    mock_stdout.readline.side_effect = stdout_lines

    mock_proc = MagicMock()
    mock_proc.stdin = mock_stdin
    mock_proc.stdout = mock_stdout
    mock_proc.wait.return_value = 0

    # 2. Patch Popen and sys.argv
    test_args = ["pi_rpc_harness.py", "--issue-number", "8", "--prompt", "solve issue 8"]
    captured_stdout = StringIO()

    with patch("subprocess.Popen", return_value=mock_proc), \
         patch("sys.argv", test_args), \
         patch("sys.stdout", captured_stdout):
        exit_code = main()

    # 3. Assertions
    assert exit_code == 0

    # Verify prompt was sent
    mock_stdin.write.assert_any_call('{"id": "prompt-8", "type": "prompt", "message": "solve issue 8"}\n')

    # Verify auto-responses were written to stdin
    mock_stdin.write.assert_any_call('{"type": "extension_ui_response", "id": "req-confirm", "confirmed": true}\n')
    mock_stdin.write.assert_any_call('{"type": "extension_ui_response", "id": "req-select", "value": "npm"}\n')

    output = captured_stdout.getvalue()
    assert "❓ [UI Request] confirm: Run build?" in output
    assert "❓ [UI Request] select: Pick a tool" in output
    assert '🤖 [Auto-Responded] Sent: {"type": "extension_ui_response", "id": "req-confirm", "confirmed": true}' in output
    assert '🤖 [Auto-Responded] Sent: {"type": "extension_ui_response", "id": "req-select", "value": "npm"}' in output


def test_pi_rpc_harness_provider_model() -> None:
    # 1. Setup mock process streams
    mock_stdin = MagicMock()
    events = [
        {"type": "response", "command": "prompt", "success": True},
        {"type": "agent_end"},
    ]
    stdout_lines = [json.dumps(event) + "\n" for event in events] + [""]

    mock_stdout = MagicMock()
    mock_stdout.readline.side_effect = stdout_lines

    mock_proc = MagicMock()
    mock_proc.stdin = mock_stdin
    mock_proc.stdout = mock_stdout
    mock_proc.wait.return_value = 0

    # 2. Patch Popen and specify --provider and --model in test args
    test_args = [
        "pi_rpc_harness.py",
        "--issue-number",
        "8",
        "--prompt",
        "solve issue 8",
        "--provider",
        "opencode-go",
        "--model",
        "deepseek-v4-pro",
    ]
    captured_stdout = StringIO()

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("sys.argv", test_args), \
         patch("sys.stdout", captured_stdout):
        exit_code = main()

    # 3. Assertions
    assert exit_code == 0
    # Verify that popen was called with correct command forwarding provider/model
    mock_popen.assert_called_once()
    called_cmd = mock_popen.call_args[0][0]
    assert "--provider" in called_cmd
    assert "opencode-go" in called_cmd
    assert "--model" in called_cmd
    assert "deepseek-v4-pro" in called_cmd

