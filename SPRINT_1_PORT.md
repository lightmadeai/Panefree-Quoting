# 🛠️ Sprint 1 Implementation Guide: Foundational Auth & Credit System
**Project**: Window Cleaning Sovereign Engine (SaaS Transition)
**Objective**: Implement the basic user account and credit-tracking system.
**Target Model**: Claude 3.5 Sonnet (via manual port)

## 📌 Architectural Constraints
- **Pure View Architecture**: The `engine.py` MUST remain pure. It does not know about users, databases, or credits. It only takes inputs and returns calculations.
- **Controller Logic**: All credit checks and user session management must happen in `app.py`.
- **Database**: SQLite for initial phase.

## 🗄️ 1. Database Schema (SQLite)
Implement the following tables:

**Table: `users`**
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `email`: TEXT UNIQUE NOT NULL
- `password_hash`: TEXT NOT NULL
- `credit_balance`: INTEGER DEFAULT 5 (Start with 5 free quotes as per the 'Sovereign Synthesis' plan)
- `created_at`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

**Table: `transactions`**
- `id`: INTEGER PRIMARY KEY AUTOINCREMENT
- `user_id`: INTEGER (FK -> users.id)
- `amount`: DECIMAL
- `credits_added`: INTEGER
- `timestamp`: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
- `stripe_tx_id`: TEXT

## ⚙️ 2. Implementation Steps

### Step A: User Authentication
- Install `Flask-Login` and `Werkzeug` (for password hashing).
- Create a `User` model and a `user_loader` for Flask-Login.
- Implement `/login` and `/register` routes.
- Add a `@login_required` decorator to all quoting and settings routes.

### Step B: The Credit Gate (The "Paywall")
Modify the quote generation route in `app.py`:
1. **Pre-Check**: Before calling the engine/generator, check `current_user.credit_balance`.
2. **The Block**: If `credit_balance < 1`, redirect to a `/top-up` placeholder page with a message: *"You've run out of credits. Top up to keep your pipeline flowing!"*
3. **The Deduction**: If balance $\ge 1$, proceed to generate the PDF.
4. **The Atomic Update**: Only *after* the PDF is successfully generated, deduct 1 credit:
   `user.credit_balance -= 1` $\rightarrow$ `db.session.commit()`.

### Step C: The 'Value Recovery' Tracker (Early Phase)
To implement the a-ha! moment, add a `total_recovered_value` column to the `users` table.
- When a quote is generated, compare the "Sovereign Price" vs a "Baseline Price" (standard rate).
- Add the difference to the user's `total_recovered_value`.
- Display this on the home page: *"You've recovered $[X] in potential revenue using Sovereign Engine."*

## 🧪 3. Validation Checklist
- [ ] Can a user register and log in?
- [ ] Does the system block PDF generation when credits are 0?
- [ ] Does it correctly deduct exactly 1 credit per successful PDF?
- [ ] Is `engine.py` completely untouched by these changes?
- [ ] Does the "Value Recovered" counter increment correctly?
