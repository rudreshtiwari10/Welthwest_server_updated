"""Tools: parse_form16, parse_salary_slip, parse_mf_cg_statement, parse_loan_document.

Each tool reads the signed-in user's MOST-RECENT uploaded document of the given
type and returns the parsed structured data. Auth-gated. Returns a clean note
if no document of that type has been uploaded yet.
"""

from agent.tools.base import Tool, ToolResult


_NOT_AUTHED = "Sign in to read your uploaded documents."
_HOW_TO_UPLOAD = (
    "No document found. Upload one from Account → Money Profile → Documents tab. "
    "Supported PDFs: Form 16, salary slip, mutual-fund capital-gains statement, loan document."
)


def _read_latest(_ctx: dict, doc_type: str, friendly_name: str) -> ToolResult:
    uid = (_ctx or {}).get("user_id")
    if not uid:
        return ToolResult(success=False, error=_NOT_AUTHED)
    try:
        from services.document_service import get_latest
        doc = get_latest(uid, doc_type)
        if not doc:
            return ToolResult(success=True, data={"found": False, "note": _HOW_TO_UPLOAD})
        # Strip raw_text_preview from agent-visible payload — keep response lean
        extracted = doc.get("extracted_data") or {}
        return ToolResult(success=True, data={
            "found": True,
            "document_id": doc.get("document_id"),
            "filename": doc.get("filename"),
            "uploaded_at": doc.get("uploaded_at"),
            "document_type": doc_type,
            "extracted": extracted,
        }, display_hint=f"document_{doc_type}")
    except Exception as e:
        return ToolResult(success=False, error=f"Could not load {friendly_name}: {e}")


class ParseForm16Tool(Tool):
    name = "parse_form16"
    description = (
        "Read the user's most-recently uploaded Form 16 (annual TDS / salary certificate). "
        "Returns: assessment year, gross salary, standard deduction, exemptions, 80C / 80D / "
        "80CCD splits, taxable income, tax computed, 87A rebate, surcharge, cess, total tax, "
        "TDS deducted, and a best-guess regime indicator. Use whenever the user asks 'how "
        "much tax did I pay last year', 'what's on my Form 16', 'help me file ITR using "
        "my Form 16', or wants to compute their actual tax under both regimes using their "
        "real numbers from the certificate."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        return _read_latest(_ctx, "form16", "Form 16")


class ParseSalarySlipTool(Tool):
    name = "parse_salary_slip"
    description = (
        "Read the user's most-recently uploaded salary slip. Returns: pay period, basic, "
        "HRA, special allowance, LTA, medical, conveyance, bonus, plus deductions (PF, "
        "professional tax, TDS, ESI), gross pay, total deductions, net take-home. Use "
        "for 'analyse my payslip', 'how much HRA am I getting', 'why is my net pay low', "
        "or to back-fill numbers into compare_tax_regimes / compute_hra_exemption."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        return _read_latest(_ctx, "salary_slip", "salary slip")


class ParseMfCgStatementTool(Tool):
    name = "parse_mf_cg_statement"
    description = (
        "Read the user's most-recently uploaded mutual-fund capital-gains statement (the "
        "AY-wise statement issued by CAMS / KFintech). Returns: assessment year, PAN, total "
        "short-term capital gain, total long-term capital gain, total losses, and a flag if "
        "the statement looks like it needs manual review. Use for 'help me file my MF gains', "
        "'how much LTCG do I owe', or to feed numbers into compute_capital_gains_tax."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        return _read_latest(_ctx, "mf_cg_statement", "MF capital-gains statement")


class ParseLoanDocumentTool(Tool):
    name = "parse_loan_document"
    description = (
        "Read the user's most-recently uploaded loan-document PDF (sanction letter / "
        "amortisation schedule / agreement). Returns: lender, loan type, account number, "
        "principal sanctioned, annual rate, tenure, EMI, processing fee, rate type "
        "(fixed/floating). Use for 'review my loan', 'what are the terms', or to feed "
        "numbers into compute_emi / compute_loan_amortization / compare_prepay_vs_invest."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        return _read_latest(_ctx, "loan_document", "loan document")
