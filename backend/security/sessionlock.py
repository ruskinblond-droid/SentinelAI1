def should_lock_session(risk_level: str) -> bool:
    return risk_level == "CRITICAL"


def get_lock_action(risk_level: str) -> str:
    if risk_level == "CRITICAL":
        return "LOCK_SESSION"

    if risk_level == "HIGH":
        return "REAUTHENTICATE"

    if risk_level == "MEDIUM":
        return "MONITOR"

    return "CONTINUE"