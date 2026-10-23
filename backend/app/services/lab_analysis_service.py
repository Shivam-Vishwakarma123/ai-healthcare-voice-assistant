from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical import MedicalDocument

logger = logging.getLogger(__name__)


@dataclass
class LabParamReference:
    name: str
    unit: str
    normal_low: float
    normal_high: float
    critical_low: float | None = None
    critical_high: float | None = None
    patient_explanation: str = ""
    clinical_correlation: str = ""


# Standard clinical laboratory reference ranges and correlation guidelines.
LAB_REFERENCES: dict[str, LabParamReference] = {
    "fasting_glucose": LabParamReference(
        name="Fasting Blood Glucose",
        unit="mg/dL",
        normal_low=70.0,
        normal_high=99.0,
        critical_low=54.0,
        critical_high=200.0,
        patient_explanation="Measures blood sugar level after overnight fasting. Key indicator for diabetes screening.",
        clinical_correlation="Elevated levels correlate with impaired glucose tolerance, insulin resistance, or diabetes mellitus.",
    ),
    "hba1c": LabParamReference(
        name="Glycated Hemoglobin (HbA1c)",
        unit="%",
        normal_low=4.0,
        normal_high=5.6,
        critical_low=None,
        critical_high=9.0,
        patient_explanation="Reflects average blood sugar control over the past 2 to 3 months.",
        clinical_correlation="Values >= 6.5% confirm diabetes mellitus; values > 8.0% indicate sub-optimal glycemic control.",
    ),
    "platelets": LabParamReference(
        name="Platelet Count",
        unit="/mcL",
        normal_low=150000.0,
        normal_high=450000.0,
        critical_low=50000.0,
        critical_high=1000000.0,
        patient_explanation="Blood cells essential for normal blood clotting and stopping bleeding.",
        clinical_correlation="Counts < 100,000/mcL flag thrombocytopenia; in acute febrile patients, raises high suspicion of Dengue or viral marrow suppression.",
    ),
    "hemoglobin": LabParamReference(
        name="Hemoglobin",
        unit="g/dL",
        normal_low=12.0,
        normal_high=17.0,
        critical_low=7.0,
        critical_high=20.0,
        patient_explanation="Iron-containing protein in red blood cells that carries oxygen throughout the body.",
        clinical_correlation="Levels < 12.0 g/dL indicate anemia, contributing to fatigue, pallor, and exertional dyspnea.",
    ),
    "total_cholesterol": LabParamReference(
        name="Total Cholesterol",
        unit="mg/dL",
        normal_low=125.0,
        normal_high=199.0,
        critical_low=None,
        critical_high=280.0,
        patient_explanation="Overall measure of fats and cholesterol in the bloodstream.",
        clinical_correlation="Levels >= 200 mg/dL increase risk of atherosclerotic cardiovascular disease and coronary events.",
    ),
    "creatinine": LabParamReference(
        name="Serum Creatinine",
        unit="mg/dL",
        normal_low=0.6,
        normal_high=1.2,
        critical_low=None,
        critical_high=3.0,
        patient_explanation="Metabolic waste product filtered by healthy kidneys. Indicates kidney filtration efficiency.",
        clinical_correlation="Elevations above 1.2 mg/dL suggest acute kidney injury or chronic renal impairment; adjust drug dosing.",
    ),
    "systolic_bp": LabParamReference(
        name="Systolic Blood Pressure",
        unit="mmHg",
        normal_low=90.0,
        normal_high=120.0,
        critical_low=80.0,
        critical_high=180.0,
        patient_explanation="Pressure exerted against artery walls when the heart beats.",
        clinical_correlation="Consistent readings >= 140 mmHg define Stage 2 hypertension requiring lifestyle and antihypertensive therapy.",
    ),
    "diastolic_bp": LabParamReference(
        name="Diastolic Blood Pressure",
        unit="mmHg",
        normal_low=60.0,
        normal_high=80.0,
        critical_low=50.0,
        critical_high=120.0,
        patient_explanation="Pressure in the arteries when the heart rests between beats.",
        clinical_correlation="Readings >= 90 mmHg confirm diastolic hypertension.",
    ),
    "spo2": LabParamReference(
        name="Oxygen Saturation (SpO2)",
        unit="%",
        normal_low=95.0,
        normal_high=100.0,
        critical_low=90.0,
        critical_high=None,
        patient_explanation="Percentage of oxygen carried in hemoglobin throughout red blood cells.",
        clinical_correlation="Levels < 94% indicate hypoxemia; < 90% constitutes a clinical respiratory emergency.",
    ),
}


