"""
dam/main.py

Entry point for the `dam` command.
Delegates to cli.py which handles both TUI and headless modes.
"""

from dam.cli import main

if __name__ == "__main__":
    main()
