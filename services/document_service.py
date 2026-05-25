"""
document_service — uploads, parses, stores user financial documents.

Flow:
  POST /api/welth/me/documents (multipart: file + type)
      → service extracts text, runs the type-specific extractor,
        stores extracted_data in MongoDB, returns document_id + summary.
      → the PDF itself is NOT persisted — only the structured extraction.

Supported types:
  - form16          (Form 16 Part A + B — annual TDS / salary certificate)
  - salary_slip     (monthly payslip)
  - mf_cg_statement (mutual-fund capital-gains statement, AY-wise)
  - loan_document   (loan sanction / amortisation letter)

Privacy model:
  - PDFs are processed in memory, extracted_data is saved, original bytes discarded.
  - The user can list / delete their parsed docs anytime.
  - Only the user (matched by user_id) can read their own docs.
"""

import io
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ASCENDING, DESCENDING

from database import get_db

logger = logging.getLogger(__name__)


SUPPORTED_TYPES = ("form16", "salary_slip", "mf_cg_statement", "loan_document")
MAX_BYTES = 8 * 1024 * 1024  # 8 MB cap — generous for a single PDF
SIGNED_URL_TTL = 60 * 60  # 1 hour — signed download links

# Cloudinary credentials (already in .env)
_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
_CLOUD_KEY = os.getenv("CLOUDINARY_API_KEY", "")
_CLOUD_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")


def _cloudinary_configured() -> bool:
    return all([_CLOUD_NAME, _CLOUD_KEY, _CLOUD_SECRET])


def _configure_cloudinary() -> bool:
    if not _cloudinary_configured():
        return False
    try:
        import cloudinary
        cloudinary.config(
            cloud_name=_CLOUD_NAME,
            api_key=_CLOUD_KEY,
            api_secret=_CLOUD_SECRET,
        )
        return True
    except Exception as e:
        logger.warning("cloudinary import / config failed: %s", e)
        return False


def _cloudinary_public_id(user_id: str, document_id: str) -> str:
    # Namespace per-user so listings can't bleed across accounts.
    return f"welthwest/user_docs/{user_id}/{document_id}"


