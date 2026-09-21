import pytest
import classifier

def test_classifier_predictions():
    # Road & traffic pothole test
    category, priority = classifier.predict("Pothole on main road", "Dangerous pothole causing severe accidents")
    assert category == "Roads & Traffic"
    assert priority == "High"

    # Garbage test
    category, priority = classifier.predict("Garbage overflow", "Bins are overflowing near hospital with foul smell")
    assert category == "Sanitation & Waste"

    # Water supply test
    category, priority = classifier.predict("No water supply", "Colony has no drinking water for 2 days")
    assert category == "Water Supply"

def test_classifier_low_confidence_fallback():
    # Random nonsense text should return None or low confidence fallback
    category, priority = classifier.predict("xyzabc123", "random meaningless text without civic keywords")
    # With thresholding, category or priority should be None if probability is low
    assert category is None or category in classifier._TRAINING_DATA
