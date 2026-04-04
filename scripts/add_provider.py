#!/usr/bin/env python3
"""Add a new OpenAI-compatible LLM provider to tradingagent_a.

Automatically registers the provider across all required files:
  1. tradingagents/llm_clients/openai_client.py  (_PROVIDER_CONFIG dict)
  2. tradingagents/llm_clients/factory.py         (routing tuple)
  3. tradingagents/llm_clients/model_catalog.py   (MODEL_OPTIONS dict)
  4. .env.example                                  (API key env var)
  5. cli/utils.py                                  (BASE_URLS list)

Usage:
    # Interactive mode (no arguments):
    python scripts/add_provider.py

    # CLI mode:
    python scripts/add_provider.py \\
        --name "deepseek" \\
        --base-url "https://api.deepseek.com/v1" \\
        --api-key-env "DEEPSEEK_API_KEY" \\
        --models "deepseek-chat,deepseek-reasoner"

    # Dry-run (preview changes without writing):
    python scripts/add_provider.py --dry-run \\
        --name "deepseek" \\
        --base-url "https://api.deepseek.com/v1" \\
        --api-key-env "DEEPSEEK_API_KEY" \\
        --models "deepseek-chat,deepseek-reasoner"

    # Separate quick/deep models:
    python scripts/add_provider.py \\
        --name "deepseek" \\
        --base-url "https://api.deepseek.com/v1" \\
        --api-key-env "DEEPSEEK_API_KEY" \\
        --quick-models "deepseek-chat" \\
        --deep-models "deepseek-reasoner"
"""

import argparse
import ast
import re
import sys
from pathlib import Path

try:
    import questionary
    from questionary import Style
except ImportError:
    questionary = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FILES = {
    "provider_config": PROJECT_ROOT / "tradingagents" / "llm_clients" / "openai_client.py",
    "factory": PROJECT_ROOT / "tradingagents" / "llm_clients" / "factory.py",
    "model_catalog": PROJECT_ROOT / "tradingagents" / "llm_clients" / "model_catalog.py",
    "env_example": PROJECT_ROOT / ".env.example",
    "cli_utils": PROJECT_ROOT / "cli" / "utils.py",
}

# questionary style matching the project CLI
_QSTYLE = Style([
    ("qmark", "fg:magenta bold"),
    ("question", "bold"),
    ("answer", "fg:magenta"),
    ("pointer", "fg:magenta"),
    ("highlighted", "fg:magenta bold"),
    ("selected", "fg:magenta"),
    ("text", ""),
])


def parse_args():
    p = argparse.ArgumentParser(
        description="Add an OpenAI-compatible LLM provider to tradingagent_a. "
                    "Run without arguments for interactive mode."
    )
    p.add_argument("--name", default=None,
                   help="Provider name, lowercase (e.g. 'deepseek')")
    p.add_argument("--base-url", default=None,
                   help="API base URL (e.g. 'https://api.deepseek.com/v1')")
    p.add_argument("--api-key-env", default=None,
                   help="Env var name for API key (omit for no-auth providers)")
    p.add_argument("--models", default=None,
                   help="Comma-separated model IDs (used for both quick and deep if --quick/deep not specified)")
    p.add_argument("--quick-models", default=None,
                   help="Comma-separated model IDs for quick thinking")
    p.add_argument("--deep-models", default=None,
                   help="Comma-separated model IDs for deep thinking")
    p.add_argument("--display-name", default=None,
                   help="CLI display name (default: title-cased name)")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview changes without modifying files")
    return p.parse_args()


# -- interactive mode ------------------------------------------------------------

