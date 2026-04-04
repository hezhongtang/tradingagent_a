"""
Automatic self-update mechanism for Windows executable.
Checks GitHub Releases for new versions, downloads, and self-updates.
"""

import os
import sys
import time
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from requests.exceptions import RequestException
from packaging.version import Version, InvalidVersion
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn
from questionary import confirm

from .config import CLI_CONFIG


# GitHub configuration
GITHUB_OWNER = CLI_CONFIG.get("github_owner", "hezhongtang")
GITHUB_REPO = CLI_CONFIG.get("github_repo", "tradingagent_a")
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_API_TIMEOUT = CLI_CONFIG.get("github_api_timeout", 10.0)


def is_running_as_pyinstaller() -> bool:
    """Check if we're running from a PyInstaller bundled executable."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def is_running_on_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform.startswith('win')


def _load_tomllib():
    """Load tomllib (Python >= 3.11) or tomli (Python 3.10)."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            # If tomli not installed, we can't read the file
            return None
    return tomllib


def get_current_version() -> str:
    """Read current version from pyproject.toml."""
    # Handle PyInstaller case differently
    if is_running_as_pyinstaller():
        # In bundled mode, pyproject.toml should be in the same directory
        # structure relative to the exe
        exe_path = Path(sys.executable).resolve()
        # Look for pyproject.toml in parent directories
        # Typically, for one-file build, it's next to the exe
        candidate = exe_path.parent / "pyproject.toml"
        if candidate.exists():
            tomllib = _load_tomllib()
            if tomllib:
                try:
                    with open(candidate, "rb") as f:
                        data = tomllib.load(f)
                        version = data.get("project", {}).get("version", "0.0.0")
                        return version
                except (OSError, KeyError):
                    pass
        # If we can't find it, check the old location too
        current_file = Path(__file__)
        project_root = current_file.parent.parent
        pyproject_path = project_root / "pyproject.toml"
        if pyproject_path.exists():
            tomllib = _load_tomllib()
            if tomllib:
                try:
                    with open(pyproject_path, "rb") as f:
                        data = tomllib.load(f)
                        version = data.get("project", {}).get("version", "0.0.0")
                        return version
                except (OSError, KeyError):
                    pass
    else:
        # Development mode
        current_file = Path(__file__)
        project_root = current_file.parent.parent
        pyproject_path = project_root / "pyproject.toml"
        if pyproject_path.exists():
            tomllib = _load_tomllib()
            if tomllib:
                try:
                    with open(pyproject_path, "rb") as f:
                        data = tomllib.load(f)
                        version = data.get("project", {}).get("version", "0.0.0")
                        return version
                except (OSError, KeyError):
                    pass

    # Fallback version if we can't read
    return "0.2.3"


def check_for_updates() -> Optional[Dict[str, Any]]:
    """
    Check GitHub for latest release.
    Returns update info if newer version available, None otherwise.
    """
    if not is_running_on_windows() or not is_running_as_pyinstaller():
        return None

    current_version_str = get_current_version()
    current_version_str = current_version_str.lstrip('v')

    try:
        response = requests.get(GITHUB_API_URL, timeout=GITHUB_API_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        tag_name = data.get("tag_name", "").lstrip('v')
        if not tag_name:
            return None

        # Parse versions
        try:
            current_version = Version(current_version_str)
            latest_version = Version(tag_name)
        except InvalidVersion:
            return None

        # Check if newer
        if latest_version <= current_version:
            return None

        # Find Windows exe asset
        assets = data.get("assets", [])
        exe_asset = None
        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".exe"):
                exe_asset = asset
                break

        if not exe_asset:
            # No exe found in this release
            return None

        return {
            "current_version": current_version_str,
            "latest_version": tag_name,
            "release_notes": data.get("body", "No release notes provided."),
            "html_url": data.get("html_url", ""),
            "download_url": exe_asset.get("browser_download_url", ""),
            "size": exe_asset.get("size", 0),
        }

    except RequestException:
        # Network/API request error - silent fail
        return None
    except (ValueError, KeyError, TypeError):
        # JSON parsing or data extraction error - silent fail
        return None


