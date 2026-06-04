from pathlib import Path

import pytest

from rangkai.config import ConfigError, DiscordConfig, load_config


def write_config(tmp_path: Path, contents: str) -> Path:
    config_path = tmp_path / "rangkai.yaml"
    config_path.write_text(contents, encoding="utf-8")
    return config_path


def test_loads_valid_config(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
    args_template:
      - run
      - --repo
      - "{repo_path}"
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    global_concurrency: 3
    per_prd_concurrency: 2
    default_harness: local
""".strip(),
    )

    config = load_config(config_path)

    repo = config.repos["demo"]
    harness = config.harnesses["local"]
    assert repo.repo_path == Path("/repos/demo")
    assert repo.global_concurrency == 3
    assert repo.per_prd_concurrency == 2
    assert harness.command == "codex"
    assert harness.args_template == ("run", "--repo", "{repo_path}")


def test_missing_required_repo_field_raises_clear_error(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    with pytest.raises(ConfigError, match="repo 'demo' must define non-empty 'repo_path'"):
        load_config(config_path)


def test_unknown_harness_reference_raises_error(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: missing
""".strip(),
    )

    with pytest.raises(ConfigError, match="references unknown harness 'missing'"):
        load_config(config_path)


def test_repo_concurrency_defaults_are_applied(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    config = load_config(config_path)

    repo = config.repos["demo"]
    assert repo.global_concurrency == 1
    assert repo.per_prd_concurrency == 1


def test_harness_command_template_is_loaded(tmp_path: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
    args_template:
      - run
      - --branch
      - "{main_branch}"
repos:
  demo:
    repo_path: /repos/demo
    main_branch: trunk
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    config = load_config(config_path)
    harness = config.harnesses["local"]

    assert harness.args_template == ("run", "--branch", "{main_branch}")


def test_observability_config_defaults_disabled(tmp_path: Path) -> None:
    """When no observability section is present, defaults are used."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    config = load_config(config_path)
    obs = config.observability

    assert obs.enabled is False
    assert obs.session_prefix == "rangkai"
    assert obs.url is None
    assert obs.token is None


def test_observability_config_enabled_with_url_and_token(tmp_path: Path) -> None:
    """Observability section supports enabled, url, token, and session_prefix."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
observability:
  enabled: true
  session_prefix: my-app
  url: https://observability.example.com
  token: secret-api-token
""".strip(),
    )

    config = load_config(config_path)
    obs = config.observability

    assert obs.enabled is True
    assert obs.session_prefix == "my-app"
    assert obs.url == "https://observability.example.com"
    assert obs.token == "secret-api-token"


def test_observability_partial_config_includes_only_specified_fields(tmp_path: Path) -> None:
    """Observability config loads only the fields that are specified."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
observability:
  enabled: true
  url: https://example.com
""".strip(),
    )

    config = load_config(config_path)
    obs = config.observability

    assert obs.enabled is True
    assert obs.session_prefix == "rangkai"  # default
    assert obs.url == "https://example.com"
    assert obs.token is None


def test_observability_invalid_url_type_raises_error(tmp_path: Path) -> None:
    """Non-string url in observability config raises ConfigError."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
observability:
  enabled: true
  url: 123
""".strip(),
    )

    with pytest.raises(ConfigError, match="observability.url must be a string"):
        load_config(config_path)


def test_observability_invalid_token_type_raises_error(tmp_path: Path) -> None:
    """Non-string token in observability config raises ConfigError."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
observability:
  enabled: true
  token: 456
""".strip(),
    )

    with pytest.raises(ConfigError, match="observability.token must be a string"):
        load_config(config_path)


def test_discord_config_parses_from_yaml(tmp_path: Path) -> None:
    """Discord block is parsed into DiscordConfig (enabled, webhook_url)."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
discord:
  enabled: true
  webhook_url: https://discord.com/api/webhooks/test
""".strip(),
    )

    config = load_config(config_path)

    assert isinstance(config.discord, DiscordConfig)
    assert config.discord.enabled is True
    assert config.discord.webhook_url == "https://discord.com/api/webhooks/test"


def test_discord_webhook_url_env_override(tmp_path: Path, monkeypatch) -> None:
    """DISCORD_WEBHOOK_URL env var overrides YAML webhook_url."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/from-env")

    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
discord:
  enabled: true
  webhook_url: https://discord.com/api/webhooks/from-yaml
""".strip(),
    )

    config = load_config(config_path)

    assert config.discord.enabled is True
    assert config.discord.webhook_url == "https://discord.com/api/webhooks/from-env"


def test_discord_env_only_no_yaml(tmp_path: Path, monkeypatch) -> None:
    """DISCORD_WEBHOOK_URL env var sets webhook_url even without YAML discord block."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/env-only")

    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    config = load_config(config_path)

    assert config.discord.webhook_url == "https://discord.com/api/webhooks/env-only"


