"""Bersama Agent Harness for Pi in RPC Mode.

This script acts as a headless wrapper and adapter around 'pi --mode rpc',
streaming live events, handling interactive dialog requests automatically,
and formatting log output for the Bersama orchestrator.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Bersama Agent Harness for Pi in RPC Mode")
    parser.add_argument("--issue-number", type=int, required=True, help="GitHub Issue Number")
    parser.add_argument("--prompt", type=str, required=True, help="User Prompt for Pi")
    parser.add_argument("--provider", type=str, default=None, help="LLM Provider Name")
    parser.add_argument("--model", type=str, default=None, help="LLM Model ID/Pattern")
    args = parser.parse_args()

    print(f"🚀 Starting Bersama Pi RPC Harness for Issue #{args.issue_number}")
    print(f"Working Directory: {os.getcwd()}")
    print("=" * 60)
    sys.stdout.flush()

    # Spawn Pi in RPC Mode
    cmd = ["pi", "--mode", "rpc", "--no-session"]
    if args.provider:
        cmd.extend(["--provider", args.provider])
    if args.model:
        cmd.extend(["--model", args.model])

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line-buffered
        )
    except Exception as exc:
        print(f"❌ Error spawning 'pi' process: {exc}")
        sys.stdout.flush()
        return 1

    # Send the initial prompt command
    prompt_cmd = {
        "id": f"prompt-{args.issue_number}",
        "type": "prompt",
        "message": args.prompt,
    }

    try:
        proc.stdin.write(json.dumps(prompt_cmd) + "\n")
        proc.stdin.flush()
    except Exception as exc:
        print(f"❌ Error sending initial prompt: {exc}")
        proc.kill()
        sys.stdout.flush()
        return 1

    last_assistant_text = ""
    stdout_stream = proc.stdout
    if stdout_stream is None:
        print("❌ Subprocess stdout stream is not available.")
        proc.kill()
        sys.stdout.flush()
        return 1

    try:
        for line in iter(stdout_stream.readline, ""):
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Print raw non-JSON outputs as log lines
                print(f"[RAW STDOUT] {line}")
                sys.stdout.flush()
                continue

            event_type = event.get("type")

            if event_type == "response":
                cmd_name = event.get("command")
                success = event.get("success", False)
                if not success:
                    error_msg = event.get("error", "Unknown error")
                    print(f"❌ Command '{cmd_name}' failed: {error_msg}")
                    sys.stdout.flush()
                    if cmd_name == "prompt":
                        proc.kill()
                        return 1
                else:
                    print(f"✅ Command '{cmd_name}' accepted successfully.")
                    sys.stdout.flush()

            elif event_type == "message_update":
                delta_event = event.get("assistantMessageEvent", {})
                delta_type = delta_event.get("type")
                if delta_type == "text_delta":
                    delta_text = delta_event.get("delta", "")
                    sys.stdout.write(delta_text)
                    sys.stdout.flush()

            elif event_type == "message_end":
                msg = event.get("message", {})
                content_blocks = msg.get("content", [])
                for block in content_blocks:
                    if block.get("type") == "text":
                        last_assistant_text = block.get("text", "")

            elif event_type == "tool_execution_start":
                tool_name = event.get("toolName")
                tool_args = event.get("args")
                print(f"\n\n🛠️ [Tool Executing] {tool_name} with args: {json.dumps(tool_args)}")
                sys.stdout.flush()

            elif event_type == "tool_execution_end":
                tool_name = event.get("toolName")
                is_error = event.get("isError", False)
                print(f"✅ [Tool Finished] {tool_name} (Error: {is_error})")
                sys.stdout.flush()

            elif event_type == "extension_ui_request":
                req_id = event.get("id")
                method = event.get("method")
                title = event.get("title", "")

                print(f"\n❓ [UI Request] {method}: {title}")
                sys.stdout.flush()

                # Headless auto-responses to UI prompts
                response_val = None
                if method == "confirm":
                    response_val = {"type": "extension_ui_response", "id": req_id, "confirmed": True}
                elif method == "select":
                    options = event.get("options", [])
                    selected = options[0] if options else ""
                    response_val = {"type": "extension_ui_response", "id": req_id, "value": selected}
                elif method == "input":
                    response_val = {"type": "extension_ui_response", "id": req_id, "value": "Headless response"}
                elif method == "editor":
                    prefill = event.get("prefill", "")
                    response_val = {"type": "extension_ui_response", "id": req_id, "value": prefill}

                if response_val and proc.stdin is not None:
                    proc.stdin.write(json.dumps(response_val) + "\n")
                    proc.stdin.flush()
                    print(f"🤖 [Auto-Responded] Sent: {json.dumps(response_val)}")
                    sys.stdout.flush()

            elif event_type == "agent_end":
                print("\n\n🏁 Agent finished execution.")
                sys.stdout.flush()
                break

            elif event_type == "extension_error":
                print(f"\n⚠️ [Extension Error] {event.get('error')}")
                sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n⚠️ Aborting harness on user interrupt...")
        if proc.stdin is not None:
            try:
                proc.stdin.write(json.dumps({"type": "abort"}) + "\n")
                proc.stdin.flush()
            except Exception:
                pass
        proc.terminate()
        sys.stdout.flush()
        return 130
    except Exception as exc:
        print(f"\n❌ Error during RPC streaming: {exc}")
        proc.kill()
        sys.stdout.flush()
        return 1

    exit_code = proc.wait()
    print(f"Process exited with code {exit_code}")
    sys.stdout.flush()

    # Format the last assistant text in the codex/-------- block so that
    # Bersama's extract_last_agent_message naturally captures it for paused states.
    if last_assistant_text:
        print("\n\ncodex")
        print(last_assistant_text)
        print("--------")
        sys.stdout.flush()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
