"""
installer.py — Legacy alias forwarding to M5 setup_guide.py.
"""

from src.cli.setup_guide import run_setup_wizard

def run_installer():
    run_setup_wizard()

if __name__ == "__main__":
    run_installer()
