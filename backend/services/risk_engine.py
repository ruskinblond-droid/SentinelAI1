def calculate_risk(anomaly_score: float):
    """
    Convert an anomaly score (0-100)
    into a risk level and security action.
    """

    anomaly_score = max(0, min(100, anomaly_score))

    if anomaly_score < 30:
        return {
            "risk_score": anomaly_score,
            "risk_level": "LOW",
            "action": "CONTINUE"
        }

    elif anomaly_score < 60:
        return {
            "risk_score": anomaly_score,
            "risk_level": "MEDIUM",
            "action": "MONITOR"
        }

    elif anomaly_score < 80:
        return {
            "risk_score": anomaly_score,
            "risk_level": "HIGH",
            "action": "REAUTHENTICATE"
        }

    else:
        return {
            "risk_score": anomaly_score,
            "risk_level": "CRITICAL",
            "action": "LOCK_SESSION"
        }