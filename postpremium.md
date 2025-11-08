# WelthWest Subscription and Profile Page — Technical Implementation Prompt

This document defines **how the Subscription Management System, Profile integration, and daily feature-limit tracking** should be built for the WelthWest platform. The system must be scalable, easy to update, and dynamically configured through the existing `.env` file.  

The `.env` file already exists and is functional, so no environment re-setup is needed. All limits, durations, and keys must be pulled directly from it.  

---

## 1. Project Context

WelthWest already has a working premium system connected with Cashfree payment gateway.  
The next stage is to **extend the system** by creating a full subscription management and usage tracking feature that integrates with both the backend (for logic and limits) and frontend (for user display under the profile page).  

The new system should:
- Automatically detect user plan type (Free or Premium)
- Track daily usage of each paid feature
- Reset usage every 24 hours or on the next login after a date change
- Handle plan activation and expiry automatically
- Store and display payment history
- Show all this data neatly on the profile page

---

## 2. High-Level Objective

Develop a **modular subscription and profile module** that connects with the existing premium logic and Cashfree setup.

This new system must include:
1. A robust **subscription management structure**
2. A clean **usage tracking mechanism** (daily and per-feature)
3. **Automatic expiry and downgrade** on plan end
4. **UI integration** under the user profile page for:
   - Active plan display  
   - Feature usage indicators  
   - Plan validity (start and end dates)  
   - Payment history  
   - Option to upgrade or renew  

No values should be hardcoded. Everything must rely on `.env` variables and database states.

---

## 3. Functional Requirements

### 3.1 Subscription Plans
- Plans can be `FREE`, `PRO_MONTHLY`, and `PRO_YEARLY`.  
- Each plan’s limits, duration, and pricing are defined in `.env`.
- The backend must fetch plan limits dynamically when needed.
- Plan validity is calculated based on plan start date + plan duration.
- On expiry, the plan automatically reverts to `FREE`.

**Example:**  
If a user buys a PRO_MONTHLY plan on Nov 6, 2025, and duration is 30 days, the expiry becomes Dec 6, 2025, 23:59:59.

---

### 3.2 Feature Access Control
Each paid feature (for example):
- **Welth Market Regime**
- **Welth AI Assistant**
- **Backtest Beta**

has a **daily usage limit**.  
The system should:
1. Check the user’s plan.
2. Compare current usage count with the limit.
3. Block further access if limit is exceeded.
4. Reset usage automatically after 24 hours (or after the date changes).
5. Store all counts per user and per feature.

This ensures each user’s feature consumption is independently tracked.

---

### 3.3 Plan Expiry Handling
- Every plan has a `plan_end` timestamp.
- A background check or login-time verification should verify expiry.
- If the current date is past `plan_end`, the plan is immediately downgraded to `FREE`, and usage data is reset.

---

### 3.4 Daily Reset Mechanism
- Instead of using cron jobs, implement a simple date comparison system.
- Each feature usage record contains a `last_reset_date`.
- When the current date != `last_reset_date`, all counts are reset to zero for that user and updated.

This approach ensures the reset works even if the user doesn’t log in daily or if the backend isn’t running a daily cron.

---

### 3.5 Payment and Transaction History
Integrate transaction data with the profile page:
- Display all successful transactions associated with the logged-in user.
- Each record includes:
  - Transaction ID
  - Amount
  - Plan name
  - Duration
  - Date and time
  - Payment status
- For detailed view, the frontend can request a specific transaction, and the backend should fetch additional info from Cashfree if needed (via Cashfree API).

This helps users verify when and how their payments were processed.

---

### 3.6 Profile Page Integration
The **Profile page** should now have:
1. **Active Plan Card:**  
   - Displays plan name, start date, and end date.  
   - Shows whether plan is active or expired.  
   - A “Renew” or “Upgrade” button based on status.

2. **Usage Summary Section:**  
   - Each feature listed with its name, today’s usage count, and total daily limit.  
   - Progress bars or indicators for visual clarity.  
   - If the plan is expired, disable buttons with an “Upgrade to unlock” message.

3. **Payment History Section:**  
   - Scrollable table of all payments.  
   - Option to click and view details in a modal or drawer.

4. **Next Reset Info:**  
   - Small note showing when the next reset will happen (“Your daily usage resets in X hours”).

---

### 3.7 Header Integration
The plan type (e.g., “PRO”) should appear in the user dropdown in the header.
- Example:  
  - “Rudresh (PRO)”  
  - “Rudresh (Free)”  
  - If expired → it should auto-switch to “Free”.

