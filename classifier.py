"""
classifier.py — AI-based complaint classification for CCMS.

Uses scikit-learn TF-IDF + Multinomial Naive Bayes pipelines to predict:
  - ai_category : which civic service category best fits the complaint text
  - ai_priority : Low / Medium / High urgency level

Both models are trained once at module import time on a built-in sample dataset
and cached in memory. No pickle files are written to disk.
"""

from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.preprocessing import LabelEncoder
import re

# ---------------------------------------------------------------------------
# Training dataset
# Each entry: (title, description, category_label, priority_label)
# Categories must match the dropdown values in file_complaint.html
# ---------------------------------------------------------------------------
_TRAINING_DATA = [
    # Roads & Traffic — High
    ("Large pothole on main road", "There is a very large pothole on the main road causing accidents and vehicle damage. Many cars are breaking their tyres.", "Roads & Traffic", "High"),
    ("Road completely broken after rain", "Heavy rain has completely destroyed the road surface. Vehicles cannot pass. Several accidents have occurred today.", "Roads & Traffic", "High"),
    ("Traffic signal not working", "The traffic signal at the main crossing has been non-functional for 3 days. It is causing serious traffic jams and risk of accidents.", "Roads & Traffic", "High"),
    ("Road crack near school", "A dangerous crack has appeared on the road near the school gate. Children are at risk while crossing.", "Roads & Traffic", "High"),
    # Roads & Traffic — Medium
    ("Pothole on side road", "There is a moderate pothole on the side street. Vehicles slow down but traffic is flowing.", "Roads & Traffic", "Medium"),
    ("Speed breaker damaged", "The speed breaker on Elm Street is damaged and missing reflectors. Drivers don't notice it at night.", "Roads & Traffic", "Medium"),
    ("Road marking faded", "Road lane markings have completely faded on the highway stretch near the flyover.", "Roads & Traffic", "Medium"),
    ("Broken footpath tiles", "Several footpath tiles near the bus stop are cracked and broken making it difficult for pedestrians.", "Roads & Traffic", "Medium"),
    # Roads & Traffic — Low
    ("Minor pothole on lane", "Small pothole on a residential lane. Traffic is not heavily affected.", "Roads & Traffic", "Low"),
    ("Road sign tilted", "A road direction sign near the park has tilted slightly. It is still readable.", "Roads & Traffic", "Low"),

    # Sanitation & Waste — High
    ("Garbage overflowing near hospital", "Garbage bins near the hospital have been overflowing for 5 days. Foul smell and health risk for patients and visitors.", "Sanitation & Waste", "High"),
    ("Dead animal on street not removed", "A dead animal has been lying on the main street for 2 days. Severe smell and disease risk to the neighborhood.", "Sanitation & Waste", "High"),
    ("Open drain causing health hazard", "An open drain is overflowing with sewage on the residential street. Children playing nearby are at risk of disease.", "Sanitation & Waste", "High"),
    ("Sewage overflow", "Sewage water is overflowing onto the road and entering homes. Emergency cleanup needed immediately.", "Sanitation & Waste", "High"),
    # Sanitation & Waste — Medium
    ("Garbage not collected for 3 days", "The garbage truck has not visited our colony for the past 3 days. Bins are full and waste is piling up.", "Sanitation & Waste", "Medium"),
    ("Public dustbin missing", "The public dustbin near the market has gone missing. People are littering on the ground.", "Sanitation & Waste", "Medium"),
    ("Street not swept for a week", "The main street in Block C has not been swept for over a week. Leaves and plastic are accumulated.", "Sanitation & Waste", "Medium"),
    # Sanitation & Waste — Low
    ("Littering in park", "People are throwing garbage inside the park despite dustbins being available.", "Sanitation & Waste", "Low"),
    ("Bin needs cleaning", "The public bin near the bus stop needs cleaning and sanitation spray.", "Sanitation & Waste", "Low"),

    # Water Supply — High
    ("No water supply for 2 days", "Our entire colony has had no water supply for the past 2 days. We are unable to drink, cook, or bathe.", "Water Supply", "High"),
    ("Water pipe burst on road", "A major water pipe has burst on the main road. Water is flooding the street and causing traffic disruption.", "Water Supply", "High"),
    ("Contaminated water from tap", "Brown and foul-smelling water is coming from the tap. We suspect contamination. People are falling sick.", "Water Supply", "High"),
    ("Water tanker not supplied", "Despite paying for water tanker service, no tanker has been sent for 3 days in the summer heat.", "Water Supply", "High"),
    # Water Supply — Medium
    ("Low water pressure", "Water pressure in our area is very low since last week. Tanks are not filling properly.", "Water Supply", "Medium"),
    ("Leaking water meter", "The water meter outside our house is leaking and wasting water continuously.", "Water Supply", "Medium"),
    ("Irregular water timing", "Water supply timings have changed without notice. We miss the supply as it comes at odd hours.", "Water Supply", "Medium"),
    # Water Supply — Low
    ("Water supply slightly late", "The water supply is coming 30 minutes later than the scheduled time.", "Water Supply", "Low"),
    ("Minor pipe drip", "A small drip from the public tap near the park. Not urgent but needs fixing.", "Water Supply", "Low"),

    # Electricity & Power — High
    ("Power outage entire street", "The entire street has been without electricity for over 12 hours. Hospitals and homes with sick patients are badly affected.", "Electricity & Power", "High"),
    ("Electric wire fallen on road", "A live electric wire has fallen on the main road. It is a life-threatening danger to passersby.", "Electricity & Power", "High"),
    ("Transformer on fire", "The electricity transformer near Block A is sparking and smoking. It may catch fire.", "Electricity & Power", "High"),
    ("Exposed live wire near playground", "A live electric wire is exposed near the children's playground. Immediate danger to children.", "Electricity & Power", "High"),
    # Electricity & Power — Medium
    ("Streetlight not working", "Two streetlights on the main road have not been working for a week. The area is dark at night.", "Electricity & Power", "Medium"),
    ("Frequent power cuts", "Our area is facing frequent 2-3 hour power cuts daily without any schedule or announcement.", "Electricity & Power", "Medium"),
    ("Electricity pole leaning", "An electricity pole in front of our house is leaning dangerously after the storm.", "Electricity & Power", "Medium"),
    # Electricity & Power — Low
    ("Streetlight flickering", "A streetlight on Lane 5 is flickering intermittently at night.", "Electricity & Power", "Low"),
    ("Meter reading not taken", "The electricity meter reading has not been taken this month.", "Electricity & Power", "Low"),

    # Public Safety — High
    ("Armed robbery near market", "An armed robbery happened near the local market last night. The area feels unsafe and police presence is needed urgently.", "Public Safety", "High"),
    ("Street harassment at night", "Women are being harassed on the street near the bus stop at night. Immediate police patrol is needed.", "Public Safety", "High"),
    ("Dangerous stray dogs attacking", "A pack of aggressive stray dogs is attacking residents near the park. Several children have been bitten.", "Public Safety", "High"),
    ("Illegal drug activity", "Suspicious drug activity is happening behind the school building. Children's safety is at serious risk.", "Public Safety", "High"),
    # Public Safety — Medium
    ("Suspicious individual loitering", "An unknown person has been loitering near the school gate for several days.", "Public Safety", "Medium"),
    ("Broken boundary wall", "The boundary wall of the public park is broken in two places. It is a safety concern at night.", "Public Safety", "Medium"),
    ("Street light needed for safety", "Dark alley near the railway station is unsafe at night. A street light is required.", "Public Safety", "Medium"),
    # Public Safety — Low
    ("Noise complaint from neighbor", "The neighbor is playing loud music late at night disturbing residents.", "Public Safety", "Low"),
    ("Illegal parking blocking gate", "Cars are being illegally parked blocking the society entrance gate.", "Public Safety", "Low"),

    # Parks & Recreation — High
    ("Playground equipment broken injuring child", "A swing in the children's playground broke and injured a child today. The equipment is old and dangerous.", "Parks & Recreation", "High"),
    ("Pond in park is a drowning risk", "The pond in Central Park has no fencing and a child nearly drowned last week.", "Parks & Recreation", "High"),
    # Parks & Recreation — Medium
    ("Park benches broken", "Several benches in the city park are broken and need replacement.", "Parks & Recreation", "Medium"),
    ("Park lights not working", "The lights in the public park are not working. People cannot walk safely in the evening.", "Parks & Recreation", "Medium"),
    ("Garden overgrown with weeds", "The municipal garden has not been maintained for months. Weeds are everywhere.", "Parks & Recreation", "Medium"),
    ("Jogging track needs repair", "The jogging track in the park has multiple cracks and is unsafe for runners.", "Parks & Recreation", "Medium"),
    # Parks & Recreation — Low
    ("Park dustbin full", "The dustbin inside the park needs emptying.", "Parks & Recreation", "Low"),
    ("Grass not mowed", "The lawn in the recreational area has not been mowed this month.", "Parks & Recreation", "Low"),

    # Other — Mixed priorities
    ("Construction noise at night", "Illegal construction work is happening late at night causing extreme noise disturbance.", "Other", "Medium"),
    ("Stray animals in market", "Many stray animals are crowding the local vegetable market. Shoppers are scared.", "Other", "Medium"),
    ("Tree fallen on footpath", "A large tree has fallen on the footpath blocking pedestrian movement.", "Other", "High"),
    ("Unauthorized banner blocking view", "A large unauthorized political banner is blocking the view at a road junction.", "Other", "Low"),
    ("Public toilet not maintained", "The public toilet near the bus stand is extremely dirty and not maintained.", "Other", "Medium"),
    ("Building crack after earthquake", "A crack has appeared in the community hall wall after the minor tremor. Safety inspection required.", "Other", "High"),
]


