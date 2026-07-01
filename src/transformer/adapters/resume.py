"""Résumé adapter (UNSTRUCTURED prose: PDF or DOCX).

Real résumés vary wildly in layout, so this adapter is **section-aware** and
**format-flexible** rather than tied to one template:

* it segments the text into sections by recognized headings (summary, experience,
  projects, education, skills, ...);
* name from the header block; emails/phones/links (GitHub, LinkedIn, portfolio)
  scanned from the whole text;
* experience entries parsed by detecting a trailing date-range and splitting the
  remainder into title / company — handles both ``"Title, Company (Jan 2021 –
  Present)"`` and ``"Title – Company   Jun 2026 – Present"``;
* education parsed both single-line (``"B.S. in CS, MIT, 2018"``) and multi-line
  (``"B.Tech ... 2023 – 2027"`` with the institution on the next line);
* skills read from the SKILLS section, stripping ``"Category:"`` prefixes and
  parentheticals.

Prose is noisy, so fragments carry lower ``raw_confidence`` than structured
sources, and anything that doesn't match is left out — never guessed. A
corrupt/unreadable file yields ``[]`` (the run must not crash).

Location is deliberately NOT inferred from a résumé (it's genuinely ambiguous —
e.g. a university's state is not the candidate's current city). ``headline`` is
left to the optional LLM enrichment lane by design.
"""

from __future__ import annotations

import re
from typing import ClassVar

from transformer.adapters.base import EMAIL_RE, FieldFragment, RawSource, clean_email
from transformer.models import Method, SourceType
from transformer.normalize.dates import parse_date_range
from transformer.normalize.phones import extract_phones
from transformer.normalize.skills import canonicalize_skill

# --- Section segmentation --------------------------------------------------- #
# Normalized heading text -> canonical section name.
_SECTION_MAP: dict[str, str] = {
    "summary": "summary", "objective": "summary", "profile": "summary", "about": "summary",
    "professional summary": "summary",
    "experience": "experience", "work experience": "experience",
    "professional experience": "experience", "employment": "experience",
    "employment history": "experience", "work history": "experience",
    "projects": "projects", "personal projects": "projects", "key projects": "projects",
    "education": "education", "academic background": "education", "academics": "education",
    "skills": "skills", "technical skills": "skills", "core skills": "skills",
    "skills & interests": "skills", "technical proficiencies": "skills",
    "certifications": "certifications", "certificates": "certifications",
    "achievements": "achievements", "key achievements": "achievements", "awards": "achievements",
    "publications": "publications", "interests": "interests", "languages": "languages",
    "references": "references", "contact": "contact",
}

# --- Dates in experience lines --------------------------------------------- #
_MONTHS = (
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|"
    r"April|June|July|August|September|October|November|December)"
)
_DATE_TOKEN = rf"(?:{_MONTHS}\.?\s+\d{{4}}|\d{{4}})"
_DATE_RANGE = rf"{_DATE_TOKEN}\s*(?:[-–—]|to)\s*(?:Present|Current|Now|Ongoing|{_DATE_TOKEN})"
_TRAILING_DATES = re.compile(rf"\(?\s*(?P<dates>{_DATE_RANGE})\s*\)?\s*$", re.IGNORECASE)

# --- Education ------------------------------------------------------------- #
# Strict single-line form: "B.S. in Computer Science, MIT, 2018".
_EDUCATION_RE = re.compile(
    r"^(?P<degree>(?:B\.?S\.?|M\.?S\.?|B\.?A\.?|M\.?A\.?|Ph\.?D\.?|B\.?Eng\.?|B\.?Tech\.?|"
    r"M\.?Tech\.?|MBA|Bachelor|Master|Associate|Diploma)[^,]*?)(?:\s+in\s+(?P<field>[^,]+))?,\s*"
    r"(?P<institution>[^,]+),\s*(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_DEGREE_WORDS = re.compile(
    r"\b(?:b\.?tech|m\.?tech|b\.?e|b\.?s|m\.?s|b\.?a|m\.?a|ph\.?d|mba|bachelor|master|"
    r"associate|diploma|class\s+x{1,2}i{0,2}|class\s+\d+|high school|hsc|ssc|10th|12th)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_GPA_RE = re.compile(r"\b(?:gpa|cgpa|percentage|score|marks)\b", re.IGNORECASE)

# --- Links ----------------------------------------------------------------- #
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)", re.IGNORECASE)
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in|pub)/([A-Za-z0-9._%-]+)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s|)>\]]+", re.IGNORECASE)

