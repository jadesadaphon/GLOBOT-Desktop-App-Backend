@echo off
echo Setting up the Python environment...

python -m venv .venv

echo Activating virtual environment and installing requirements...
.\.venv\Scripts\pip.exe install -r requirements.txt

echo Setup complete. You can now start developing!
pause