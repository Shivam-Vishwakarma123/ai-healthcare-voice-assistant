import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import AdminUserRow, {
  requiresPlatformAdminDemotionConfirmation,
} from "../src/components/AdminUserRow.js";

const allRoles = [
  "platform_admin",
  "hospital_admin",
  "hospital_staff",
  "doctor",
  "patient",
];

function renderRow(account, currentUser, draft) {
  return renderToStaticMarkup(createElement(AdminUserRow, {
    account,
    currentUser,
    busy: false,
    draft,
    hospitals: [{ id: 2, name: "Test Hospital" }],
    doctors: [{ id: 4, hospital_id: 2, full_name: "Dr. Test", is_active: true }],
    onDraftChange: () => {},
    onSaveRole: () => {},
    onToggle: () => {},
  }));
}

test("Platform Admin can edit their own row and all five roles are available", () => {
  const account = {
    id: 12,
    full_name: "Platform Operator",
    email: "operator@example.test",
    role: "platform_admin",
    hospital_id: null,
    is_active: true,
  };
  const markup = renderRow(account, { id: 12, role: "platform_admin" });

  assert.match(markup, /Platform Admin/);
  assert.match(markup, /<select/);
  assert.match(markup, /Save role/);
  for (const role of allRoles) assert.match(markup, new RegExp(`value="${role}"`));
  assert.match(markup, /value="platform_admin" selected/);
});

test("Platform Admin role dropdown selects the actual backend role", () => {
  const currentUser = { id: 1, role: "platform_admin" };
  for (const role of allRoles) {
    const account = {
      id: role === "platform_admin" ? 1 : 20,
      full_name: "Managed account",
      email: "managed@example.test",
      role,
      hospital_id: role === "patient" || role === "platform_admin" ? null : 2,
      doctor_id: role === "doctor" ? 4 : null,
      is_active: true,
    };
    const markup = renderRow(account, currentUser);
    assert.match(markup, new RegExp(`value="${role}" selected`));
    assert.match(markup, /Save role/);
  }
});

test("self-demotion requires confirmation, while retaining the Platform Admin role does not", () => {
  const account = { id: 12 };
  const currentUser = { id: 12, role: "platform_admin" };
  assert.equal(
    requiresPlatformAdminDemotionConfirmation(account, currentUser, "hospital_admin"),
    true,
  );
  assert.equal(
    requiresPlatformAdminDemotionConfirmation(account, currentUser, "platform_admin"),
    false,
  );
  assert.equal(
    requiresPlatformAdminDemotionConfirmation({ id: 13 }, currentUser, "patient"),
    false,
  );
});

test("Hospital Admin can only edit doctor and staff accounts within their hospital", () => {
  const currentUser = { id: 1, role: "hospital_admin", hospital_id: 2 };
  const render = (role, id, hospitalId) => renderRow({
    id,
    full_name: "Managed account",
    email: "managed@example.test",
    role,
    hospital_id: hospitalId,
    is_active: true,
  }, currentUser);

  assert.match(render("doctor", 2, 2), /Save role/);
  assert.match(render("hospital_staff", 3, 2), /Save role/);
  assert.doesNotMatch(render("patient", 4, 2), /Save role/);
  assert.doesNotMatch(render("doctor", 5, 3), /Save role/);
});