# --- Name ------------------------------------------------------------------ #
_NAME_DELIM = re.compile(r"\s*(?:[|—·•]|\s-\s)\s*")
_NAME_TOKEN = re.compile(r"^[A-Z][A-Za-z.'’-]*$")
_TITLE_WORDS = {
    "engineer", "developer", "manager", "intern", "analyst", "architect", "student",
    "consultant", "designer", "lead", "scientist", "administrator", "specialist",
    "resume", "curriculum", "vitae", "cv",
}

_SKILL_SPLIT = re.compile(r"[,;•|/]+")
_BULLET_PREFIX = re.compile(r"^\s*[\-–—•*·▪‣◦]\s*")


class ResumeAdapter:
    """Adapter for PDF/DOCX résumés."""

    source_type: ClassVar[SourceType] = SourceType.RESUME

    def detect(self, raw: RawSource) -> bool:
        return raw.path.suffix.lower() in {".pdf", ".docx", ".doc"}

    def extract(self, raw: RawSource) -> list[FieldFragment]:
        text = read_text(raw)
        if not text:
            return []
        return _fragments_from_text(text, raw.path.stem)


# --------------------------------------------------------------------------- #
# Parsing (module-level so it's unit-testable on raw text, no file needed)
# --------------------------------------------------------------------------- #
def _fragments_from_text(text: str, record_key: str) -> list[FieldFragment]:
    lines = [ln.strip() for ln in text.splitlines()]
    header, sections = _segment(lines)
    src = SourceType.RESUME.value
    fragments: list[FieldFragment] = []

    def add(field_path: str, value: object, conf: float, normalize: str | None = None) -> None:
        fragments.append(
            FieldFragment(
                field_path=field_path, value=value, source=src, method=Method.REGEX,
                raw_confidence=conf, record_key=record_key, normalize_method=normalize,
            )
        )

    # Name (from the header block, before the first section heading).
    name = _extract_name(header)
    if name:
        add("full_name", name, 0.7)

    # Emails (deduped, order-stable).
    seen_emails: set[str] = set()
    for match in EMAIL_RE.finditer(text):
        email = clean_email(match.group(0))
        if email and email not in seen_emails:
            seen_emails.add(email)
            add("emails", email, 0.8)

    # Phones (validated + E.164 by the normalizer).
    for phone in extract_phones(text):
        add("phones", phone, 0.8, normalize=Method.PHONE_NORMALIZE)

    # Links: GitHub / LinkedIn / portfolio / other.
    for field_path, url in _extract_links(text):
        add(field_path, url, 0.75)

    # Experience (only within the experience section).
    for entry in _extract_experience(sections.get("experience", [])):
        add("experience", entry, 0.7, normalize=Method.DATE_PARSE)

    # Education (single-line strict form anywhere + multi-line within the section).
    for entry in _extract_education(sections.get("education", []), lines):
        add("education", entry, 0.7)

    # Skills (from the skills section, category-prefix aware).
    for raw_skill in _extract_skills(sections.get("skills", [])):
        canon = canonicalize_skill(raw_skill)
        if canon.name:
            add("skills", canon.name, 0.7 if canon.canonical else 0.5,
                normalize=Method.SKILL_CANONICALIZE)

    return fragments


def _section_key(line: str) -> str | None:
    norm = line.lower().strip().rstrip(":").strip()
    if not norm or len(norm) > 30:
        return None
    return _SECTION_MAP.get(norm)


