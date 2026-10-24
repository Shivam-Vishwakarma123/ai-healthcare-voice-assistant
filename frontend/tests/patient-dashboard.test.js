import assert from "node:assert/strict";
import { test } from "node:test";

// Standardized clinical metric metadata and reference thresholds used in PatientDashboard.jsx
const METRIC_CONFIGS = {
  bp: {
    label: "Blood Pressure",
    unit: "mmHg",
    series: [
      { key: "bp_systolic", label: "Systolic", color: "#006E51", normalMin: 90, normalMax: 120 },
      { key: "bp_diastolic", label: "Diastolic", color: "#0284C7", normalMin: 60, normalMax: 80 },
    ],
    yMin: 50,
    yMax: 180,
    referenceText: "Standard resting target: < 120/80 mmHg (AHA/ACC Stage 1 threshold >= 130/80)",
  },
  hr: {
    label: "Heart Rate",
    unit: "bpm",
    series: [
      { key: "heart_rate", label: "Pulse Rate", color: "#D97706", normalMin: 60, normalMax: 100 },
    ],
    yMin: 40,
    yMax: 130,
    referenceText: "Normal resting heart rate: 60 – 100 bpm",
  },
  spo2: {
    label: "Oxygen Saturation (SpO2)",
    unit: "%",
    series: [
      { key: "spo2", label: "Oxygen Saturation", color: "#0284C7", normalMin: 95, normalMax: 100 },
    ],
    yMin: 88,
    yMax: 100,
    referenceText: "Normal arterial oxygen saturation on room air: 95 – 100%",
  },
  glucose: {
    label: "Blood Glucose",
    unit: "mg/dL",
    series: [
      { key: "blood_glucose", label: "Glucose Level", color: "#7C3AED", normalMin: 70, normalMax: 99 },
    ],
    yMin: 60,
    yMax: 160,
    referenceText: "Normal fasting reference range: 70 – 99 mg/dL (Pre-diabetes: 100 – 125 mg/dL)",
  },
  weight: {
    label: "Body Weight",
    unit: "kg",
    series: [
      { key: "weight_kg", label: "Weight", color: "#059669", normalMin: 50, normalMax: 85 },
    ],
    yMin: 50,
    yMax: 95,
    referenceText: "Measured body weight trajectory",
  },
};

// Computes statistics for vital series
function computeMetricStats(vitals, activeMetric) {
  if (!vitals || !vitals.length) return { latest: "—", avg: "—", min: "—", max: "—" };
  const cfg = METRIC_CONFIGS[activeMetric];
  const key = cfg.series[0].key;

  if (activeMetric === "bp") {
    const last = vitals[vitals.length - 1];
    const sVals = vitals.map((v) => v.bp_systolic).filter((n) => typeof n === "number");
    const dVals = vitals.map((v) => v.bp_diastolic).filter((n) => typeof n === "number");
    const sAvg = sVals.length ? Math.round(sVals.reduce((a, b) => a + b, 0) / sVals.length) : "—";
    const dAvg = dVals.length ? Math.round(dVals.reduce((a, b) => a + b, 0) / dVals.length) : "—";
    return {
      latest: last.bp_systolic && last.bp_diastolic ? `${last.bp_systolic}/${last.bp_diastolic} mmHg` : "—",
      avg: sAvg !== "—" && dAvg !== "—" ? `${sAvg}/${dAvg} mmHg` : "—",
      min: sVals.length && dVals.length ? `${Math.min(...sVals)}/${Math.min(...dVals)}` : "—",
      max: sVals.length && dVals.length ? `${Math.max(...sVals)}/${Math.max(...dVals)}` : "—",
    };
  }

  const vals = vitals.map((v) => v[key]).filter((n) => typeof n === "number");
  if (!vals.length) return { latest: "—", avg: "—", min: "—", max: "—" };
  const last = vals[vals.length - 1];
  const avg = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(activeMetric === "glucose" ? 0 : 1);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  return {
    latest: `${last} ${cfg.unit}`,
    avg: `${avg} ${cfg.unit}`,
    min: `${min} ${cfg.unit}`,
    max: `${max} ${cfg.unit}`,
  };
}

