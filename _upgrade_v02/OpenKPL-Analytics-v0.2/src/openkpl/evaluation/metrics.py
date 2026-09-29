import numpy as np
from sklearn.metrics import log_loss,brier_score_loss,accuracy_score
def binary_metrics(y,p):
    y=np.asarray(y,float); p=np.clip(np.asarray(p,float),1e-8,1-1e-8)
    return {"n":int(len(y)),"log_loss":float(log_loss(y,p,labels=[0,1])),
            "brier_score":float(brier_score_loss(y,p)),"accuracy":float(accuracy_score(y,p>=.5))}