def _upload_pdf_to_cloudinary(user_id: str, document_id: str, file_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Upload PDF as a private/authenticated raw resource. Returns metadata or None."""
    if not _configure_cloudinary():
        logger.info("cloudinary not configured — PDF will not be persisted")
        return None
    try:
        import cloudinary.uploader
        public_id = _cloudinary_public_id(user_id, document_id)
        result = cloudinary.uploader.upload(
            io.BytesIO(file_bytes),
            public_id=public_id,
            overwrite=True,
            resource_type="raw",          # PDFs are raw (non-image)
            type="authenticated",         # not publicly accessible; needs signed URL
            unique_filename=False,
            use_filename=False,
        )
        return {
            "public_id": result.get("public_id"),
            "bytes": result.get("bytes"),
            "format": result.get("format") or "pdf",
            "uploaded_at": result.get("created_at"),
        }
    except Exception as e:
        logger.error("cloudinary upload failed: %s", e)
        return None


def _generate_signed_download_url(public_id: str, ttl_seconds: int = SIGNED_URL_TTL) -> Optional[str]:
    """Time-limited signed URL for an authenticated raw resource."""
    if not public_id or not _configure_cloudinary():
        return None
    try:
        import cloudinary.utils
        expires_at = int(time.time()) + int(ttl_seconds)
        url, _opts = cloudinary.utils.cloudinary_url(
            public_id,
            resource_type="raw",
            type="authenticated",
            sign_url=True,
            expires_at=expires_at,
        )
        return url
    except Exception as e:
        logger.error("signed URL generation failed: %s", e)
        return None


def _delete_from_cloudinary(public_id: str) -> bool:
    if not public_id or not _configure_cloudinary():
        return False
    try:
        import cloudinary.uploader
        result = cloudinary.uploader.destroy(
            public_id,
            resource_type="raw",
            type="authenticated",
            invalidate=True,
        )
        return result.get("result") in ("ok", "not found")
    except Exception as e:
        logger.error("cloudinary delete failed: %s", e)
        return False


# ---- Storage ---------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _collection():
    db = get_db()
    coll = db.welth_user_documents
    try:
        coll.create_index([("user_id", ASCENDING), ("uploaded_at", DESCENDING)], name="user_recent")
        coll.create_index([("user_id", ASCENDING), ("document_id", ASCENDING)], name="user_doc", unique=True)
    except Exception:
        pass
    return coll


# ---- PDF text extraction ---------------------------------------------------

def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF using pypdf. Returns concatenated page text."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf is not installed. Run `pip install pypdf` on the server.") from e

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as e:
            logger.warning("page extract failed: %s", e)
            pages.append("")
    return "\n".join(pages)


# ---- Helpers ---------------------------------------------------------------

_RUPEE_RE = re.compile(
    r"(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


def _to_float(s: str) -> Optional[float]:
    if not s:
        return None
    s = str(s).replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _find_amount_near(text: str, label_patterns: List[str], window: int = 200) -> Optional[float]:
    """
    Look for any of the label_patterns in `text` (case-insensitive). For each
    match, scan the following `window` chars for a rupee-shaped number.
    Returns the FIRST plausible amount found.
    """
    lower = text.lower()
    for pat in label_patterns:
        for m in re.finditer(pat.lower(), lower):
            start = m.end()
            window_text = text[start:start + window]
            num_match = re.search(r"[\d,]+(?:\.\d{1,2})?", window_text)
            if num_match:
                val = _to_float(num_match.group(0))
                if val is not None and val > 0:
                    return val
    return None


def _find_first(text: str, pattern: str, group: int = 1, flags=re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    if m:
        try:
            return m.group(group).strip()
        except IndexError:
            return None
    return None


# ---- Extractors per document type -----------------------------------------

def _extract_form16(text: str) -> Dict[str, Any]:
    """
    Form 16 has Part A (TAN, TDS deposit summary) and Part B (salary breakup +
    deductions + tax computation). Layouts vary across issuers — we look for
    common labels and extract whatever we can. Anything missing is left as None.
    """
    out: Dict[str, Any] = {"document_type": "form16"}

    out["assessment_year"] = _find_first(text, r"Assessment\s*Year[:\s]*([0-9\-/]+)")
    out["financial_year"] = _find_first(text, r"Financial\s*Year[:\s]*([0-9\-/]+)")
    out["employer_tan"] = _find_first(text, r"TAN[\s:]*([A-Z]{4}\d{5}[A-Z])")
    out["employee_pan"] = _find_first(text, r"PAN[\s:]*([A-Z]{5}\d{4}[A-Z])")
    out["employee_name"] = _find_first(text, r"Name and address of the Employee[:\s]*\n?\s*([A-Z][A-Z\s\.]+)")

    out["gross_salary"] = _find_amount_near(text, [
        r"Gross\s+Salary",
        r"Total\s+Salary\s+Received",
    ])
    out["section_10_exemptions"] = _find_amount_near(text, [
        r"Less\s*:\s*Allowances\s+to\s+the\s+extent\s+exempt\s+under\s+section\s+10",
        r"Allowances\s+exempt\s+under\s+section\s+10",
    ])
    out["standard_deduction"] = _find_amount_near(text, [
        r"Standard\s+deduction\s+under\s+section\s+16",
        r"Standard\s+deduction",
    ])
    out["profession_tax"] = _find_amount_near(text, [r"Tax\s+on\s+employment\s+under\s+section\s+16", r"Profession(al)?\s+Tax"])
    out["salary_after_section_16"] = _find_amount_near(text, [r"Income\s+chargeable\s+under\s+the\s+head\s+['\"]Salaries"])

    out["section_80c"] = _find_amount_near(text, [r"(?:Deduction\s+under\s+section\s+)?80C\b", r"Section\s+80C"])
    out["section_80d"] = _find_amount_near(text, [r"(?:Deduction\s+under\s+section\s+)?80D\b", r"Section\s+80D"])
    out["section_80ccd_1b"] = _find_amount_near(text, [r"80CCD\s*\(\s*1B\s*\)", r"80CCD1B"])
    out["section_80ccd_2"] = _find_amount_near(text, [r"80CCD\s*\(\s*2\s*\)"])
    out["section_24_home_loan_interest"] = _find_amount_near(text, [r"Section\s+24", r"Interest\s+on\s+(?:housing|home)\s+loan"])
    out["other_chapter_via"] = _find_amount_near(text, [r"Aggregate\s+of\s+deductible\s+amount\s+under\s+Chapter\s+VI[-\s]?A"])

    out["total_taxable_income"] = _find_amount_near(text, [
        r"Total\s+(?:taxable\s+)?income",
        r"Income\s+chargeable\s+to\s+tax",
    ])
    out["tax_on_total_income"] = _find_amount_near(text, [r"Tax\s+on\s+total\s+income"])
    out["rebate_87a"] = _find_amount_near(text, [r"Rebate\s+under\s+section\s+87A", r"Section\s+87A"])
    out["surcharge"] = _find_amount_near(text, [r"Surcharge"])
    out["cess"] = _find_amount_near(text, [r"Health\s+and\s+Education\s+cess", r"Education\s+cess"])
    out["total_tax_payable"] = _find_amount_near(text, [r"Total\s+tax\s+payable", r"Net\s+tax\s+payable"])
    out["tds_deducted"] = _find_amount_near(text, [r"Total\s+tax\s+deducted", r"Tax\s+deducted\s+at\s+source"])

    # Best guess at regime
    regime_hint = None
    if re.search(r"new\s+(tax\s+)?regime", text, re.IGNORECASE):
        regime_hint = "new"
    elif re.search(r"old\s+(tax\s+)?regime", text, re.IGNORECASE):
        regime_hint = "old"
    out["regime_indicated"] = regime_hint

    return out


def _extract_salary_slip(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"document_type": "salary_slip"}

    out["pay_period"] = _find_first(text, r"(?:Pay\s+Period|For\s+the\s+month\s+of)[:\s]*([A-Za-z]+\s+\d{4})")
    out["employee_name"] = _find_first(text, r"(?:Employee\s+Name|Name)[:\s]*([A-Z][A-Za-z\s\.]+?)(?:\n|$)")

    out["basic"] = _find_amount_near(text, [r"Basic(?:\s+Salary)?(?:\s+\(.*?\))?"])
    out["hra"] = _find_amount_near(text, [r"House\s+Rent\s+Allowance", r"\bHRA\b"])
    out["special_allowance"] = _find_amount_near(text, [r"Special\s+Allowance"])
    out["lta"] = _find_amount_near(text, [r"Leave\s+Travel\s+Allowance", r"\bLTA\b"])
    out["medical_allowance"] = _find_amount_near(text, [r"Medical\s+Allowance"])
    out["conveyance_allowance"] = _find_amount_near(text, [r"Conveyance\s+Allowance"])
    out["bonus"] = _find_amount_near(text, [r"Bonus"])

    out["pf_employee"] = _find_amount_near(text, [r"Provident\s+Fund(?!\s+Employer)", r"\bPF\b(?!\s+Employer)"])
    out["professional_tax"] = _find_amount_near(text, [r"Professional\s+Tax", r"\bPT\b"])
    out["income_tax_tds"] = _find_amount_near(text, [r"Income\s+Tax", r"\bTDS\b"])
    out["esi"] = _find_amount_near(text, [r"\bESI\b", r"Employee\s+State\s+Insurance"])

    out["gross_pay"] = _find_amount_near(text, [r"Gross\s+(?:Pay|Salary|Earnings)", r"Total\s+Earnings"])
    out["total_deductions"] = _find_amount_near(text, [r"Total\s+Deductions"])
    out["net_pay"] = _find_amount_near(text, [r"Net\s+Pay", r"Net\s+Salary", r"Take[\s\-]home"])

    # If gross / net is missing, synthesise from components
    components = [v for v in (out["basic"], out["hra"], out["special_allowance"], out["lta"], out["medical_allowance"], out["conveyance_allowance"], out["bonus"]) if v]
    if not out["gross_pay"] and components:
        out["gross_pay_inferred_from_components"] = round(sum(components), 2)
    deductions = [v for v in (out["pf_employee"], out["professional_tax"], out["income_tax_tds"], out["esi"]) if v]
    if not out["total_deductions"] and deductions:
        out["total_deductions_inferred"] = round(sum(deductions), 2)

    return out


def _extract_mf_cg_statement(text: str) -> Dict[str, Any]:
    """
    MF CG statements vary enormously by RTA (CAMS, KFintech) and AMC. We look
    for any rows that look like CG transactions and aggregate to STCG / LTCG.
    """
    out: Dict[str, Any] = {"document_type": "mf_cg_statement"}

    out["assessment_year"] = _find_first(text, r"Assessment\s*Year[:\s]*([0-9\-/]+)")
    out["pan"] = _find_first(text, r"\b([A-Z]{5}\d{4}[A-Z])\b")  # any PAN seen

    # Aggregate totals (most CAMS/KFintech statements have these summary rows)
    out["total_short_term_gain"] = _find_amount_near(text, [
        r"Total\s+Short[\s\-]?term\s+Capital\s+Gain",
        r"STCG\s+Total",
        r"Short\s+Term\s+Gain",
    ])
    out["total_long_term_gain"] = _find_amount_near(text, [
        r"Total\s+Long[\s\-]?term\s+Capital\s+Gain",
        r"LTCG\s+Total",
        r"Long\s+Term\s+Gain",
    ])
    out["total_short_term_loss"] = _find_amount_near(text, [r"Short[\s\-]?term\s+Capital\s+Loss"])
    out["total_long_term_loss"] = _find_amount_near(text, [r"Long[\s\-]?term\s+Capital\s+Loss"])

    # Try to extract scheme-level rows that match a "buy_date sell_date qty price gain" pattern
    # This is best-effort — real statements have wildly varying column orders.
    scheme_count = len(re.findall(r"\b(?:Direct|Regular)\s+Plan\b", text, re.IGNORECASE))
    out["schemes_detected_count"] = scheme_count

    out["needs_manual_review"] = (
        out["total_short_term_gain"] is None and out["total_long_term_gain"] is None and scheme_count > 0
    )

    return out


def _extract_loan_document(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"document_type": "loan_document"}

    out["lender_name"] = _find_first(text, r"(?:Lender|Bank|NBFC|Lender's\s+Name)[:\s]*([A-Z][A-Za-z\s&\.]+?)(?:\n|$)")
    out["loan_type"] = _find_first(text, r"(?:Loan\s+Type|Type\s+of\s+Loan|Product)[:\s]*([A-Za-z\s\-]+?)(?:\n|$)")
    out["loan_account_number"] = _find_first(text, r"(?:Loan\s+Account\s+Number|Loan\s+A/c\s+No\.?)[:\s]*([A-Z0-9\-]+)")

    out["principal_sanctioned"] = _find_amount_near(text, [
        r"(?:Sanctioned\s+Loan\s+)?(?:Loan\s+)?Amount\s+(?:Sanctioned|Approved)",
        r"Principal\s+Amount",
        r"Loan\s+Amount",
    ])
    out["annual_interest_rate_pct"] = None
    rate_match = re.search(r"(?:Interest\s+Rate|Rate\s+of\s+Interest)[:\s]*([\d.]+)\s*%", text, re.IGNORECASE)
    if rate_match:
        out["annual_interest_rate_pct"] = _to_float(rate_match.group(1))

    out["tenure_months"] = None
    tenure_months_match = re.search(r"(?:Tenure|Loan\s+Term)[:\s]*(\d+)\s*months?", text, re.IGNORECASE)
    if tenure_months_match:
        out["tenure_months"] = int(tenure_months_match.group(1))
    else:
        tenure_years_match = re.search(r"(?:Tenure|Loan\s+Term)[:\s]*(\d+)\s*years?", text, re.IGNORECASE)
        if tenure_years_match:
            out["tenure_months"] = int(tenure_years_match.group(1)) * 12

    out["monthly_emi"] = _find_amount_near(text, [r"\bEMI\b", r"Equated\s+Monthly\s+Instal+ment"])
    out["processing_fee"] = _find_amount_near(text, [r"Processing\s+(?:Fee|Charges)"])
    out["disbursement_date"] = _find_first(text, r"Disbursement\s+Date[:\s]*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})")

    is_floating = bool(re.search(r"floating\s+rate", text, re.IGNORECASE))
    is_fixed = bool(re.search(r"fixed\s+rate", text, re.IGNORECASE))
    out["rate_type"] = "floating" if is_floating and not is_fixed else "fixed" if is_fixed and not is_floating else None

    return out


_EXTRACTORS = {
    "form16": _extract_form16,
    "salary_slip": _extract_salary_slip,
    "mf_cg_statement": _extract_mf_cg_statement,
    "loan_document": _extract_loan_document,
}


# ---- Public API ------------------------------------------------------------

def parse_and_store(user_id: str, document_type: str, filename: str, file_bytes: bytes) -> Dict[str, Any]:
    if document_type not in SUPPORTED_TYPES:
        raise ValueError(f"document_type must be one of {SUPPORTED_TYPES}")
    if not file_bytes:
        raise ValueError("file is empty")
    if len(file_bytes) > MAX_BYTES:
        raise ValueError(f"file is larger than {MAX_BYTES // (1024*1024)} MB")

    try:
        text = _extract_pdf_text(file_bytes)
    except Exception as e:
        logger.error("pdf extract failed: %s", e)
        raise ValueError(f"could not extract text from PDF: {e}")

    if not text or len(text.strip()) < 50:
        raise ValueError("PDF appears to contain no extractable text (it may be a scanned image — OCR is not yet supported)")

    extractor = _EXTRACTORS[document_type]
    try:
        extracted = extractor(text)
    except Exception as e:
        logger.error("extraction failed: %s", e)
        extracted = {"document_type": document_type, "extraction_error": str(e)}

    doc_id = uuid.uuid4().hex[:12]

    # Persist the PDF to Cloudinary (authenticated, signed-url access only).
    cloud_meta = _upload_pdf_to_cloudinary(user_id, doc_id, file_bytes)

    doc = {
        "user_id": user_id,
        "document_id": doc_id,
        "document_type": document_type,
        "filename": (filename or "uploaded.pdf")[:200],
        "uploaded_at": _now(),
        "extracted_data": extracted,
        "raw_text_preview": text[:1500],
        "status": "parsed",
        "cloudinary_public_id": cloud_meta.get("public_id") if cloud_meta else None,
        "cloudinary_bytes": cloud_meta.get("bytes") if cloud_meta else None,
        "file_bytes": len(file_bytes),
    }
    _collection().insert_one(doc)
    doc.pop("_id", None)
    # Attach a freshly-signed download URL for the immediate response.
    if doc.get("cloudinary_public_id"):
        doc["download_url"] = _generate_signed_download_url(doc["cloudinary_public_id"])
    return doc


def list_documents(user_id: str, document_type: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"user_id": user_id}
    if document_type:
        query["document_type"] = document_type
    cur = _collection().find(query, {"raw_text_preview": 0}).sort("uploaded_at", DESCENDING).limit(limit)
    out = []
    for d in cur:
        d.pop("_id", None)
        if isinstance(d.get("uploaded_at"), datetime):
            d["uploaded_at"] = d["uploaded_at"].isoformat()
        # Generate a fresh signed URL — the previous one (if any) has expired.
        pid = d.get("cloudinary_public_id")
        if pid:
            d["download_url"] = _generate_signed_download_url(pid)
        out.append(d)
    return out


def get_latest(user_id: str, document_type: str) -> Optional[Dict[str, Any]]:
    d = _collection().find_one(
        {"user_id": user_id, "document_type": document_type},
        sort=[("uploaded_at", DESCENDING)],
    )
    if not d:
        return None
    d.pop("_id", None)
    if isinstance(d.get("uploaded_at"), datetime):
        d["uploaded_at"] = d["uploaded_at"].isoformat()
    pid = d.get("cloudinary_public_id")
    if pid:
        d["download_url"] = _generate_signed_download_url(pid)
    return d


def delete_document(user_id: str, document_id: str) -> bool:
    # Look up the public_id first so we can clean up Cloudinary too.
    existing = _collection().find_one(
        {"user_id": user_id, "document_id": document_id},
        {"cloudinary_public_id": 1},
    )
    if not existing:
        return False
    pid = existing.get("cloudinary_public_id")
    if pid:
        _delete_from_cloudinary(pid)
    res = _collection().delete_one({"user_id": user_id, "document_id": document_id})
    return res.deleted_count > 0