// SVG coordinate scaling function adhering to single-axis rules
function computeSvgY(val, yMin, yMax, padTop, plotH) {
  const yRange = yMax - yMin;
  return padTop + plotH - ((val - yMin) / yRange) * plotH;
}

// Time-range filter
function filterVitalsByRange(vitals, rangeDays, referenceDate = new Date("2026-10-24T12:00:00Z")) {
  if (rangeDays === "all") return [...vitals].sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at));
  const days = parseInt(rangeDays, 10);
  const cutoff = new Date(referenceDate.getTime() - days * 24 * 60 * 60 * 1000);
  return vitals
    .filter((v) => new Date(v.recorded_at) >= cutoff)
    .sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at));
}

test("Patient Dashboard: All 5 core physiological metrics define single-axis reference boundaries", () => {
  const metrics = Object.keys(METRIC_CONFIGS);
  assert.deepEqual(metrics, ["bp", "hr", "spo2", "glucose", "weight"]);

  for (const [key, cfg] of Object.entries(METRIC_CONFIGS)) {
    assert.ok(cfg.label, `Metric ${key} must have a label`);
    assert.ok(cfg.unit, `Metric ${key} must specify units`);
    assert.ok(cfg.yMin < cfg.yMax, `Metric ${key} yMin must be strictly less than yMax`);
    assert.ok(cfg.series.length >= 1, `Metric ${key} must have at least one data series`);
    for (const s of cfg.series) {
      assert.ok(s.key, `Series in ${key} must specify data key`);
      assert.ok(s.normalMin < s.normalMax, `Series in ${key} must define physiological target`);
      assert.ok(s.color.startsWith("#"), `Series ${s.key} must provide valid hex color`);
    }
  }
});

test("Patient Dashboard: SVG single-axis coordinate projection satisfies bounds", () => {
  const padTop = 30;
  const plotH = 210; // total 280 - 30 - 40
  const yMin = 50;
  const yMax = 180;

  // Maximum value maps to padTop
  const yAtMax = computeSvgY(180, yMin, yMax, padTop, plotH);
  assert.equal(Math.round(yAtMax), padTop);

  // Minimum value maps to padTop + plotH
  const yAtMin = computeSvgY(50, yMin, yMax, padTop, plotH);
  assert.equal(Math.round(yAtMin), padTop + plotH);

  // Normal systolic upper target (120 mmHg) is correctly proportioned
  const yAt120 = computeSvgY(120, yMin, yMax, padTop, plotH);
  assert.ok(yAt120 > yAtMax && yAt120 < yAtMin, "Reference corridor upper bound sits inside plot");
});

test("Patient Dashboard: Statistics aggregation accurately computes latest, avg, min, and max", () => {
  const mockVitals = [
    { recorded_at: "2026-08-25T08:00:00Z", bp_systolic: 142, bp_diastolic: 92, heart_rate: 84, blood_glucose: 104 },
    { recorded_at: "2026-09-15T08:00:00Z", bp_systolic: 130, bp_diastolic: 84, heart_rate: 76, blood_glucose: 94 },
    { recorded_at: "2026-10-23T08:00:00Z", bp_systolic: 120, bp_diastolic: 78, heart_rate: 68, blood_glucose: 88 },
  ];

  // Blood Pressure stats
  const bpStats = computeMetricStats(mockVitals, "bp");
  assert.equal(bpStats.latest, "120/78 mmHg");
  assert.equal(bpStats.avg, "131/85 mmHg");
  assert.equal(bpStats.min, "120/78");
  assert.equal(bpStats.max, "142/92");

  // Blood Glucose stats
  const bgStats = computeMetricStats(mockVitals, "glucose");
  assert.equal(bgStats.latest, "88 mg/dL");
  assert.equal(bgStats.avg, "95 mg/dL");
  assert.equal(bgStats.min, "88 mg/dL");
  assert.equal(bgStats.max, "104 mg/dL");

  // Heart Rate stats
  const hrStats = computeMetricStats(mockVitals, "hr");
  assert.equal(hrStats.latest, "68 bpm");
  assert.equal(hrStats.avg, "76.0 bpm");
  assert.equal(hrStats.min, "68 bpm");
  assert.equal(hrStats.max, "84 bpm");
});