---

### 3.8 API Structure (Conceptual Only)
**No code — just structure for Claude to implement.**

1. `/api/subscription/status`
   - Returns plan type, start/end date, and usage stats per feature.
2. `/api/subscription/usage/update`
   - Called when a feature is used; increments count and enforces limits.
3. `/api/subscription/payment-history`
   - Returns list of all payments made.
4. `/api/subscription/verify-expiry`
   - Runs on login to downgrade expired plans.
5. `/api/subscription/reset`
   - Internal endpoint for resetting daily usage.

---

### 3.9 Environment Variable Usage
Claude must ensure every configurable limit or value is derived from `.env`.

**Example keys (already present or to be added):**
- `FREE_MARKET_REGIME_LIMIT`
- `PRO_MARKET_REGIME_LIMIT`
- `FREE_AI_ASSISTANT_LIMIT`
- `PRO_AI_ASSISTANT_LIMIT`
- `PLAN_PRO_MONTHLY_DURATION`
- `PLAN_PRO_YEARLY_DURATION`
- `PLAN_PRO_MONTHLY_PRICE`
- `PLAN_PRO_YEARLY_PRICE`

No limit or duration value should exist directly in the source code.

---

### 3.10 Logging and Error Handling
All important actions should have logs:
- When a plan is activated
- When usage is incremented
- When a reset happens
- When an expiry triggers downgrade
- When a Cashfree verification occurs

Errors (like invalid plan IDs or expired tokens) should be clearly logged with timestamps and user IDs.

---

## 4. Data Flow Summary

1. **User Logs In** → Backend checks subscription validity via expiry check.  
   - If expired → downgrade to Free.  
   - If valid → load subscription data.

2. **User Uses Feature (e.g., Welth AI Assistant)**  
   - API verifies plan type and usage count.  
   - If within limit → allow.  
   - If exceeded → block and prompt to upgrade.

3. **User Visits Profile Page**  
   - Frontend requests `/subscription/status` → receives plan, expiry, and usage data.  
   - Displays all in structured cards and progress bars.  
   - Also fetches `/payment-history` for transaction list.

4. **Midnight or Next Login**  
   - System detects date change → usage counts reset to zero.

5. **Plan Renewal**  
   - If the user makes a new payment via Cashfree, the plan is updated with a new `start_date` and `end_date`.

---

## 5. UI and UX Guidelines

- The **Profile page** should be clean, minimal, and card-based.
- Use consistent styling from existing WelthWest components.
- Use soft colors (blue, gray, green) to indicate plan type and feature activity.
- Display alerts (green = active, red = expired, yellow = nearing limit).
- Progress bar for usage should animate when updated.
- Payment list must be paginated or lazy-loaded for performance.

---

## 6. Future-Proofing

This design should allow:
- Adding new plans easily (e.g., PRO+, ENTERPRISE)
- Adding new features without changing schema (just add new keys in usage map)
- Integration with other gateways later (Stripe, Razorpay)
- Analytics tracking of user feature engagement via the same usage data

---

## 7. Deliverables (for Claude or any AI Agent)

When this prompt is provided to a coding model (like Claude or another assistant), it should:
1. Implement backend logic for subscription and usage.
2. Connect it with existing user authentication and Cashfree webhook.
3. Create necessary MongoDB schemas or extend current ones.
4. Build frontend sections for:
   - Subscription status display
   - Usage tracking and visual indicators
   - Payment history
5. Ensure all limits, prices, and durations are `.env` driven.
6. Verify expiry and downgrade mechanism is functional and reliable.

---

## 8. Testing Scenarios

- **Scenario 1:** Free user hits daily limit → system blocks further usage.  
- **Scenario 2:** Premium user crosses limit → allowed because higher limit.  
- **Scenario 3:** Plan expires → auto-downgrade and reset.  
- **Scenario 4:** Plan renewed → new start/end date applied correctly.  
- **Scenario 5:** Payment appears in history immediately after successful Cashfree callback.  
- **Scenario 6:** Reset occurs on next login after midnight.  

All these must pass without manual intervention.

---

## 9. Final Note for Claude
Claude must:
- Reuse existing user collection (add `subscription` and `usage` inside it).
- Keep all logic modular and environment-driven.
- Write backend routes in a scalable, well-commented manner.
- Make frontend UI responsive and cohesive with WelthWest design system.
- Ensure the system is ready for immediate deployment without affecting current premium flow.

---

**End of Prompt**