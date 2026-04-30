import hashlib
import uuid
from fpdf import FPDF

DEFAULT_BUSINESS_NAME = "YOUR BUSINESS NAME"
DEFAULT_PHONE_NUMBER = "(555) 123-4567"

# Sovereign footer defaults. {{phone}} and {{date}} are substituted by the
# controller (render_footer_template); the generator never sees an unrendered
# template. Kept here so the controller can import them as the fallback when
# a user has not customized their footer.
DEFAULT_QUOTE_FOOTER = "Quote expires: {{date}} | Text 'YES' to {{phone}} to approve this quote"
DEFAULT_INVOICE_FOOTER = "Payment due within 14 days | Questions? Call {{phone}}"

# Length caps (Heresy #10) — enforced at render time as a second line of
# defense; the controller also caps on save.
LABEL_MAX_LEN = 80
FOOTER_MAX_LEN = 200
CUSTOMER_NAME_MAX = 100
CUSTOMER_ADDR_MAX = 200
CUSTOMER_EMAIL_MAX = 254  # RFC 5321 max length
CUSTOMER_PHONE_MAX = 30


_UNICODE_REPLACEMENTS = {
    "\u2014": "-",  # em-dash
    "\u2013": "-",  # en-dash
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2026": "...",
}


def _sanitize_text(text, max_len):
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    for bad, good in _UNICODE_REPLACEMENTS.items():
        cleaned = cleaned.replace(bad, good)
    # Core FPDF fonts only support latin-1. Drop anything else so a rogue
    # input (emoji, CJK, etc.) can't crash PDF generation mid-flight.
    cleaned = cleaned.encode("latin-1", "ignore").decode("latin-1")
    return cleaned[:max_len]


def _sanitize_label(label):
    return _sanitize_text(label, LABEL_MAX_LEN)


class QuotingPDF(FPDF):
    def __init__(self, business_name=DEFAULT_BUSINESS_NAME, phone_number=DEFAULT_PHONE_NUMBER,
                 doc_type="QUOTE", quote_footer="", invoice_footer=""):
        super().__init__()
        self.business_name = business_name
        self.phone_number = phone_number
        self.doc_type = (doc_type or "QUOTE").upper()
        # Footers arrive pre-substituted from the controller (placeholders
        # already resolved). We re-sanitize here as defense in depth so a
        # bad value can never crash FPDF mid-render.
        self.quote_footer = _sanitize_text(quote_footer, FOOTER_MAX_LEN)
        self.invoice_footer = _sanitize_text(invoice_footer, FOOTER_MAX_LEN)

    def header(self):
        self.set_font("helvetica", "B", 20)
        self.set_text_color(44, 62, 80)
        self.cell(0, 10, self.business_name.upper(), ln=True, align="L")
        self.ln(10)

    def footer(self):
        self.set_y(-30)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        cta = self.invoice_footer if self.doc_type == "INVOICE" else self.quote_footer
        self.cell(0, 10, cta, align="C")


def derive_doc_code(quote_id):
    """
    Deterministic 8-char document code derived from the stored Quote.id.
    Same quote -> same code across re-renders (fixes the "every PDF gets a
    different number" design bug). Opaque, so it doesn't leak quote counts.
    """
    h = hashlib.sha1(f"Q{int(quote_id)}".encode()).hexdigest()
    return h[:8].upper()


def generate_document(snapshot, doc_type="QUOTE", output_path="output.pdf",
                      business_name=None, phone_number=None, label=None,
                      doc_code=None, quote_footer=None, invoice_footer=None,
                      customer_name=None, customer_address=None,
                      customer_email=None, customer_phone=None):
    """
    Generates a professional PDF based on a quote snapshot.
    This is a PURE VIEW. No calculations are performed here.

    doc_code: stable document identifier shown on the PDF. Pass the value
    from derive_doc_code(quote.id) so re-renders of the same stored quote
    (quote/invoice conversions, history re-downloads) share one number.
    Falls back to a random UUID for ad-hoc callers without a persisted row.

    quote_footer / invoice_footer: pre-rendered footer strings (placeholders
    already substituted by the controller). The active doc_type picks one;
    the other is still attached so multi-mode callers don't have to re-build
    a PDF object.
    """
    doc_type = (doc_type or "QUOTE").upper()
    pdf = QuotingPDF(
        business_name=business_name or DEFAULT_BUSINESS_NAME,
        phone_number=phone_number or DEFAULT_PHONE_NUMBER,
        doc_type=doc_type,
        quote_footer=quote_footer or "",
        invoice_footer=invoice_footer or "",
    )
    pdf.add_page()

    # Document Title & ID
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(0, 0, 0)
    code = doc_code or uuid.uuid4().hex[:8].upper()
    doc_title = f"{doc_type} #{code}"
    pdf.cell(0, 10, doc_title, ln=True, align="R")
    pdf.ln(5)

    # Bill To block — customer contact info. Each field is sanitized
    # defensively here (Heresy #10 second layer); controller already
    # length-caps on save. customer_name falls back to the legacy `label`
    # for quotes created before customer_* columns existed.
    safe_name = _sanitize_text(customer_name, CUSTOMER_NAME_MAX) or _sanitize_label(label)
    safe_address = _sanitize_text(customer_address, CUSTOMER_ADDR_MAX)
    safe_email = _sanitize_text(customer_email, CUSTOMER_EMAIL_MAX)
    safe_phone = _sanitize_text(customer_phone, CUSTOMER_PHONE_MAX)

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, "Bill To:", ln=True)
    pdf.set_font("helvetica", "", 11)
    if safe_name:
        pdf.cell(0, 6, safe_name, ln=True)
    if safe_address:
        pdf.multi_cell(0, 6, safe_address)
    if safe_email:
        pdf.cell(0, 6, safe_email, ln=True)
    if safe_phone:
        pdf.cell(0, 6, safe_phone, ln=True)
    pdf.cell(0, 6, f"Date: {snapshot['timestamp'][:10]}", ln=True)
    pdf.ln(5)

    # Line Items Table
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("helvetica", "B", 11)
    pdf.cell(130, 10, " Description", border=1, fill=True)
    pdf.cell(60, 10, " Amount", border=1, align="R", fill=True, ln=True)

    pdf.set_font("helvetica", "", 11)

    for item in snapshot['line_items']:
        description = item['description']
        cost = item['cost']
        cost_str = f"${cost:,.2f}"
        pdf.cell(130, 8, f" {description}", border="TRB", align="L")
        pdf.cell(60, 8, f"{cost_str}", border="TRB", align="R", ln=True)

    # Totals Section
    pdf.ln(10)
    pdf.set_font("helvetica", "", 11)
    calc = snapshot['calculation']

    pdf.cell(130, 8, "Subtotal (before tax):", align="R")
    pdf.cell(60, 8, f"${calc['final_before_tax']:,.2f}", align="R", ln=True)

    pdf.cell(130, 8, "Tax:", align="R")
    pdf.cell(60, 8, f"${calc['tax_amount']:,.2f}", align="R", ln=True)

    pdf.ln(2)
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(44, 62, 80)
    label_total = "AMOUNT DUE:" if doc_type == "INVOICE" else "GRAND TOTAL:"
    pdf.cell(130, 12, label_total, align="R")
    pdf.cell(60, 12, f"${calc['grand_total']:,.2f}", align="R", ln=True)

    pdf.output(output_path)
    return output_path
