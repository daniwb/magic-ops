"""Host-independent checkout locations for the Factory control plane."""
import os
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("FACTORY_NG_SOURCE", str(OPS.parent / "test/openmagic")))


def local_gate_command(command):
    """Resolve relocated control-plane tools without changing stored contracts."""
    return command.replace("/opt/development/magic-ops/", str(OPS) + "/")