def _segment(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Split résumé lines into a header block + {section: lines}."""

    header: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        key = _section_key(line)
        if key is not None:
            current = key
            sections.setdefault(key, [])
            continue
        if current is None:
            header.append(line)
        else:
            sections[current].append(line)
    return header, sections


def _looks_like_name(candidate: str) -> bool:
    tokens = candidate.split()
    if not (2 <= len(tokens) <= 4):
        return False
    if any(tok.lower().strip(".") in _TITLE_WORDS for tok in tokens):
        return False
    return all(_NAME_TOKEN.match(tok) for tok in tokens)


def _extract_name(header: list[str]) -> str | None:
    for line in header[:4]:
        if not line:
            continue
        candidate = _NAME_DELIM.split(line, maxsplit=1)[0].strip().rstrip(",")
        if _looks_like_name(candidate):
            return candidate
    return None


def _extract_links(text: str) -> list[tuple[str, str]]:
    """Return (field_path, url) pairs for github/linkedin/portfolio/other."""

    out: list[tuple[str, str]] = []
    gh = _GITHUB_RE.search(text)
    if gh:
        out.append(("links.github", f"https://github.com/{gh.group(1)}"))
    li = _LINKEDIN_RE.search(text)
    if li:
        out.append(("links.linkedin", f"https://linkedin.com/in/{li.group(1)}"))

    # Remaining full URLs that aren't github/linkedin -> portfolio (first) + other.
    seen: set[str] = set()
    others: list[str] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,);]")
        low = url.lower()
        if "github.com" in low or "linkedin.com" in low or url in seen:
            continue
        seen.add(url)
        others.append(url)
    if others:
        out.append(("links.portfolio", others[0]))
        for extra in others[1:]:
            out.append(("links.other", extra))
    return out


def _split_title_company(head: str) -> tuple[str, str | None]:
    """Split "Title – Company" / "Title, Company" on the FIRST separator."""

    separators = [" – ", " — ", " - ", ", ", " at ", " @ "]
    positions = [(head.find(sep), sep) for sep in separators if head.find(sep) != -1]
    if not positions:
        return head.strip(), None
    pos, sep = min(positions)
    return head[:pos].strip(), head[pos + len(sep):].strip() or None


def _extract_experience(section_lines: list[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line in section_lines:
        if not line or _BULLET_PREFIX.match(line):
            continue
        m = _TRAILING_DATES.search(line)
        if not m:
            continue  # entry lines carry a date range; descriptions don't
        head = line[: m.start()].strip().rstrip("(").strip().rstrip(",").strip()
        if not head:
            continue
        title, company = _split_title_company(head)
        start, end = parse_date_range(m.group("dates"))
        entries.append({
            "company": company, "title": title or None,
            "start": start, "end": end, "summary": None,
        })
    return entries


def _split_degree_field(text: str) -> tuple[str, str | None]:
    match = re.search(r"\s+in\s+", text, re.IGNORECASE)
    if match:
        return text[: match.start()].strip(), text[match.end():].strip() or None
    return text.strip(), None


def _extract_education(section_lines: list[str], all_lines: list[str]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    matched_single: set[str] = set()

    # Pass 1: strict single-line form, scanned across the whole résumé (keeps the
    # simple "Degree in Field, Institution, YYYY" layout working).
    for line in all_lines:
        m = _EDUCATION_RE.match(line)
        if not m:
            continue
        matched_single.add(line)
        field = m.group("field")
        entries.append({
            "institution": m.group("institution").strip(),
            "degree": m.group("degree").strip(),
            "field": field.strip() if field else None,
            "end_year": int(m.group("year")),
        })

    # Pass 2: multi-line form within the education section — a degree/qualification
    # line carrying a year, with the institution on a following line.
    n = len(section_lines)
    for i, line in enumerate(section_lines):
        if not line or line in matched_single or _BULLET_PREFIX.match(line):
            continue
        years = _YEAR_RE.findall(line)
        if not years or not _DEGREE_WORDS.search(line):
            continue
        end_year = max(int(y) for y in years)
        degree_text = _YEAR_RE.sub("", line)
        degree_text = re.sub(r"[–—\-]", " ", degree_text)  # drop range dashes
        degree_text = re.sub(r"\s{2,}", " ", degree_text).strip(" ,–-—")
        degree, field = _split_degree_field(degree_text)

        institution: str | None = None
        for j in range(i + 1, min(i + 3, n)):
            nxt = section_lines[j].strip()
            if not nxt or _GPA_RE.search(nxt):
                continue
            if _YEAR_RE.search(nxt) and _DEGREE_WORDS.search(nxt):
                break  # that's the next entry, not this institution
            institution = nxt.split(",")[0].strip()
            break

        entries.append({
            "institution": institution, "degree": degree or None,
            "field": field, "end_year": end_year,
        })
    return entries


def _extract_skills(section_lines: list[str]) -> list[str]:
    raw_skills: list[str] = []
    for line in section_lines:
        text = _BULLET_PREFIX.sub("", line).strip()
        if not text:
            continue
        # Strip a leading "Category:" label (e.g. "Programming Languages: Java, ...").
        if ":" in text:
            label, _, rest = text.partition(":")
            if len(label) <= 45 and re.fullmatch(r"[A-Za-z0-9 &/+.\-]+", label):
                text = rest.strip()
        for token in _SKILL_SPLIT.split(text):
            token = re.sub(r"\s*\([^)]*\)", "", token).strip().strip(".")
            if token and len(token) <= 40:
                raw_skills.append(token)
    return raw_skills


def read_text(raw: RawSource) -> str:
    """Extract plain text from a PDF or DOCX; '' on any read failure.

    Public so the optional enrichment lane can recover résumé prose (a DOCX/PDF's
    text is never in ``raw.text``, which is the best-effort UTF-8 decode).
    """

    suffix = raw.path.suffix.lower()
    try:
        if suffix == ".pdf":
            import pdfplumber

            with pdfplumber.open(str(raw.path)) as pdf:
                return "\n".join((page.extract_text() or "") for page in pdf.pages)
        if suffix in {".docx", ".doc"}:
            import docx

            document = docx.Document(str(raw.path))
            return "\n".join(p.text for p in document.paragraphs)
    except Exception:
        # Corrupt/unreadable résumé -> graceful empty.
        return ""
    return ""