# ── Quality Gate config tests ──────────────────────────────────────


def test_quality_gate_omitted_defaults_disabled(tmp_path: Path) -> None:
    """When quality_gate is omitted, it defaults to disabled."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
""".strip(),
    )

    config = load_config(config_path)
    repo = config.repos["demo"]

    assert repo.quality_gate.enabled is False
    assert repo.quality_gate.command is None
    assert repo.quality_gate.args_template == ()
    assert repo.quality_gate.timeout_seconds is None


def test_quality_gate_disabled_explicitly(tmp_path: Path) -> None:
    """When quality_gate is present but enabled is false, it stays disabled."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
    quality_gate:
      enabled: false
""".strip(),
    )

    config = load_config(config_path)
    repo = config.repos["demo"]

    assert repo.quality_gate.enabled is False


def test_quality_gate_enabled_with_command_and_args(tmp_path: Path) -> None:
    """When quality_gate is enabled, command and args_template are parsed."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
    quality_gate:
      enabled: true
      command: saringan
      args_template:
        - validate
        - --repo
        - "{repo_name}"
        - --issue
        - "{issue_number}"
""".strip(),
    )

    config = load_config(config_path)
    gate = config.repos["demo"].quality_gate

    assert gate.enabled is True
    assert gate.command == "saringan"
    assert gate.args_template == ("validate", "--repo", "{repo_name}", "--issue", "{issue_number}")
    assert gate.timeout_seconds is None


def test_quality_gate_enabled_with_timeout(tmp_path: Path) -> None:
    """Quality gate supports optional timeout_seconds."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
    quality_gate:
      enabled: true
      command: saringan
      timeout_seconds: 600
""".strip(),
    )

    config = load_config(config_path)
    gate = config.repos["demo"].quality_gate

    assert gate.enabled is True
    assert gate.timeout_seconds == 600


def test_quality_gate_enabled_missing_command_raises_error(tmp_path: Path) -> None:
    """When quality_gate is enabled but command is missing, raises ConfigError."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
    quality_gate:
      enabled: true
""".strip(),
    )

    with pytest.raises(ConfigError, match="quality_gate must define non-empty 'command'"):
        load_config(config_path)


def test_quality_gate_not_a_mapping_raises_error(tmp_path: Path) -> None:
    """When quality_gate is not a mapping, raises ConfigError."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
    quality_gate: "not-a-mapping"
""".strip(),
    )

    with pytest.raises(ConfigError, match="quality_gate must be a mapping"):
        load_config(config_path)


def test_quality_gate_invalid_timeout_raises_error(tmp_path: Path) -> None:
    """When quality_gate timeout_seconds is not a positive int, raises ConfigError."""
    config_path = write_config(
        tmp_path,
        """
harnesses:
  local:
    command: codex
repos:
  demo:
    repo_path: /repos/demo
    main_branch: main
    worktree_root: /worktrees/demo
    default_harness: local
    quality_gate:
      enabled: true
      command: saringan
      timeout_seconds: 0
""".strip(),
    )

    with pytest.raises(ConfigError, match="quality_gate timeout_seconds must be a positive integer"):
        load_config(config_path)