def interactive_mode() -> dict:
    """Collect all parameters via interactive prompts."""
    if questionary is None:
        sys.exit("Error: interactive mode requires 'questionary'. Install with: pip install questionary")

    print("\n=== Add New LLM Provider ===\n")

    # Step 1: Provider name
    name = questionary.text(
        "Provider name (lowercase, e.g. deepseek):",
        validate=lambda x: bool(re.match(r'^[a-z][a-z0-9_-]*$', x.strip())) or "Must be lowercase alphanumeric/underscore",
        style=_QSTYLE,
    ).ask()
    if not name:
        sys.exit("Cancelled.")
    name = name.strip()

    # Step 2: Display name
    default_display = name.replace("-", " ").title()
    display_name = questionary.text(
        f"Display name for CLI menus (default: {default_display}):",
        default=default_display,
        style=_QSTYLE,
    ).ask()
    if not display_name:
        sys.exit("Cancelled.")
    display_name = display_name.strip() or default_display

    # Step 3: Base URL
    base_url = questionary.text(
        "API base URL (e.g. https://api.deepseek.com/v1):",
        validate=lambda x: x.strip().startswith(("https://", "http://")) or "Must start with https:// or http://",
        style=_QSTYLE,
    ).ask()
    if not base_url:
        sys.exit("Cancelled.")
    base_url = base_url.strip().rstrip("/")

    # Step 4: API key env var
    has_api_key = questionary.confirm(
        "Does this provider require an API key?",
        default=True,
        style=_QSTYLE,
    ).ask()
    if has_api_key is None:
        sys.exit("Cancelled.")

    api_key_env = None
    if has_api_key:
        default_key_env = name.upper().replace("-", "_") + "_API_KEY"
        api_key_env = questionary.text(
            f"Environment variable name for API key (default: {default_key_env}):",
            default=default_key_env,
            validate=lambda x: bool(x.strip()) or "Must not be empty",
            style=_QSTYLE,
        ).ask()
        if not api_key_env:
            sys.exit("Cancelled.")
        api_key_env = api_key_env.strip() or default_key_env

    # Step 5: Model assignment strategy
    strategy = questionary.select(
        "How to assign models to quick/deep categories?",
        choices=[
            "Same models for both quick and deep",
            "Specify quick and deep models separately",
        ],
        style=_QSTYLE,
    ).ask()
    if not strategy:
        sys.exit("Cancelled.")

    quick_models: list[str] = []
    deep_models: list[str] = []

    if "Same" in strategy:
        models_str = questionary.text(
            "Model IDs (comma-separated, e.g. deepseek-chat,deepseek-reasoner):",
            validate=lambda x: bool(x.strip()) or "At least one model required",
            style=_QSTYLE,
        ).ask()
        if not models_str:
            sys.exit("Cancelled.")
        quick_models = deep_models = [m.strip() for m in models_str.split(",") if m.strip()]
    else:
        quick_str = questionary.text(
            "Quick-thinking model IDs (comma-separated):",
            validate=lambda x: bool(x.strip()) or "At least one model required",
            style=_QSTYLE,
        ).ask()
        if quick_str is None:
            sys.exit("Cancelled.")

        deep_str = questionary.text(
            "Deep-thinking model IDs (comma-separated):",
            validate=lambda x: bool(x.strip()) or "At least one model required",
            style=_QSTYLE,
        ).ask()
        if deep_str is None:
            sys.exit("Cancelled.")

        quick_models = [m.strip() for m in quick_str.split(",") if m.strip()]
        deep_models = [m.strip() for m in deep_str.split(",") if m.strip()]

    # Summary & confirm
    print(f"\n--- Summary ---")
    print(f"  Name:        {name}")
    print(f"  Display:     {display_name}")
    print(f"  Base URL:    {base_url}")
    print(f"  API Key Env: {api_key_env or '(no auth)'}")
    print(f"  Quick:       {', '.join(quick_models)}")
    print(f"  Deep:        {', '.join(deep_models)}")

    action = questionary.select(
        "Proceed?",
        choices=[
            "Apply changes",
            "Dry-run (preview only)",
            "Cancel",
        ],
        style=_QSTYLE,
    ).ask()

    if not action or "Cancel" in action:
        sys.exit("Cancelled.")

    dry_run = "Dry-run" in action

    return {
        "name": name,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "display_name": display_name,
        "quick_models": quick_models,
        "deep_models": deep_models,
        "dry_run": dry_run,
    }


# -- validation -----------------------------------------------------------------

def validate(name: str, base_url: str, quick_models: list[str], deep_models: list[str]):
    if not re.match(r'^[a-z][a-z0-9_-]*$', name):
        sys.exit(f"Error: --name must be lowercase alphanumeric/underscore, got '{name}'")
    if not base_url.startswith(("https://", "http://")):
        sys.exit(f"Error: --base-url must start with https:// or http://")
    if not quick_models and not deep_models:
        sys.exit("Error: at least one model must be specified via --models, --quick-models, or --deep-models")

    for label, path in FILES.items():
        if not path.exists():
            sys.exit(f"Error: required file not found: {path}")


# -- file editors ---------------------------------------------------------------