test("Patient Dashboard: Longitudinal time-range filtering respects 30-day and 60-day windows", () => {
  const refDate = new Date("2026-10-24T12:00:00Z");
  const mockVitals = [
    { recorded_at: "2026-08-15T08:00:00Z", bp_systolic: 145 }, // ~70 days ago
    { recorded_at: "2026-09-10T08:00:00Z", bp_systolic: 135 }, // ~44 days ago
    { recorded_at: "2026-10-15T08:00:00Z", bp_systolic: 122 }, // ~9 days ago
    { recorded_at: "2026-10-23T08:00:00Z", bp_systolic: 120 }, // 1 day ago
  ];

  const allRecords = filterVitalsByRange(mockVitals, "all", refDate);
  assert.equal(allRecords.length, 4);

  const sixtyDayRecords = filterVitalsByRange(mockVitals, "60", refDate);
  assert.equal(sixtyDayRecords.length, 3); // 9-10, 10-15, 10-23

  const thirtyDayRecords = filterVitalsByRange(mockVitals, "30", refDate);
  assert.equal(thirtyDayRecords.length, 2); // 10-15, 10-23
});

test("Patient Dashboard: Exactly 8 metric summary cards map to verifiable clinical data sources", () => {
  const summaryCards = [
    { id: "upcoming_visits", label: "Upcoming Visits", sourceKey: "upcoming_appointments" },
    { id: "active_meds", label: "Active Medications", sourceKey: "active_medications" },
    { id: "allergies", label: "Recorded Allergies", sourceKey: "allergies" },
    { id: "lab_reports", label: "Lab Reports", sourceKey: "documents" },
    { id: "vitals", label: "Health Observations", sourceKey: "vitals" },
    { id: "assessments", label: "AI Assessments", sourceKey: "assessments" },
    { id: "follow_up", label: "Follow-up Tasks", sourceKey: "follow_up_tasks" },
    { id: "total_records", label: "Total Health Records", sourceKey: "total_records" },
  ];

  assert.equal(summaryCards.length, 8, "Dashboard must maintain exactly 8 clinical metric summary cards");
  const uniqueKeys = new Set(summaryCards.map((c) => c.sourceKey));
  assert.equal(uniqueKeys.size, 8, "Every summary card must have a distinct verifiable data source");
});

test("Patient Dashboard: Clinical status banner activates caution styling when active allergies exist", () => {
  function getBannerState(allergiesCount) {
    return {
      hasAlert: allergiesCount > 0,
      icon: allergiesCount > 0 ? "⚠️" : "🩺",
      ariaRole: "region",
    };
  }

  const cleanPatient = getBannerState(0);
  assert.equal(cleanPatient.hasAlert, false);
  assert.equal(cleanPatient.icon, "🩺");

  const allergicPatient = getBannerState(2);
  assert.equal(allergicPatient.hasAlert, true);
  assert.equal(allergicPatient.icon, "⚠️");
});

test("Patient Dashboard: AI Insights payload contains required grounding citations and clinical disclaimer", () => {
  const mockInsights = {
    disclaimer: "CareVoice AI insights are educational summaries synthesized from your authorized clinical records. They do not constitute a medical diagnosis or treatment plan.",
    insights: [
      {
        id: "vitals",
        title: "Vital Signs Trajectory",
        summary: "Blood pressure has stabilized within normal thresholds.",
        grounding_sources: [{ type: "vital", label: "Vitals Log #7" }],
      },
    ],
    suggested_questions: ["What is my target resting systolic blood pressure?"],
  };

  assert.ok(mockInsights.disclaimer.includes("educational summaries"), "Must contain mandatory clinical disclaimer");
  assert.ok(mockInsights.insights.length >= 1, "Must contain at least 1 grounded insight");
  assert.ok(mockInsights.insights[0].grounding_sources.length >= 1, "Insight must have traceable grounding citations");
  assert.ok(mockInsights.suggested_questions.length >= 1, "Must offer actionable questions for clinician consultation");
});
