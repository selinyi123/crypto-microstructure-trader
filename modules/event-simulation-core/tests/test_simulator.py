from simulator import Event, EventScorer


def test_event_scorer_accepts_strong_event():
    decision = EventScorer().score(Event(name="sample", strength=0.8, timestamp=1.0))
    assert decision.action == "accept"
    assert decision.score == 0.8