def edit_provider_config(name: str, base_url: str, api_key_env: str | None,
                         dry_run: bool = False) -> None:
    """Add (base_url, api_key_env) to _PROVIDER_CONFIG in openai_client.py."""
    path = FILES["provider_config"]
    text = path.read_text(encoding="utf-8")

    if f'"{name}":' in text:
        _skip(path, "entry already in _PROVIDER_CONFIG")
        return

    api_key_str = f'"{api_key_env}"' if api_key_env else "None"
    new_line = f'    "{name}": ("{base_url}", {api_key_str}),'

    # Insert before the closing } of _PROVIDER_CONFIG
    pattern = r'(\n    "[^"]+":\s*\([^)]+\),\n)(})'
    matches = list(re.finditer(pattern, text))
    if not matches:
        sys.exit(f"Error: could not find _PROVIDER_CONFIG closing in {path}")

    last = matches[-1]
    insert_at = last.start(2)
    result = text[:insert_at] + new_line + "\n" + text[insert_at:]

    if dry_run:
        _preview(path, new_line.strip())
        return

    path.write_text(result, encoding="utf-8")
    _ok(path, "+1 entry in _PROVIDER_CONFIG")


def edit_factory(name: str, dry_run: bool = False) -> None:
    """Add provider name to the OpenAI-compatible routing tuple in factory.py."""
    path = FILES["factory"]
    text = path.read_text(encoding="utf-8")

    if f'"{name}"' in text.split("raise ValueError")[0]:
        _skip(path, "already in routing")
        return

    # Match: if provider_lower in ("openai", "ollama", "openrouter"):
    pattern = r'if provider_lower in \([^)]+\):'
    match = re.search(pattern, text)
    if not match:
        sys.exit(f"Error: could not find routing tuple in {path}")

    old = match.group(0)
    new = old.replace("):", f', "{name}"):')

    if dry_run:
        _preview(path, f"{old}  -->  {new}")
        return

    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    _ok(path, f'+{name} in routing tuple')


def edit_model_catalog(name: str, quick_models: list[str], deep_models: list[str],
                       display_name: str, dry_run: bool = False) -> None:
    """Add provider + models to MODEL_OPTIONS in model_catalog.py."""
    path = FILES["model_catalog"]
    text = path.read_text(encoding="utf-8")

    if re.search(rf'"{name}"\s*:', text):
        _skip(path, "provider already in MODEL_OPTIONS")
        return

    def _build_entries(models: list[str]) -> str:
        return ",\n            ".join(
            f'("{display_name} {m}", "{m}")' for m in models
        )

    quick_entries = _build_entries(quick_models) if quick_models else ""
    deep_entries = _build_entries(deep_models) if deep_models else ""

    lines = [f'    "{name}": {{']
    if quick_entries:
        lines.append('        "quick": [')
        lines.append(f'            {quick_entries},')
        lines.append('        ],')
    if deep_entries:
        lines.append('        "deep": [')
        lines.append(f'            {deep_entries},')
        lines.append('        ],')
    lines.append("    },")
    block = "\n".join(lines)

    # Find the final closing "}" of MODEL_OPTIONS dict
    pattern = r'\n\}\n\n\ndef '
    match = re.search(pattern, text)
    if not match:
        pattern = r'\n\}\n\n'
        match = re.search(pattern, text)
        if not match:
            sys.exit(f"Error: could not find MODEL_OPTIONS closing in {path}")

    insert_pos = match.start() + 1
    result = text[:insert_pos] + block + "\n" + text[insert_pos:]

    if dry_run:
        _preview(path, block)
        return

    path.write_text(result, encoding="utf-8")
    _ok(path, f"+quick:{len(quick_models)} deep:{len(deep_models)} models for {name}")


def edit_env_example(api_key_env: str | None, dry_run: bool = False) -> None:
    """Add API_KEY_ENV= line to .env.example."""
    if not api_key_env:
        print("  SKIP .env.example (no --api-key-env specified)")
        return

    path = FILES["env_example"]
    text = path.read_text(encoding="utf-8")

    if api_key_env in text:
        _skip(path, f"{api_key_env} already present")
        return

    new_line = f"{api_key_env}=\n"

    if dry_run:
        _preview(path, new_line.strip())
        return

    if not text.endswith("\n"):
        text += "\n"
    text += new_line
    path.write_text(text, encoding="utf-8")
    _ok(path, f"+{api_key_env}=")


