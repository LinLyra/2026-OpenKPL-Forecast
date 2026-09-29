import numpy as np
from sklearn.metrics import log_loss, brier_score_loss, accuracy_score


def score_binary(y, p):
    """v0.1 metrics (keys: n, log_loss, brier, accuracy). Kept for compatibility."""
    y = np.asarray(y); p = np.clip(np.asarray(p), 1e-6, 1 - 1e-6)
    return {
        "n": int(len(y)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "accuracy": float(accuracy_score(y, p >= 0.5)),
    }


def binary_metrics(y, p):
    """v0.2 metrics (keys: n, log_loss, brier_score, accuracy)."""
    y = np.asarray(y, float); p = np.clip(np.asarray(p, float), 1e-8, 1 - 1e-8)
    return {"n": int(len(y)), "log_loss": float(log_loss(y, p, labels=[0, 1])),
            "brier_score": float(brier_score_loss(y, p)), "accuracy": float(accuracy_score(y, p >= .5))}