def download_update(download_url: str, console: Console) -> Optional[Path]:
    """
    Download update to temp directory.
    Returns path to downloaded file on success, None on failure.
    """
    try:
        temp_dir = Path(tempfile.gettempdir())
        timestamp = int(time.time())
        temp_file = temp_dir / f"tradingagents_update_{timestamp}.exe"

        response = requests.get(download_url, stream=True, timeout=GITHUB_API_TIMEOUT * 2)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[green]Downloading update...", total=total_size)
            with open(temp_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

        # Verify download
        if temp_file.stat().st_size == 0:
            console.print("[red]Download failed: file is empty[/red]")
            temp_file.unlink()
            return None

        return temp_file

    except RequestException as e:
        console.print(f"[red]Failed to download update: {str(e)}[/red]")
        return None
    except OSError as e:
        console.print(f"[red]File system error writing download: {str(e)}[/red]")
        return None


def create_update_batch(temp_exe: Path, target_exe: Path) -> Path:
    """
    Create batch script that updates the executable after exit.
    Returns path to the batch script.
    """
    temp_dir = temp_exe.parent
    timestamp = int(time.time())
    batch_path = temp_dir / f"tradingagents_update_{timestamp}.bat"

    target_dir = target_exe.parent
    # Use dynamic backup name based on actual target name
    backup_name = f"{target_exe.stem}.old.exe"
    backup_path = target_dir / backup_name

    # Batch script template
    batch_content = f'''@echo off
chcp 65001 >nul
echo Waiting for application to exit...
timeout /t 3 /nobreak >nul

set "TEMP_UPDATE_FILE={temp_exe}"
set "TARGET_EXE={target_exe}"
set "BACKUP_OLD={backup_path}"

REM Backup original
if exist "%TARGET_EXE%" (
    move /Y "%TARGET_EXE%" "%BACKUP_OLD%" >nul
)

REM Copy new version
copy /Y "%TEMP_UPDATE_FILE%" "%TARGET_EXE%"

if errorlevel 1 (
    echo.
    echo [31mERROR: Failed to copy update! Rolling back...[0m
    if exist "%BACKUP_OLD%" (
        move /Y "%BACKUP_OLD%" "%TARGET_EXE%" >nul
    )
    del "%TEMP_UPDATE_FILE%" >nul
    timeout /t 3 /nobreak >nul
    exit /b 1
)

REM Cleanup
del "%TEMP_UPDATE_FILE%" >nul

echo.
echo [32mUpdate completed successfully![0m
echo Starting new version...
timeout /t 1 /nobreak >nul

REM Start new version
start "" "%TARGET_EXE%"

REM Self-delete this batch file
del "%~f0"
'''

    with open(batch_path, "w", encoding="utf-8") as f:
        f.write(batch_content)

    return batch_path


def perform_update(temp_exe: Path, target_exe: Path) -> None:
    """
    Trigger the update: create batch and exit.
    After this function exits, Python exits and batch takes over.
    """
    batch_path = create_update_batch(temp_exe, target_exe)

    # Launch the batch script detached
    # CREATE_NO_WINDOW flag (0x08000000) prevents extra console window popup
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    subprocess.Popen(
        [str(batch_path)],
        shell=True,
        startupinfo=startupinfo,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )

    # Exit immediately - batch will do the work after we exit
    sys.exit(0)


def display_update_info(update_info: Dict[str, Any], console: Console) -> None:
    """Display update information in a Rich panel."""
    current = update_info["current_version"]
    latest = update_info["latest_version"]
    notes = update_info["release_notes"]
    url = update_info["html_url"]

    # Truncate long release notes
    if len(notes) > 500:
        notes = notes[:497] + "..."

    content = (
        f"[bold]Current version:[/bold] v{current}\n"
        f"[bold]New version:[/bold] v{latest}\n\n"
        f"[bold]Release notes:[/bold]\n{notes}\n\n"
        f"[link={url}]{url}[/link]"
    )

    panel = Panel(
        content,
        title="🎉 Update Available",
        border_style="yellow",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)
    console.print()


def check_and_prompt_update(console: Console) -> None:
    """
    Main entry point: check for updates and prompt user if available.
    If user accepts, start update process and exit.
    """
    # Only run on Windows PyInstaller exe
    if not is_running_on_windows() or not is_running_as_pyinstaller():
        return

    console.print("[dim]Checking for updates...[/dim]")

    update_info = check_for_updates()
    if not update_info:
        return

    # Display update info
    display_update_info(update_info, console)

    # Ask user for confirmation
    answer = confirm("Would you like to update now?").ask()
    if not answer:
        console.print("[dim]Update skipped. You can update later from the GitHub releases page.[/dim]")
        console.print()
        return

    console.print()

    # Download the update
    download_url = update_info["download_url"]
    if not download_url:
        console.print("[red]Error: No download URL found for this release.[/red]")
        console.print()
        return

    temp_exe = download_update(download_url, console)
    if not temp_exe:
        console.print()
        return

    console.print()
    console.print("[green]Download complete. Preparing update...[/green]")
    console.print("[yellow]The application will now exit and update.[/yellow]")

    # Get current running executable path
    target_exe = Path(sys.executable).resolve()

    # Trigger update - this will exit the process
    perform_update(temp_exe, target_exe)
