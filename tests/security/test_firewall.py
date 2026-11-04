from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def load_firewall_module():
    module_path = Path(".claude/hooks/security_firewall_v2.py")
    spec = importlib.util.spec_from_file_location("security_firewall_v2", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_blocks_dangerous_command() -> None:
    firewall_module = load_firewall_module()
    firewall = firewall_module.SecurityFirewall()

    result = firewall.process(
        '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}'
    )

    assert result["block"] is True


def test_allows_safe_write() -> None:
    firewall_module = load_firewall_module()
    firewall = firewall_module.SecurityFirewall()

    result = firewall.process(
        '{"tool_name":"Write","tool_input":{"path":"frontend/src/App.tsx",'
        '"content":"export default 1;"}}'
    )

    assert result["block"] is False


def test_blocks_protected_path() -> None:
    firewall_module = load_firewall_module()
    firewall = firewall_module.SecurityFirewall()

    result = firewall.process(
        '{"tool_name":"Write","tool_input":{"path":"C:/Users/me/.ssh/id_rsa","content":"x"}}'
    )

    assert result["block"] is True


def test_blocks_hardcoded_secret() -> None:
    firewall_module = load_firewall_module()
    firewall = firewall_module.SecurityFirewall()

    result = firewall.process(
        '{"tool_name":"Write","tool_input":{"path":"app/config.py",'
        '"content":"password = \\"hunter2-secret\\""}}'
    )

    assert result["block"] is True


def test_blocks_multiedit_to_protected_path() -> None:
    firewall_module = load_firewall_module()
    firewall = firewall_module.SecurityFirewall()

    result = firewall.process(
        '{"tool_name":"MultiEdit","tool_input":{"edits":'
        '[{"path":"/etc/hosts","new_string":"127.0.0.1 x"}]}}'
    )

    assert result["block"] is True


def test_fails_closed_on_malformed_payload() -> None:
    firewall_module = load_firewall_module()
    firewall = firewall_module.SecurityFirewall()

    assert firewall.process("not-json")["block"] is True
    assert firewall.process('{"tool_name":"Bash","tool_input":"oops"}')["block"] is True


@pytest.mark.parametrize("payload", ["{}", '{"tool_name":"Read","tool_input":{"path":"x"}}'])
def test_allows_unknown_or_read_tools(payload: str) -> None:
    firewall_module = load_firewall_module()
    firewall = firewall_module.SecurityFirewall()

    assert firewall.process(payload)["block"] is False