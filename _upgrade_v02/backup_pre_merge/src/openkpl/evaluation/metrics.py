import numpy as np
from sklearn.metrics import log_loss, brier_score_loss, accuracy_score

def score_binary(y, p):
    y=np.asarray(y); p=np.clip(np.asarray(p),1e-6,1-1e-6)
    return {
        "n": int(len(y)),
        "log_loss": float(log_loss(y,p,labels=[0,1])),
        "brier": float(brier_score_loss(y,p)),
        "accuracy": float(accuracy_score(y,p>=0.5)),
    }