# Service performing laboratory parameter evaluation, reference range comparison, and trend analysis.
class LabAnalysisService:
    # Evaluates a single lab test value against standard reference thresholds.
    @staticmethod
    def evaluate_parameter(param_key: str, raw_value: Any) -> dict[str, Any]:
        ref = LAB_REFERENCES.get(param_key.lower().strip())
        try:
            val = float(raw_value)
        except (ValueError, TypeError):
            return {
                "key": param_key,
                "raw_value": str(raw_value),
                "status": "uninterpretable",
                "label": param_key.replace("_", " ").title(),
            }

        if not ref:
            return {
                "key": param_key,
                "value": val,
                "status": "unknown",
                "label": param_key.replace("_", " ").title(),
            }

        status = "normal"
        # Check critical
        if (ref.critical_low is not None and val < ref.critical_low) or (
            ref.critical_high is not None and val > ref.critical_high
        ):
            status = "critical"
        elif val < ref.normal_low or val > ref.normal_high:
            status = "borderline" if status != "critical" else status

        return {
            "key": param_key,
            "label": ref.name,
            "value": val,
            "unit": ref.unit,
            "status": status,
            "reference_range": f"{ref.normal_low} - {ref.normal_high} {ref.unit}",
            "patient_explanation": ref.patient_explanation,
            "clinical_correlation": ref.clinical_correlation,
        }

    # Analyzes longitudinal historical lab results for a patient across all diagnostic records.
    @staticmethod
    def get_patient_lab_trends(db: Session, patient_user_id: int) -> dict[str, Any]:
        """Extracts and organizes longitudinal diagnostic trends across all patient records."""
        docs = db.scalars(
            select(MedicalDocument)
            .where(MedicalDocument.patient_user_id == patient_user_id)
            .order_by(MedicalDocument.created_at.asc())
        ).all()

        parameters_timeline: dict[str, list[dict[str, Any]]] = {}

        for doc in docs:
            data = doc.extracted_data or {}
            if not isinstance(data, dict):
                continue
            doc_date = doc.created_at.isoformat() if doc.created_at else None

            for key, val in data.items():
                clean_key = key.lower().strip()
                if clean_key in LAB_REFERENCES:
                    evaluated = LabAnalysisService.evaluate_parameter(clean_key, val)
                    evaluated["date"] = doc_date
                    evaluated["document_title"] = doc.title
                    evaluated["document_id"] = doc.id
                    parameters_timeline.setdefault(clean_key, []).append(evaluated)

        trends_summary: list[dict[str, Any]] = []
        for param_key, history in parameters_timeline.items():
            ref = LAB_REFERENCES[param_key]
            values = [h["value"] for h in history if "value" in h]

            # Calculate direction if at least 2 readings
            direction = "stable"
            if len(values) >= 2:
                diff = values[-1] - values[0]
                if abs(diff) > (ref.normal_high - ref.normal_low) * 0.05:
                    if param_key in {"fasting_glucose", "hba1c", "total_cholesterol", "creatinine", "systolic_bp"}:
                        direction = "improving" if diff < 0 else "worsening"
                    elif param_key in {"platelets", "hemoglobin", "spo2"}:
                        direction = "improving" if diff > 0 else "worsening"

            latest = history[-1]
            trends_summary.append({
                "parameter_key": param_key,
                "label": ref.name,
                "unit": ref.unit,
                "latest_value": latest.get("value"),
                "latest_status": latest.get("status"),
                "reference_range": f"{ref.normal_low} - {ref.normal_high} {ref.unit}",
                "direction": direction,
                "readings_count": len(history),
                "history": history,
                "clinical_correlation": ref.clinical_correlation,
                "patient_explanation": ref.patient_explanation,
            })

        return {
            "patient_user_id": patient_user_id,
            "evaluated_parameters_count": len(trends_summary),
            "trends": trends_summary,
        }
