"""
Bacchus - Local LLM Chat Application for Intel NPU
Entry point for the application.
"""

import sys


def main():
    """Application entry point."""
    from bacchus.app import run_application
    return run_application(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
