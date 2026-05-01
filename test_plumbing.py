import json
from engine import calculate_quote
from generator import generate_document

def run_test_suite():
    print("Starting Phase 3: The Plumbing Test Suite...")
    
    # 1. Setup Data
    with open('price_sheet.json', 'r') as f:
        price_sheet = json.load(f)
    
    job_data = {
        "panes": {"floor1": 12, "floor2": 8},
        "add_ons": ["Screen Cleaning", "Track Cleaning"]
    }

    # 2. Brain Calculation
    print("\nCalculating quote...")
    snapshot = calculate_quote(job_data, price_sheet)
    print(f"Grand Total: ${snapshot['calculation']['grand_total']}")

    # 3. Generate Quote PDF
    print("Generating quote.pdf...")
    generate_document(snapshot, doc_type="QUOTE", output_path="quote.pdf")
    print("OK: quote.pdf generated.")

    # 4. Invoice Bridge with Reconciliation
    # Scenario: During the job, the technician found 2 extra panes on floor 2.
    print("\nReconciling pane counts for invoice...")
    reconciled_panes = {"floor1": 12, "floor2": 10} # 8 -> 10
    
    # Re-calculating to ensure math is correct for the invoice
    reconciled_job_data = {
        "panes": reconciled_panes,
        "add_ons": job_data["add_ons"]
    }
    # MANDATORY: Re-run the engine to get a fresh snapshot for the invoice.
    # This ensures no 'Ghost Totals' and a pure view in the generator.
    invoice_snapshot = calculate_quote(reconciled_job_data, price_sheet)
    
    print("Generating invoice.pdf...")
    generate_document(invoice_snapshot, doc_type="INVOICE", output_path="invoice.pdf")
    print("OK: invoice.pdf generated.")

    # Feature 2 smoke: invoice_number kwarg path. We're not asserting PDF
    # content here (consistent with the rest of this suite), just proving
    # the new param flows through generate_document without crashing. The
    # title-format branch lives in generator.py:118-124; visual confirmation
    # comes from inspecting invoice_numbered.pdf — should read "INV-000042".
    print("\nGenerating invoice_numbered.pdf with invoice_number=42...")
    generate_document(invoice_snapshot, doc_type="INVOICE",
                      output_path="invoice_numbered.pdf", invoice_number=42)
    print("OK: invoice_numbered.pdf generated (visual check: INV-000042).")

    # Re-render with the same number to confirm idempotency at the generator
    # level (the *real* idempotency lives in app.py:_claim_invoice_number,
    # but the generator must accept a repeated number cleanly).
    print("Re-generating with the same invoice_number=42...")
    generate_document(invoice_snapshot, doc_type="INVOICE",
                      output_path="invoice_numbered_2.pdf", invoice_number=42)
    print("OK: re-render produced a file (same INV-000042).")

    # Feature 3 smoke: invoice_prefix kwarg path. Three cases — custom
    # prefix, empty prefix (bare numbers), None prefix (legacy fallback).
    # Same "no content assertion, just don't crash" pattern as the rest
    # of this suite. Visual check the title field of each PDF:
    #   - invoice_custom.pdf      -> "INVOICE #ACME-000042"
    #   - invoice_bare.pdf        -> "INVOICE #000042"
    #   - invoice_fallback.pdf    -> "INVOICE #INV-000042" (legacy default)
    print("\nGenerating invoice_custom.pdf with invoice_prefix='ACME-'...")
    generate_document(invoice_snapshot, doc_type="INVOICE",
                      output_path="invoice_custom.pdf",
                      invoice_number=42, invoice_prefix="ACME-")
    print("OK: invoice_custom.pdf generated (visual check: ACME-000042).")

    print("Generating invoice_bare.pdf with invoice_prefix=''...")
    generate_document(invoice_snapshot, doc_type="INVOICE",
                      output_path="invoice_bare.pdf",
                      invoice_number=42, invoice_prefix="")
    print("OK: invoice_bare.pdf generated (visual check: bare 000042).")

    print("Generating invoice_fallback.pdf with invoice_prefix=None...")
    generate_document(invoice_snapshot, doc_type="INVOICE",
                      output_path="invoice_fallback.pdf",
                      invoice_number=42, invoice_prefix=None)
    print("OK: invoice_fallback.pdf generated (visual check: INV-000042).")

    print("\nAll tests passed. Check quote.pdf, invoice.pdf, and "
          "invoice_*.pdf for output.")

if __name__ == "__main__":
    run_test_suite()
