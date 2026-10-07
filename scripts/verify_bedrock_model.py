#!/usr/bin/env python3
"""Fail if Scope.Glacier still defaults its Bedrock model to Anthropic Claude.

Checks the client, analysis Lambda, Terraform variable and IAM policy,
``.env.example``, and the README. Exits 0 when Amazon Nova Lite is the
default and Converse is scoped to Nova resources.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NOVA_LITE = "us.amazon.nova-lite-v1:0"
# Kept split so this script does not itself contain the retired default id.
FORBIDDEN_DEFAULT = "anthropic." + "claude-3-haiku-20240307-v1:0"

SCAN_SKIP_DIRS = {
    ".git",
    ".cursor",
    ".venv",
    "venv",
    "openspec",
    "tests",
    "__pycache__",
    "node_modules",
    ".terraform",
}
SCAN_SUFFIXES = {".py", ".tf", ".md", ".example", ".yml", ".yaml", ".html"}


def collect_errors(root: Path | None = None) -> list[str]:
    """Return human-readable failures. An empty list means the tree is clean."""
    root = root or REPO_ROOT
    errors: list[str] = []

    for path in _scan_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        if FORBIDDEN_DEFAULT in text:
            errors.append(f"{path.relative_to(root)} still contains the retired Claude model id")

    client = _read(root, "bedrock_client.py", errors)
    if client is not None and f'DEFAULT_BEDROCK_MODEL_ID = "{NOVA_LITE}"' not in client:
        errors.append("bedrock_client.py does not default to Amazon Nova Lite")

    variables = _read(root, "terraform/variables.tf", errors)
    if variables is not None:
        if f'default     = "{NOVA_LITE}"' not in variables:
            errors.append("terraform/variables.tf does not default bedrock_model_id to Amazon Nova Lite")
        if 'startswith(lower(var.bedrock_model_id), "anthropic.")' not in variables:
            errors.append("terraform/variables.tf does not reject anthropic.* model ids")
        if 'strcontains(lower(var.bedrock_model_id), ".anthropic.")' not in variables:
            errors.append("terraform/variables.tf does not reject cross-region Anthropic inference profiles")

    env_example = _read(root, ".env.example", errors)
    if env_example is not None and f"BEDROCK_MODEL_ID={NOVA_LITE}" not in env_example:
        errors.append(".env.example does not set BEDROCK_MODEL_ID to Amazon Nova Lite")

    readme = _read(root, "README.md", errors)
    if readme is not None:
        if "Amazon Nova Lite" not in readme or NOVA_LITE not in readme:
            errors.append("README.md does not document Amazon Nova Lite")
        for retired in ("Claude Haiku", "Claude 3 Haiku"):
            if retired in readme:
                errors.append(f"README.md still names {retired} as the model in use")

    main_tf = _read(root, "terraform/main.tf", errors)
    if main_tf is not None:
        errors.extend(_iam_errors(main_tf))

    handler = _read(root, "src/lambda/glacier_analysis_handler.py", errors)
    if handler is not None and "resolve_bedrock_model_id" not in handler:
        errors.append("glacier_analysis_handler.py does not use the shared model-id resolver")

    return errors


def _iam_errors(main_tf: str) -> list[str]:
    errors: list[str] = []
    if "foundation-model/amazon.nova-*" not in main_tf:
        errors.append("Lambda IAM does not allow foundation-model/amazon.nova-*")
    if "inference-profile/us.amazon.nova-*" not in main_tf:
        errors.append("Lambda IAM does not allow inference-profile/us.amazon.nova-*")
    if "anthropic" in main_tf.lower():
        errors.append("Lambda IAM still names an Anthropic model")
    wildcard = _wildcard_statement(main_tf)
    if wildcard is None:
        errors.append('Lambda IAM is missing the Resource = "*" statement')
    elif "bedrock:" in wildcard:
        errors.append('bedrock:Converse is still granted on Resource = "*"')
    if '"bedrock:Converse"' not in main_tf:
        errors.append("Lambda IAM does not allow bedrock:Converse")
    return errors


def _wildcard_statement(main_tf: str) -> str | None:
    """Return the HCL statement object whose resource is a bare wildcard."""
    needle = 'Resource = "*"'
    start = 0
    while True:
        idx = main_tf.find(needle, start)
        if idx == -1:
            return None
        brace = main_tf.rfind("{", 0, idx)
        if brace == -1:
            return None
        end = main_tf.find("}", idx)
        if end == -1:
            return None
        statement = main_tf[brace : end + 1]
        if "{" not in statement[1:] and "}" not in statement[:-1]:
            return statement
        start = idx + len(needle)


def _scan_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SCAN_SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix in SCAN_SUFFIXES or path.name.endswith(".env.example"):
            found.append(path)
    return found


def _read(root: Path, relative: str, errors: list[str]) -> str | None:
    path = root / relative
    if not path.is_file():
        errors.append(f"missing {relative}")
        return None
    return path.read_text(encoding="utf-8")


def main() -> int:
    errors = collect_errors()
    if errors:
        print("Bedrock model verification failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Bedrock model defaults to {NOVA_LITE}; Anthropic defaults are absent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