# ---------------------------------------------------------------------------
# Model training (runs once at import time)
# ---------------------------------------------------------------------------

def _build_corpus(data):
    """Combine title and description into a single text string for vectorisation."""
    return [f"{title} {description}" for title, description, *_ in data]


def _train():
    """Train category and priority classifiers. Returns (cat_pipeline, pri_pipeline)."""
    texts = _build_corpus(_TRAINING_DATA)
    cat_labels = [row[2] for row in _TRAINING_DATA]
    pri_labels  = [row[3] for row in _TRAINING_DATA]

    cat_pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words='english')),
        ('clf',   MultinomialNB(alpha=0.5)),
    ])
    cat_pipeline.fit(texts, cat_labels)

    pri_pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words='english')),
        ('clf',   MultinomialNB(alpha=0.3)),
    ])
    pri_pipeline.fit(texts, pri_labels)

    return cat_pipeline, pri_pipeline


# Module-level cached models — trained once on first import
try:
    _cat_model, _pri_model = _train()
    _MODEL_READY = True
    print("[CCMS Classifier] AI complaint classifier trained successfully.")
except Exception as _e:
    _cat_model = _pri_model = None
    _MODEL_READY = False
    print(f"[CCMS Classifier] WARNING: Model training failed — {_e}. Predictions will be unavailable.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict(title: str, description: str):
    """
    Predict the category and priority of a complaint.

    Args:
        title       (str): Complaint title entered by the citizen.
        description (str): Complaint description entered by the citizen.

    Returns:
        tuple(str, str): (ai_category, ai_priority)
                         Returns (None, None) if the model is unavailable.
    """
    if not _MODEL_READY:
        return None, None

    # Sanitise input
    text = re.sub(r'\s+', ' ', f"{title.strip()} {description.strip()}")

    try:
        ai_category = _cat_model.predict([text])[0]
        ai_priority  = _pri_model.predict([text])[0]
        return ai_category, ai_priority
    except Exception as e:
        print(f"[CCMS Classifier] Prediction error: {e}")
        return None, None
