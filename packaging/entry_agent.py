"""PyInstaller entry point for ufo-agent.exe.

Built by .github/workflows/ci.yml on windows-latest. Keeping this as a real
file (instead of `-m agent.main`) gives PyInstaller a stable analysis root.
"""

from agent.main import run

if __name__ == "__main__":
    run()
