from linuxlab.lab.controller import LabController
from linuxlab.config import SESSION_FILE

def reset_lab(controller: LabController) -> bool:
    """Reset container environment and clear active session."""
    success = controller.reset()
    if SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
        except Exception:
            pass
    return success
