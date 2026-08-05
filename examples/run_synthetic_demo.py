"""Run the public aggregate-only medprov synthetic demonstration."""

from pathlib import Path

from medprov.cli import main


if __name__ == "__main__":
    destination = Path(__file__).resolve().parent / "synthetic_demo_output"
    raise SystemExit(main(["demo", "--out", str(destination)]))
