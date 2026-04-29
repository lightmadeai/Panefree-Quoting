# 🏗️ SaaS Blueprint: Window Sovereign Credit System
**Model**: Plan Beta (Pay-Per-Quote)
**Status**: Draft Specification

## 🎯 Objective
Transition the Window Cleaning Sovereign Engine from a local tool to a monetized SaaS by implementing a credit-based payment system.

## ⚙️ Logic Flow
1. **User Authentication**: User logs in via a simple account system (email/password).
2. **Credit Balance**: Each user has a `credit_balance` in the database.
3. **The Transaction**:
    - User configures a quote in the UI.
    - User clicks "Generate PDF."
    - **System Check**: `if user.credit_balance >= 1`:
        - Deduct 1 credit from `user.credit_balance`.
        - Trigger `generator.py` to produce the PDF.
        - Deliver PDF.
    - **Else**:
        - Redirect user to "Top-Up" page.
        - Prompt for credit purchase.

## 🗄️ Database Schema (Conceptual)
**Table: `users`**
- `user_id` (PK, UUID)
- `email` (Unique)
- `password_hash`
- `credit_balance` (Integer)
- `created_at` (Timestamp)

**Table: `transactions`**
- `tx_id` (PK, UUID)
- `user_id` (FK)
- `amount_paid` (Decimal)
- `credits_added` (Integer)
- `timestamp` (Timestamp)
- `stripe_tx_id` (String)

## 🔌 API Implementation Plan
- **`GET /api/credits`**: Returns the current balance of the authenticated user.
- **`POST /api/generate-quote`**:
    - Validates session.
    - Checks credit balance.
    - Atomic operation: `UPDATE users SET credit_balance = credit_balance - 1 WHERE user_id = ? AND credit_balance > 0`.
    - If successful, calls `generator.py`.
- **`POST /api/purchase-credits`**:
    - Integrates with Stripe Checkout.
    - Upon successful webhook, updates `users.credit_balance`.

## 🛠️ Integration with `engine.py` & `app.py`
- **`app.py`**: Add a middleware layer to check for authentication before allowing access to the quoting engine.
- **`engine.py`**: Remains a "Pure Engine." It doesn't care about credits; it just calculates. The credit check happens in the `app.py` (the View/Controller layer) *before* the engine's results are passed to the generator.
- **`generator.py`**: Now gated by the credit check.

---
**Sovereign Note**: This ensures that "The Engine" remains pure logic, while the "SaaS Wrapper" handles the money.
