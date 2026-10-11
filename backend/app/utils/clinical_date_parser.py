import re
from datetime import date, datetime

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "sept": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _parse_date_string(s: str) -> date | None:
    """Parse a single date string into a datetime.date object."""
    if not s:
        return None
    s = s.strip()

    # Format: YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD
    m_iso = re.match(r"^(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})$", s)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
            try:
                return date(y, m, d)
            except ValueError:
                pass

    # Format: DD-Mon-YYYY or DD Mon YYYY or DD/Mon/YYYY
    m_mon = re.match(r"^(\d{1,2})[-/\s]+([A-Za-z]{3,9})[-/,\s]+(\d{2,4})$", s)
    if m_mon:
        d, mon_str, y = int(m_mon.group(1)), m_mon.group(2).lower(), int(m_mon.group(3))
        if y < 100:
            y += 2000
        m = MONTHS.get(mon_str)
        if m and 1900 <= y <= 2100 and 1 <= d <= 31:
            try:
                return date(y, m, d)
            except ValueError:
                pass

    # Format: Mon DD, YYYY or Mon DD YYYY
    m_mon2 = re.match(r"^([A-Za-z]{3,9})[-/\s]+(\d{1,2})[-/,\s]+(\d{2,4})$", s)
    if m_mon2:
        mon_str, d, y = m_mon2.group(1).lower(), int(m_mon2.group(2)), int(m_mon2.group(3))
        if y < 100:
            y += 2000
        m = MONTHS.get(mon_str)
        if m and 1900 <= y <= 2100 and 1 <= d <= 31:
            try:
                return date(y, m, d)
            except ValueError:
                pass

    # Format: DD/MM/YYYY or DD-MM-YYYY or MM/DD/YYYY
    m_num = re.match(r"^(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2,4})$", s)
    if m_num:
        p1, p2, y = int(m_num.group(1)), int(m_num.group(2)), int(m_num.group(3))
        if y < 100:
            y += 2000
        # If p2 > 12 and p1 <= 12: MM/DD/YYYY
        if p2 > 12 and 1 <= p1 <= 12:
            m, d = p1, p2
        else:
            # Default clinical convention: DD/MM/YYYY
            d, m = p1, p2
        if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
            try:
                return date(y, m, d)
            except ValueError:
                pass

    return None


def parse_clinical_date(text: str) -> date | None:
    """Extract clinical report / encounter date from medical document text.
    
    Checks clinical header patterns first (e.g. 'Report Date:', 'Collection Date:',
    'Date:'), then falls back to general date patterns in the text.
    """
    if not text:
        return None

    # Focus on the first ~3000 characters where headers / dates typically live
    header_text = text[:3000]

    # 1. Look for labeled date patterns in clinical header
    label_pattern = re.compile(
        r"(?:date\s*of\s*(?:collection|examination|report|service|visit|test|sample|admission)|"
        r"report(?:ing)?\s*date|collection\s*date|sample\s*date|specimen\s*date|"
        r"visit\s*date|test\s*date|exam(?:ination)?\s*date|scheduled\s*date|"
        r"encounter\s*date|दिनांक|तारिख|date)\s*[:：\-–|]\s*([A-Za-z0-9,\.\s/\-]+?)(?:[\r\n|;]|  |\t|$)",
        re.IGNORECASE,
    )

    matches = label_pattern.findall(header_text)
    for raw in matches:
        raw = raw.strip(" ,;:-|\t\r\n")
        d = _parse_date_string(raw)
        if d:
            return d

    # 2. General date patterns in text (e.g. 2025-10-15 or 15-Oct-2025)
    general_pattern = re.compile(
        r"\b(\d{1,2}[-/\.](?:[A-Za-z]{3,9}|\d{1,2})[-/\.]\d{2,4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})\b"
    )
    for raw in general_pattern.findall(header_text):
        d = _parse_date_string(raw.strip())
        if d:
            return d

    return None
