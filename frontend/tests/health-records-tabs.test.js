import assert from "node:assert/strict";
import { test } from "node:test";

// Simulates the TABS metadata configuration used in PatientHealthRecords.jsx
const TABS = [
  { id: "timeline", icon: "🕒", en: "Health Timeline", hi: "स्वास्थ्य समयरेखा" },
  { id: "reports", icon: "📑", en: "AI Reports", hi: "AI रिपोर्ट" },
  { id: "conversations", icon: "💬", en: "AI Conversations", hi: "AI परामर्श संवाद" },
  { id: "prescriptions", icon: "℞", en: "Prescriptions", hi: "पर्चे" },
  { id: "notes", icon: "🩺", en: "Doctor Notes", hi: "विज़िट नोट्स" },
  { id: "documents", icon: "🔬", en: "Lab & Diagnostic Reports", hi: "लैब व नैदानिक रिपोर्ट" },
  { id: "vitals", icon: "💓", en: "Vitals & Protocols", hi: "महत्वपूर्ण संकेत" },
  { id: "allergies", icon: "⚠️", en: "Conditions & Allergies", hi: "एलर्जी और सावधानियां" },
  { id: "billing", icon: "💳", en: "Billing & Receipts", hi: "बिलिंग और रसीदें" },
  { id: "guides", icon: "📖", en: "Care Guides", hi: "केयर गाइड्स" },
  { id: "careteam", icon: "👨‍⚕️", en: "Care Team", hi: "केयर टीम" },
  { id: "privacy", icon: "🔒", en: "DPDP Privacy", hi: "गोपनीयता केंद्र" },
];

// Handles ArrowLeft/Right, Home, and End keyboard navigation across tabs according to WAI-ARIA authoring practices.
function getNextTabIndex(key, currentIndex, totalTabs) {
  if (key === "ArrowRight") return (currentIndex + 1) % totalTabs;
  if (key === "ArrowLeft") return (currentIndex - 1 + totalTabs) % totalTabs;
  if (key === "Home") return 0;
  if (key === "End") return totalTabs - 1;
  return currentIndex;
}

test("Health Records Tabs: Exactly 12 tabs are configured with unique ids and localized labels", () => {
  assert.equal(TABS.length, 12, "Health Records must contain all 12 clinical tabs");

  const ids = TABS.map((t) => t.id);
  const uniqueIds = new Set(ids);
  assert.equal(uniqueIds.size, 12, "All tab IDs must be strictly unique");

  for (const tab of TABS) {
    assert.ok(tab.icon, `Tab '${tab.id}' must have an icon`);
    assert.ok(tab.en, `Tab '${tab.id}' must have an English label`);
    assert.ok(tab.hi, `Tab '${tab.id}' must have a Hindi label`);
  }
});

test("Health Records Tabs: WAI-ARIA keyboard navigation wraps correctly around boundaries", () => {
  const total = TABS.length;

  // ArrowRight wraps from end (11) back to start (0)
  assert.equal(getNextTabIndex("ArrowRight", 0, total), 1);
  assert.equal(getNextTabIndex("ArrowRight", 5, total), 6);
  assert.equal(getNextTabIndex("ArrowRight", 11, total), 0, "ArrowRight on last tab must wrap to first tab");

  // ArrowLeft wraps from start (0) back to end (11)
  assert.equal(getNextTabIndex("ArrowLeft", 1, total), 0);
  assert.equal(getNextTabIndex("ArrowLeft", 0, total), 11, "ArrowLeft on first tab must wrap to last tab");

  // Home and End keys
  assert.equal(getNextTabIndex("Home", 7, total), 0, "Home key must jump to first tab");
  assert.equal(getNextTabIndex("End", 2, total), 11, "End key must jump to last tab");
});

test("Health Records Tabs: Roving tabindex correctly assigns 0 to active tab and -1 to siblings", () => {
  const activeTabId = "documents";

  const tabElements = TABS.map((tab) => ({
    id: tab.id,
    role: "tab",
    "aria-selected": tab.id === activeTabId,
    tabIndex: tab.id === activeTabId ? 0 : -1,
    "aria-controls": `tabpanel-${tab.id}`,
  }));

  const activeElement = tabElements.find((el) => el.id === activeTabId);
  assert.equal(activeElement["aria-selected"], true);
  assert.equal(activeElement.tabIndex, 0);

  const inactiveElements = tabElements.filter((el) => el.id !== activeTabId);
  assert.equal(inactiveElements.length, 11);
  for (const inactive of inactiveElements) {
    assert.equal(inactive["aria-selected"], false);
    assert.equal(inactive.tabIndex, -1, "Inactive tabs must have tabIndex -1 for roving focus");
  }
});

test("Health Records Tabs: Scroll overflow detection math computes edge mask thresholds", () => {
  // Scenario 1: Scrolled to very beginning
  const scrollLeftStart = 0;
  const clientWidth = 600;
  const scrollWidth = 1200;

  const canScrollLeft1 = scrollLeftStart > 4;
  const canScrollRight1 = scrollLeftStart + clientWidth < scrollWidth - 4;
  assert.equal(canScrollLeft1, false, "No left mask when scrolled to the start");
  assert.equal(canScrollRight1, true, "Right mask enabled when content extends right");

  // Scenario 2: Scrolled to middle
  const scrollLeftMiddle = 300;
  const canScrollLeft2 = scrollLeftMiddle > 4;
  const canScrollRight2 = scrollLeftMiddle + clientWidth < scrollWidth - 4;
  assert.equal(canScrollLeft2, true, "Left mask enabled when scrolled past start");
  assert.equal(canScrollRight2, true, "Right mask enabled when content extends right");

  // Scenario 3: Scrolled to end
  const scrollLeftEnd = 600;
  const canScrollLeft3 = scrollLeftEnd > 4;
  const canScrollRight3 = scrollLeftEnd + clientWidth < scrollWidth - 4;
  assert.equal(canScrollLeft3, true, "Left mask enabled when scrolled past start");
  assert.equal(canScrollRight3, false, "No right mask when reached the end");
});
