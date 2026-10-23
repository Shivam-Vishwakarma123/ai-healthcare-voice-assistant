import { createElement } from "react";

// Maps raw role identifier slug to localized, human-readable display title.
function roleLabel(role) {
  const labels = {
    platform_admin: "Platform Admin",
    hospital_admin: "Hospital Admin",
    hospital_staff: "Hospital Staff",
    doctor: "Doctor",
    patient: "Patient",
  };
  return labels[role] || role;
}

// Determines if an administrative role change demotes the active user from platform admin privileges.
export function requiresPlatformAdminDemotionConfirmation(account, currentUser, role) {
  return (
    account.id === currentUser?.id &&
    currentUser?.role === "platform_admin" &&
    role !== "platform_admin"
  );
}

// Renders an editable table row for user role management, facility linkage, and activation toggling.
export default function AdminUserRow({
  account,
  currentUser,
  busy,
  draft,
  hospitals,
  doctors,
  onDraftChange,
  onSaveRole,
  onToggle,
}) {
  const isPlatformAdmin = currentUser?.role === "platform_admin";
  const isHospitalAdmin = currentUser?.role === "hospital_admin";
  const isHospitalAccount =
    isHospitalAdmin &&
    account.hospital_id === currentUser.hospital_id &&
    ["doctor", "hospital_staff"].includes(account.role);
  const canEditRole = isPlatformAdmin || isHospitalAccount;
  const selectedRole = draft?.role || account.role;
  const selectedHospital = draft?.hospital_id ?? account.hospital_id ?? "";
  const selectedDoctor = draft?.doctor_id ?? account.doctor_id ?? "";
  const needsHospital = ["hospital_admin", "hospital_staff", "doctor"].includes(selectedRole);
  const availableDoctors = doctors.filter(
    (doctor) =>
      Number(doctor.hospital_id) === Number(selectedHospital) &&
      doctor.is_active,
  );

  return createElement(
    "tr",
    { "data-account-id": account.id },
    createElement(
      "td",
      null,
      account.full_name,
      createElement("small", null, account.email),
    ),
    createElement(
      "td",
      null,
      canEditRole
        ? createElement(
            "select",
            {
              "aria-label": `Role for ${account.full_name}`,
              value: selectedRole,
              disabled: busy,
              onChange: (event) => onDraftChange(account.id, { role: event.target.value }),
            },
            ...(isPlatformAdmin
              ? ["platform_admin", "hospital_admin", "hospital_staff", "doctor", "patient"]
              : ["doctor", "hospital_staff"]
            ).map((role) =>
              createElement("option", { key: role, value: role }, roleLabel(role)),
            ),
          )
        : roleLabel(account.role),
    ),
    createElement(
      "td",
      null,
      canEditRole && needsHospital
        ? isPlatformAdmin
          ? createElement(
              "select",
              {
                "aria-label": `Hospital for ${account.full_name}`,
                value: selectedHospital,
                disabled: busy,
                onChange: (event) =>
                  onDraftChange(account.id, {
                    hospital_id: event.target.value,
                    doctor_id: "",
                  }),
              },
              createElement("option", { value: "" }, "Select hospital"),
              ...hospitals.map((hospital) =>
                createElement(
                  "option",
                  { key: hospital.id, value: hospital.id },
                  `#${hospital.id} · ${hospital.name}`,
                ),
              ),
            )
          : `#${currentUser.hospital_id}`
        : account.hospital_id ?? "—",
      canEditRole && selectedRole === "doctor"
        ? createElement(
            "select",
            {
              "aria-label": `Clinician for ${account.full_name}`,
              value: selectedDoctor,
              disabled: busy,
              onChange: (event) => onDraftChange(account.id, { doctor_id: event.target.value }),
            },
            createElement("option", { value: "" }, "Select clinician"),
            ...availableDoctors.map((doctor) =>
              createElement(
                "option",
                { key: doctor.id, value: doctor.id },
                `#${doctor.id} · ${doctor.full_name}`,
              ),
            ),
          )
        : null,
    ),
    createElement("td", null, account.is_active ? "Active" : "Inactive"),
    createElement(
      "td",
      null,
      canEditRole
        ? createElement(
            "div",
            { className: "cv-admin-row-actions" },
            createElement(
              "button",
              {
                className: "cv-button cv-button-quiet",
                disabled: busy || (selectedRole === "doctor" && !selectedDoctor) || (needsHospital && !selectedHospital),
                onClick: () => onSaveRole(account, { role: selectedRole, hospital_id: selectedHospital, doctor_id: selectedDoctor }),
              },
              "Save role",
            ),
            createElement(
              "button",
              {
                className: "cv-button cv-button-quiet",
                disabled: busy,
                onClick: () => onToggle(account),
              },
              account.is_active ? "Deactivate" : "Reactivate",
            ),
          )
        : "—",
    ),
  );
}
