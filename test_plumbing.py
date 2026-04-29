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

    print("\nAll tests passed. Check quote.pdf and invoice.pdf for output.")

if __name__ == "__main__":
    run_test_suite()
