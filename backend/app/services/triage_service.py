import re
from dataclasses import dataclass, field
from typing import Iterable


EMERGENCY_CONTACTS = {
    "default": ["112", "108"],
    "mental_health": ["Tele-MANAS 14416", "112"],
}


@dataclass
class TriageResult:
    urgency: str
    category: str
    summary: str
    guidance: str
    emergency_numbers: list[str] = field(default_factory=list)
    safety_block: bool = False
    flags: list[str] = field(default_factory=list)
    is_medical_guidance_only: bool = True
    urgency_level: str = "routine"
    reported_symptoms: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    possible_explanations: list[str] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)
    emergency_warning: str | None = None
    uncertainty_note: str | None = None
    disclaimer: str = (
        "CareVoice provides health education and navigation assistance only. "
        "It does not provide a definitive medical diagnosis or replace consultation with a qualified clinician."
    )
    specialty_hint: str | None = None

    def __post_init__(self):
        if not self.urgency_level:
            self.urgency_level = self.urgency
        if self.urgency == "emergency" and not self.emergency_warning:
            self.emergency_warning = (
                "EMERGENCY WARNING: Potential life-threatening or urgent indicators detected. "
                "Immediate in-person clinical assessment is recommended. Do not delay emergency care."
            )

    def to_reply(self) -> str:
        prefix = "Emergency guidance: " if self.urgency == "emergency" else "Safety guidance: "
        contacts = ", ".join(self.emergency_numbers) if self.emergency_numbers else "contact a local emergency service"
        return (
            f"{prefix}{self.summary} {self.guidance} "
            f"Call {contacts}. This is not a medical diagnosis. Please seek urgent professional advice."
        )


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _self_harm_patterns() -> tuple[str, ...]:
    return (
        "want to die",
        "suicidal",
        "self-harm",
        "hurt myself",
        "end my life",
        "kill myself",
        "suicide",
        "khudkushi",
        "aatmahatya",
        "apni jaan lena",
        "khud ko nuksan",
        "khud ko maar",
        "marna chahta",
        "marna chahti",
        "jeena nahi chahta",
        "jeena nahi chahti",
        "आत्महत्या",
        "खुदकुशी",
        "खुद को नुकसान",
        "मरना चाहता",
        "मरना चाहती",
    )


def _prompt_injection_patterns() -> tuple[str, ...]:
    return (
        "ignore all previous instructions",
        "system prompt",
        "override the rules",
        "developer message",
        "ignore the system",
        "do not follow these instructions",
    )


def _obvious_red_flags(text: str) -> list[str]:
    lower = _normalise_text(text)
    flags: list[str] = []
    if _contains_any(lower, [
        "chest pain", "pressure in chest", "tight chest", "squeezing chest",
        "seene mein dard", "seene me dard", "chhati mein dard", "chhati me dard",
        "सीने में दर्द", "छाती में दर्द",
    ]) or re.search(r"\b(seene|chhati)\b.*?\bdard\b", lower) or re.search(r"(सीने|छाती).*?दर्द", lower):
        flags.append("chest_pain")
    if _contains_any(lower, [
        "breathlessness", "shortness of breath", "trouble breathing", "difficulty breathing",
        "can't breathe", "cant breathe", "gasping", "saans nahi aa rahi", "saans nahin aa rahi",
        "saans lene mein dikkat", "saans lene me dikkat", "saans lene mein takleef",
        "saans lene me takleef", "सांस नहीं आ रही", "साँस नहीं आ रही",
        "सांस लेने में दिक्कत", "साँस लेने में दिक्कत",
    ]) or re.search(r"\bsaans\b.*?\b(takleef|dikkat|ruk|kam|nahi|nahin)\b", lower) or re.search(r"(सांस|साँस).*?(तकलीफ|दिक्कत|रुक|नहीं)", lower):
        flags.append("breathing")
    if _contains_any(lower, [
        "face drooping", "one side of face", "slurred speech", "weak arm",
        "can't smile", "cannot smile", "stroke", "chehra tedha", "bolne mein dikkat",
        "एक तरफ चेहरा", "चेहरा टेढ़ा", "बोलने में दिक्कत",
    ]):
        flags.append("stroke")
    if _contains_any(lower, [
        "severe bleeding", "bleeding heavily", "lots of blood", "blood loss",
        "bleeding won't stop", "bleeding is heavy", "bahut khoon beh",
        "khoon ruk nahi raha", "बहुत खून बह", "खून रुक नहीं रहा",
    ]):
        flags.append("severe_bleeding")
    if _contains_any(lower, ["seizure", "fit", "convulsion", "uncontrolled shaking", "daura pad", "दौरा पड़"]):
        flags.append("seizure")
    if _contains_any(lower, [
        "passed out", "unconscious", "loss of consciousness", "fainted", "not waking up",
        "behosh", "hosh mein nahi", "बेहोश", "होश में नहीं",
    ]):
        flags.append("loss_of_consciousness")
    if _contains_any(lower, [
        "swollen lips", "swelling of lips", "tongue swelling", "face swelling",
        "anaphylaxis", "allergic reaction", "hives", "jeebh sooj", "honth sooj",
        "जीभ सूज", "होंठ सूज",
    ]):
        flags.append("anaphylaxis")
    if _contains_any(lower, ["poison", "overdose", "ingested chemicals", "toxic substance", "drunk cleaning fluid", "chemical exposure"]):
        flags.append("poisoning")
    if _contains_any(lower, ["head injury", "hit my head", "fall and hit head", "concussion", "severe head trauma"]):
        flags.append("head_injury")
    if _contains_any(lower, ["pregnant", "pregnancy"]) and _contains_any(lower, ["severe bleeding", "bleeding", "abdominal pain", "pain in stomach", "heavy bleeding"]):
        flags.append("pregnancy_emergency")
    if _contains_any(lower, ["baby", "infant", "newborn", "child"]) and _contains_any(lower, ["fever", "lethargic", "not waking", "difficult to wake", "blue lips"]):
        flags.append("infant_critical")
    if _contains_any(lower, _self_harm_patterns()):
        flags.append("self_harm")
    if _contains_any(lower, _prompt_injection_patterns()):
        flags.append("prompt_injection")
    return flags


