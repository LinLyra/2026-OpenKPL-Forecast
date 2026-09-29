import unittest
import pandas as pd
from openkpl.modeling.elo import build_elo

class TestElo(unittest.TestCase):
    def test_no_future_leakage_in_first_prediction(self):
        df=pd.DataFrame([
            {"team_a":"A","team_b":"B","winner_team":"A","source_row":0},
            {"team_a":"A","team_b":"B","winner_team":"A","source_row":1},
        ])
        out=build_elo(df,k=24,initial=1500)
        self.assertAlmostEqual(out.iloc[0].p_a_elo,0.5)
        self.assertGreater(out.iloc[1].p_a_elo,0.5)

if __name__=="__main__": unittest.main()