def edit_cli_utils(name: str, base_url: str, display_name: str,
                   dry_run: bool = False) -> None:
    """Add provider to BASE_URLS list in cli/utils.py."""
    path = FILES["cli_utils"]
    text = path.read_text(encoding="utf-8")

    if f'"{display_name}"' in text and base_url in text:
        _skip(path, "already in BASE_URLS")
        return

    new_entry = f'        ("{display_name}", "{base_url}"),'

    # Find last entry in the BASE_URLS list before the closing ]
    pattern = r'(\("[A-Za-z. ]+",\s*"https?://[^"]+"\),\n)(    \])'
    matches = list(re.finditer(pattern, text))
    if not matches:
        pattern2 = r'(\("[A-Za-z. ]+",\s*"[^"]*"\),\n)(    \])'
        matches = list(re.finditer(pattern2, text))
        if not matches:
            print(f"  WARN {path.relative_to(PROJECT_ROOT)} (could not auto-insert, add manually)")
            return

    last = matches[-1]
    insert_at = last.start(2)
    result = text[:insert_at] + new_entry + "\n" + text[insert_at:]

    if dry_run:
        _preview(path, new_entry.strip())
        return

    path.write_text(result, encoding="utf-8")
    _ok(path, f"+{display_name}")


# -- syntax check ---------------------------------------------------------------

def validate_syntax(path: Path) -> None:
    """Verify file still parses as valid Python."""
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        sys.exit(f"Error: {path} has syntax error after modification: {e}")


# -- helpers --------------------------------------------------------------------

def _ok(path: Path, msg: str):
    print(f"  OK   {str(path.relative_to(PROJECT_ROOT)):55s} {msg}")


def _skip(path: Path, reason: str):
    print(f"  SKIP {str(path.relative_to(PROJECT_ROOT)):55s} ({reason})")


def _preview(path: Path, change: str):
    print(f"  WOULD {str(path.relative_to(PROJECT_ROOT)):55s}")
    for line in change.split("\n"):
        print(f"        {line}")


# -- main -----------------------------------------------------------------------

def run(params: dict) -> None:
    """Execute the provider registration with resolved parameters."""
    name = params["name"]
    base_url = params["base_url"]
    display_name = params["display_name"]
    api_key_env = params["api_key_env"]
    quick_models = params["quick_models"]
    deep_models = params["deep_models"]
    dry_run = params["dry_run"]

    validate(name, base_url, quick_models, deep_models)

    if dry_run:
        print(f"\n[DRY RUN] Provider '{name}' ({display_name}):")
    else:
        print(f"\nAdding provider '{name}' ({display_name}):")
    print(f"  Base URL:  {base_url}")
    print(f"  API Key:   {api_key_env or '(no auth)'}")
    print(f"  Quick:     {', '.join(quick_models) or '(none)'}")
    print(f"  Deep:      {', '.join(deep_models) or '(none)'}\n")

    edit_provider_config(name, base_url, api_key_env, dry_run=dry_run)
    edit_factory(name, dry_run=dry_run)
    edit_model_catalog(name, quick_models, deep_models, display_name, dry_run=dry_run)
    edit_env_example(api_key_env, dry_run=dry_run)
    edit_cli_utils(name, base_url, display_name, dry_run=dry_run)

    # Post-modification syntax validation (only when actually writing)
    if not dry_run:
        print("\nValidating syntax...")
        for key in ("provider_config", "factory", "model_catalog", "cli_utils"):
            validate_syntax(FILES[key])
        print("  All files pass syntax check.")

    print(f"\nDone! Usage:")
    model_hint = (quick_models or deep_models)[0]
    print(f'  config["llm_provider"] = "{name}"')
    print(f'  config["deep_think_llm"] = "{model_hint}"')
    print(f'  config["quick_think_llm"] = "{model_hint}"')
    if api_key_env:
        print(f'  # Set {api_key_env}=your_key in .env')


def main():
    args = parse_args()

    # If no provider arguments given, launch interactive mode
    has_cli_args = args.name or args.base_url or args.models or args.quick_models or args.deep_models

    if has_cli_args:
        # CLI mode — validate required args
        if not args.name or not args.base_url:
            sys.exit("Error: --name and --base-url are required in CLI mode")
        name = args.name.lower().strip()
        base_url = args.base_url.rstrip("/")
        display_name = args.display_name or name.replace("-", " ").title()

        if args.quick_models or args.deep_models:
            quick_models = [m.strip() for m in args.quick_models.split(",") if m.strip()] if args.quick_models else []
            deep_models = [m.strip() for m in args.deep_models.split(",") if m.strip()] if args.deep_models else []
        elif args.models:
            quick_models = deep_models = [m.strip() for m in args.models.split(",") if m.strip()]
        else:
            sys.exit("Error: specify --models or --quick-models/--deep-models")

        run({
            "name": name,
            "base_url": base_url,
            "api_key_env": args.api_key_env,
            "display_name": display_name,
            "quick_models": quick_models,
            "deep_models": deep_models,
            "dry_run": args.dry_run,
        })
    else:
        # Interactive mode
        params = interactive_mode()
        run(params)


if __name__ == "__main__":
    main()