SYMPTOM_DICTIONARY = {
    "fever": ["fever", "bukhar", "high temp", "temperature", "chills", "तेज़ बुखार", "बुखार"],
    "cough": ["cough", "khasi", "phlegm", "खांसी"],
    "chest pain": ["chest pain", "seene mein dard", "chhati mein dard", "सीने में दर्द"],
    "shortness of breath": ["shortness of breath", "breathless", "saans lene mein dikkat", "सांस लेने में दिक्कत"],
    "headache": ["headache", "sar dard", "सिर दर्द"],
    "sore throat": ["sore throat", "gale mein kharash", "gale mein dard", "गले में खराश"],
    "vomiting": ["vomiting", "ulti", "throwing up", "उल्टी"],
    "nausea": ["nausea", "nauseous", "ji machlana"],
    "diarrhea": ["diarrhea", "loose motion", "dast", "दस्त"],
    "abdominal pain": ["abdominal pain", "stomach pain", "pet dard", "पेट दर्द"],
    "dizziness": ["dizziness", "dizzy", "lightheaded", "chakkar", "चक्कर"],
    "fatigue": ["fatigue", "tired", "weakness", "kamzori", "थकान"],
    "rash": ["rash", "skin itching", "khujli", "खुजली"],
    "joint pain": ["joint pain", "jodon mein dard", "knee pain", "जोड़ों में दर्द"],
    "back pain": ["back pain", "kamar dard", "कमर दर्द"],
}

SPECIALTY_HINTS = {
    "Cardiology": ["chest pain", "pressure in chest", "palpitations", "heart", "cardiac", "दिल", "सीने में दर्द"],
    "Pulmonology": ["breathless", "breathing", "cough", "wheezing", "asthma", "lungs", "फेफड़े", "सांस"],
    "Neurology": ["stroke", "seizure", "numbness", "paralysis", "headache", "fainting", "neuro", "चक्कर", "दौरा"],
    "Gastroenterology": ["stomach", "vomiting", "diarrhea", "abdominal", "acidity", "liver", "pet dard", "पेट"],
    "Obstetrics & Gynecology": ["pregnant", "pregnancy", "period", "menstrual", "vaginal", "गर्भवती"],
    "Pediatrics": ["baby", "infant", "child", "newborn", "बच्चा"],
    "Dermatology": ["skin", "rash", "itching", "eczema", "acne", "त्वचा"],
    "Orthopedics": ["bone", "joint", "fracture", "sprain", "knee", "spine", "हड्डी"],
    "ENT": ["ear", "throat", "sinus", "nasal", "gale mein", "कान", "नाक", "गला"],
}


def _extract_symptoms(lower: str) -> list[str]:
    extracted: list[str] = []
    for symptom, terms in SYMPTOM_DICTIONARY.items():
        if _contains_any(lower, terms):
            extracted.append(symptom)
    return extracted


