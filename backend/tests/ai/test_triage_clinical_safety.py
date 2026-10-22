from __future__ import annotations

import pytest
from app.services.triage_service import evaluate_triage


def test_cardiac_emergency_zero_miss():
    """Verify cardiac symptoms trigger emergency triage deterministically across English, Hindi, and Hinglish."""
    cardiac_cases = [
        "Crushing chest pain radiating to left arm with shortness of breath",
        "Severe pressure in chest like an elephant sitting on my sternum",
        "Mujhe seene me bahut tez dard ho raha hai aur pasina aa raha hai",
        "Chhati mein dard ho raha hai aur ghabrahat ho rahi hai",
        "सीने में बहुत तेज़ दर्द है और साँस लेने में दिक्कत है",
    ]
    for text in cardiac_cases:
        res = evaluate_triage(text)
        assert res.urgency == "emergency", f"Failed to flag emergency for: {text}"
        assert res.urgency_level == "emergency"
        assert "112" in res.emergency_numbers
        assert "108" in res.emergency_numbers
        assert res.emergency_warning is not None


def test_stroke_fast_red_flag_detection():
    """Verify stroke FAST symptoms (face drooping, slurred speech, arm weakness) trigger emergency."""
    stroke_cases = [
        "My mother's face is drooping on one side and she has slurred speech",
        "Sudden weakness in one arm and cannot smile",
        "Chehra tedha ho gaya hai aur bolne mein dikkat ho rahi hai",
        "चेहरा टेढ़ा हो गया है और बोलने में दिक्कत आ रही है",
    ]
    for text in stroke_cases:
        res = evaluate_triage(text)
        assert res.urgency == "emergency", f"Failed to flag stroke emergency for: {text}"
        assert "stroke" in res.flags


def test_respiratory_crisis_detection():
    """Verify acute respiratory distress is prioritized with 112/108 routing."""
    respiratory_cases = [
        "Gasping for air, severe difficulty breathing, lips turning slightly blue",
        "Saans lene me bahut takleef ho rahi hai",
        "सांस नहीं आ रही है, बहुत घबराहट हो रही है",
    ]
    for text in respiratory_cases:
        res = evaluate_triage(text)
        assert res.urgency == "emergency", f"Failed respiratory emergency: {text}"
        assert "breathing" in res.flags
        assert "108" in res.emergency_numbers


def test_psychiatric_crisis_and_tele_manas_routing():
    """Verify self-harm and acute mental distress route to India's Tele-MANAS 14416 helpline."""
    mental_health_cases = [
        "I feel like ending my life, I want to die",
        "Mujhe jeene ka mann nahi kar raha, khudkushi ke khayal aa rahe hain",
        "खुदकुशी करने का मन कर रहा है, सब खत्म करना चाहता हूँ",
        "Marna chahta hu, I can't take this pain anymore",
    ]
    for text in mental_health_cases:
        res = evaluate_triage(text)
        assert res.urgency == "emergency", f"Failed mental health crisis: {text}"
        assert res.category == "mental_health"
        assert "Tele-MANAS 14416" in res.emergency_numbers
        assert "112" in res.emergency_numbers


def test_pediatric_and_maternal_emergencies():
    """Verify pediatric and obstetric emergencies are caught promptly."""
    # Infant critical
    res_infant = evaluate_triage("Newborn baby has high fever and is not waking up with blue lips")
    assert res_infant.urgency == "emergency"
    assert "infant_critical" in res_infant.flags

    # Maternal emergency
    res_maternal = evaluate_triage("I am 7 months pregnant and having severe bleeding with abdominal pain")
    assert res_maternal.urgency == "emergency"
    assert "pregnancy_emergency" in res_maternal.flags


def test_vague_insufficient_information_handling():
    """Verify brief uninformative inputs produce insufficient_information triage rather than guessing."""
    vague_inputs = ["pain", "help", "sick", "dard", "not well"]
    for text in vague_inputs:
        res = evaluate_triage(text)
        assert res.urgency == "insufficient_information"
        assert len(res.follow_up_questions) > 0
        assert res.uncertainty_note is not None


def test_routine_symptoms_and_specialty_inference():
    """Verify common self-limiting symptoms result in routine care with appropriate specialty hint."""
    # Routine dermatology
    res_skin = evaluate_triage("I have a mild itchy skin rash on my forearm since yesterday")
    assert res_skin.urgency == "routine"
    assert res_skin.specialty_hint == "Dermatology"
    assert len(res_skin.recommended_next_steps) > 0

    # Routine ENT
    res_ent = evaluate_triage("Mild sore throat and runny nose without fever")
    assert res_ent.urgency == "routine"
    assert res_ent.specialty_hint in {"ENT", "Pulmonology", "General Medicine"}

    # Routine general medicine
    res_gen = evaluate_triage("Feeling tired and mild fatigue after studying late")
    assert res_gen.urgency == "routine"
    assert res_gen.emergency_warning is None
