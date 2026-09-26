from linuxlab.lab.controller import LabController

def check_lab_health(controller: LabController) -> dict:
    """Returns a health summary of the lab container and key services."""
    running = controller.is_running()
    if not running:
        return {
            "status": "stopped",
            "container": controller.container_name,
            "web_app": "down",
            "payment_api": "down",
        }

    # Check services inside container
    code1, out1, _ = controller.exec_cmd("/usr/local/bin/systemctl is-active web-app")
    code2, out2, _ = controller.exec_cmd("/usr/local/bin/systemctl is-active payment-api")

    return {
        "status": "running",
        "container": controller.container_name,
        "web_app": out1.strip() if code1 == 0 else "inactive",
        "payment_api": out2.strip() if code2 == 0 else "inactive",
    }
