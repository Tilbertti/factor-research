import pytest
import pandas as pd
from portfolio.construction import equal_weight, weight_by_rank

def test_equal_weights_sum():
    scores_dict = {'ABC': 2.5, 'DEF': 1.9, 'GHI': 1.6, 'JKL': 1.4, 'MNO': 1.3, 'PQR': 1.2}
    scores = pd.Series(scores_dict)
    assert equal_weight(scores, 3).sum() == pytest.approx(1.0)

def test_weight_by_rank_sequence():
    scores_dict = {'ABC': 2.5, 'DEF': 1.9, 'GHI': 1.6, 'JKL': 1.4, 'MNO': 1.3, 'PQR': 1.2}
    scores = pd.Series(scores_dict)
    weights = weight_by_rank(scores, 4)
    ordered = weights[['ABC', 'DEF', 'GHI', 'JKL']]
    assert (ordered.diff().dropna() < 0).all()