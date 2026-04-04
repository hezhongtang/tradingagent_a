@echo off
REM Build script for tradingagents Windows executable
REM Usage: .\build_exe.bat

echo ========================================
echo Building tradingagents Windows executable
echo ========================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found, installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller
        pause
        exit /b 1
    )
)

echo.
echo Cleaning previous build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo Starting PyInstaller build...
pyinstaller pyinstaller.spec

if errorlevel 1 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo Output executable: dist\tradingagents.exe
echo.
echo To run: .\dist\tradingagents.exe
echo.
pause
