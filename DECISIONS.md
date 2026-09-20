# Architecture & Domain Decisions Document

This document records key domain architecture choices made during the development of **Inspector_Website_004**.

---

## 1. Reference vs. Visit (Historical Truth Protection)

- **Reference**: A standalone, reusable library template or hierarchy representing evaluation items (`BRANCH`, `SPECIFICATION`, `CHECKLIST_ITEM`). References can be modified or deleted without affecting past or active inspection visits.
- **Visit**: A discrete, point-in-time inspection event tied to an institution and an inspector. Upon visit creation, a deep snapshot of the chosen source reference is generated and saved as a JSON document (`frozen_snapshot`).
- **Data Model Guarantee**: All `VisitItem` entries are spawned directly from the `frozen_snapshot`. Future edits to the reference or even complete deletion of the reference leave the visit's snapshot and local structure completely untouched.

---

## 2. Selective Scope (Selected vs. Context)

- Visits do not force every item from a reference onto the inspector.
- Inspectors toggle items into their active evaluation scope (`is_selected = True`).
- When a deeply nested checklist item is selected, its parent hierarchy (`BRANCH` or `SPECIFICATION`) is retained in the evaluation tree as a **`CONTEXT`** node.
- **Progress Calculation**: `CONTEXT` nodes and excluded items are strictly ignored when calculating completed items percentage. Only active checklist items explicitly in `is_selected = True` contribute to progress.

---

## 3. Soft Exclusion vs. Restoration

- Excluding an item sets `is_excluded = True` rather than performing a database deletion.
- Any recorded values (`result`, `value_text`, `observation`) remain preserved in the database.
- If the inspector restores an excluded item, all previous values and notes reappear intact.

---

## 4. Origin Classification

Items in a visit's scope carry an `origin` attribute:
- `LEGACY`: Historical nodes from migrated data.
- `MANUAL`: Added manually by inspector during visit setup.
- `GUIDE`: Added via optional guide suggestion.
- `ASSIGNMENT`: Mandatory item enforced by official assignment.
- `LOCAL`: Local visit content authored during draft stage.

Applying a guide or issuing an assignment preserves the item's original `origin` baseline while adding official obligation layers.

---

## 5. Guides vs. Assignments

- **Guide**: Optional, reusable suggestion created by Admin for shared references. Applying a guide selects corresponding items in the draft visit if they exist in the snapshot. It is non-binding, does not lock scope, and does not block visit completion. Guide application is **idempotent** and skips mismatched/outdated entries gracefully.
- **Assignment**: Formal, binding administrative order issued to a specific draft visit. It supports two independent constraints per item:
  - `scope_locked`: Prevents the inspector from soft-excluding the item.
  - `completion_required`: Prevents visit completion until the item has a valid recorded response.
- **Atomic Issuance**: Assignment issuance validates all target items against the visit snapshot. If any target item is missing, the entire issue fails (all-or-nothing).
- **Revocation**: Admins can revoke an issued assignment on draft visits, requiring a mandatory audit reason (`revocation_reason`). Revocation releases assignment obligations while maintaining audit history.

---

## 6. Baseline vs. Effective Constraints

When evaluating whether an item is locked or required for completion, the system aggregates all active (`ISSUED`) assignments for that visit item. If Assignment A locks scope and Assignment B requires completion, revoking Assignment A removes the scope lock while keeping Assignment B's completion constraint active.

---

## 7. Draft vs. Completed Visits

- **DRAFT**: Active editable state. Inspector can select scope, record responses, add local items, apply guides, and receive assignments. Draft visits can be deleted by their owning inspector or Admin.
- **COMPLETED**: Immutable historical record. Once completed:
  - No item results, text, or scope can be modified.
  - No new assignments can be issued or revoked.
  - Draft deletion is strictly forbidden.

---

## 8. Export Schema

Visits are exported as versioned (`schema_version: "1.0"`), deterministic JSON objects containing visit metadata, complete item hierarchy with active constraints, progress statistics, and full assignment audit history (including revocation logs).