def _infer_specialty(lower: str) -> str:
    for specialty, terms in SPECIALTY_HINTS.items():
        if _contains_any(lower, terms):
            return specialty
    return "General Medicine"


def evaluate_triage(text: str, *, age_band: str | None = None, pregnancy: bool = False, chronic_condition: bool = False) -> TriageResult:
    lower = _normalise_text(text)
    flags = _obvious_red_flags(lower)
    reported = _extract_symptoms(lower)
    specialty = _infer_specialty(lower)

    # Check for truly ambiguous or insufficient inputs
    is_vague_input = (
        len(lower.strip()) <= 30
        and not flags
        and lower.strip() in {
            "pain", "sick", "help", "ill", "dard", "bimar", "check", "test",
            "not well", "problem", "unwell", "kuch thik nahi",
            "feeling bad", "not feeling well", "tabiyat kharab",
        }
    )
    if is_vague_input:
        return TriageResult(
            urgency="insufficient_information",
            urgency_level="insufficient_information",
            category="insufficient_information",
            summary="The reported symptom description is too brief to safely evaluate clinical urgency.",
            guidance=(
                "Please describe what you are experiencing in more detail: which part of the body is affected, "
                "how long it has been going on, whether there is fever or severe pain, and if there are any emergency signs."
            ),
            emergency_numbers=["112", "108"],
            flags=flags,
            reported_symptoms=reported,
            specialty_hint="General Medicine",
            follow_up_questions=[
                "Where in your body are you experiencing discomfort or pain?",
                "How long have you had these symptoms (hours, days, or weeks)?",
                "Are you experiencing any red-flag signs such as chest pain, breathing difficulty, or fainting?",
            ],
            possible_explanations=[
                "Symptoms require further detail for non-diagnostic educational assessment."
            ],
            recommended_next_steps=[
                "Provide specific symptom details and duration for tailored educational guidance.",
                "If you feel severely unwell, call 112 or 108 immediately.",
            ],
            uncertainty_note="Symptom location, duration, and severity indicators were not provided.",
        )

    emergency_flags = {
        "chest_pain", "breathing", "stroke", "severe_bleeding", "seizure",
        "loss_of_consciousness", "anaphylaxis", "poisoning", "head_injury",
        "pregnancy_emergency", "infant_critical", "self_harm",
    }
    if "self_harm" in flags:
        return TriageResult(
            urgency="emergency",
            urgency_level="emergency",
            category="mental_health",
            summary="The symptoms suggest immediate risk to the person’s safety or severe mental-health distress.",
            guidance="Call Tele-MANAS 14416 immediately and contact 112 or a trusted emergency contact. Do not leave the person alone if there is immediate danger.",
            emergency_numbers=["Tele-MANAS 14416", "112", "108"],
            flags=flags,
            reported_symptoms=reported or ["mental_health_crisis"],
            specialty_hint="Psychiatry",
            follow_up_questions=[],
            possible_explanations=["Acute psychiatric crisis or acute safety risk requiring immediate intervention."],
            recommended_next_steps=[
                "Call Tele-MANAS (14416) immediately for 24/7 mental health crisis support.",
                "Call 112 or contact trusted emergency family/support services.",
                "Do not stay alone; seek immediate physical presence of a trusted person or emergency responder.",
            ],
            emergency_warning="CRITICAL CRISIS: Immediate support is available via Tele-MANAS 14416 and Emergency 112.",
        )

    if any(flag in flags for flag in emergency_flags):
        return TriageResult(
            urgency="emergency",
            urgency_level="emergency",
            category="emergency",
            summary="The reported symptoms meet emergency red-flag criteria and require immediate medical attention.",
            guidance="Call 112 for emergency assistance and 108 for ambulance support. Go to the nearest emergency-capable hospital or urgent care center without delay.",
            emergency_numbers=["112", "108"],
            flags=flags,
            reported_symptoms=reported or [f"red_flag_{flag}" for flag in flags if flag in emergency_flags],
            specialty_hint=specialty,
            follow_up_questions=[],
            possible_explanations=["Acute emergency medical condition requiring immediate in-person hospital evaluation."],
            recommended_next_steps=[
                "Call 112 (National Emergency Helpline) or 108 (Ambulance) right now.",
                "Proceed immediately to the nearest hospital emergency department.",
                "Do not attempt to drive yourself; ask someone nearby to assist you.",
            ],
            emergency_warning="CRITICAL EMERGENCY: Red-flag symptoms detected. Immediate emergency care is required.",
        )

    if "prompt_injection" in flags:
        return TriageResult(
            urgency="urgent",
            urgency_level="urgent",
            category="safety",
            summary="The message appears to try to override the safety instructions for this assistant.",
            guidance="Share only symptoms and relevant context. I can help with general, non-diagnostic guidance and safe next steps.",
            emergency_numbers=["112"],
            safety_block=True,
            flags=flags,
            reported_symptoms=[],
            specialty_hint="General Medicine",
            follow_up_questions=["Please describe your actual symptoms (e.g. fever, headache, cough)."],
            possible_explanations=[],
            recommended_next_steps=["Re-enter symptom details without instruction-override keywords."],
            uncertainty_note="System security filter was engaged; no clinical guidance was generated.",
        )

    if age_band in {"infant", "child"} or pregnancy or chronic_condition:
        if _contains_any(lower, ["fever", "vomiting", "dizziness", "severe pain", "shortness of breath", "confusion"]):
            return TriageResult(
                urgency="urgent",
                urgency_level="urgent",
                category="special_population",
                summary="The symptoms may need clinician review soon because this person is in a higher-risk group.",
                guidance="Please contact a doctor or nearest urgent care center promptly, and use an emergency service if symptoms worsen.",
                emergency_numbers=["112", "108"],
                flags=flags,
                reported_symptoms=reported or ["higher_risk_symptom"],
                specialty_hint="Pediatrics" if age_band in {"infant", "child"} else "Obstetrics & Gynecology" if pregnancy else specialty,
                follow_up_questions=[
                    "How long have these symptoms been present?",
                    "Is the individual able to drink liquids and stay hydrated?",
                    "Have there been any sudden changes in activity level or alertness?",
                ],
                possible_explanations=[
                    "Symptoms in higher-risk groups (pediatric, pregnancy, chronic illness) warrant timely in-person evaluation."
                ],
                recommended_next_steps=[
                    "Contact a pediatrician or relevant clinician for a prompt consultation today.",
                    "If breathing becomes rapid or difficulty waking occurs, proceed to emergency care immediately.",
                ],
            )

    if _contains_any(lower, ["severe pain", "uncontrolled fever", "vomiting blood", "difficulty walking", "severe dehydration", "dizziness"]) or _contains_any(lower, ["bad pain", "really painful", "cannot walk", "very weak"]):
        return TriageResult(
            urgency="urgent",
            urgency_level="urgent",
            category="urgent",
            summary="The reported symptoms may need same-day clinical review but are not yet showing the strongest emergency signs.",
            guidance="Arrange a same-day assessment with a clinician or urgent care center. If symptoms worsen or new red flags appear, go to emergency care immediately.",
            emergency_numbers=["112", "108"],
            flags=flags,
            reported_symptoms=reported or ["urgent_symptom"],
            specialty_hint=specialty,
            follow_up_questions=[
                "Are your symptoms progressively worsening or stable?",
                "Are you able to keep fluids down without vomiting?",
                "Do you have a personal history of chronic conditions?",
            ],
            possible_explanations=[
                "Acute symptoms requiring same-day clinical examination to prevent progression or dehydration."
            ],
            recommended_next_steps=[
                "Arrange a same-day consultation with a qualified doctor or clinic.",
                "If severe chest pain, breathlessness, or confusion develops, call 112 or 108 immediately.",
            ],
        )

    return TriageResult(
        urgency="routine",
        urgency_level="routine",
        category="advice",
        summary="The symptoms are not clearly matching emergency red flags.",
        guidance="Use home-care measures, hydration, rest, and monitor symptoms; if they persist or worsen, seek medical attention from a doctor or clinic.",
        emergency_numbers=[],
        flags=flags,
        reported_symptoms=reported or ["general_symptom"],
        specialty_hint=specialty,
        follow_up_questions=[
            "How many days have you experienced these symptoms?",
            "Have you noticed any other symptoms such as chills, body aches, or nausea?",
            "Does anything specific relieve or worsen your symptoms?",
        ],
        possible_explanations=[
            "Common self-limiting conditions (such as mild viral upper respiratory or gastrointestinal infections)."
        ],
        recommended_next_steps=[
            "Rest, ensure adequate oral fluid intake, and monitor your symptoms.",
            "Schedule an appointment with a general practitioner if symptoms persist for more than 48-72 hours or worsen.",
        ],
        uncertainty_note="Assessment is preliminary and educational; diagnosis requires in-person medical evaluation.",
    )
