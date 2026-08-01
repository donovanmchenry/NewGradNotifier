"""Conservative heuristic scorer for fit and difficulty."""

from __future__ import annotations

from collections import defaultdict

from newgrad_notifier.config.settings import CandidateProfile
from newgrad_notifier.contracts import NormalizedJob, RankingResult, Recommendation

SKILL_PATTERNS: dict[str, tuple[str, ...]] = {
    "Python": ("python",),
    "TypeScript": ("typescript",),
    "JavaScript": ("javascript",),
    "Java": ("java",),
    "C++": ("c++", "cpp"),
    "SQL": ("sql",),
    "React": ("react",),
    "Next.js": ("next.js", "nextjs"),
    "Node.js": ("node.js", "nodejs", "node "),
    "FastAPI": ("fastapi",),
    "Flask": ("flask",),
    "Express": ("express",),
    "Docker": ("docker",),
    "GitHub Actions": ("github actions",),
    "REST APIs": ("rest api", "restful"),
    "Apollo Client": ("apollo",),
    "MUI": ("mui", "material ui"),
    "Zustand": ("zustand",),
    "Pydantic": ("pydantic",),
    "Selenium": ("selenium",),
    "Langfuse": ("langfuse",),
    "Retrieval-Augmented Generation": ("retrieval-augmented generation", "retrieval augmented generation", "rag pipeline"),
    "Model Context Protocol": ("model context protocol", "mcp server"),
    "Kubernetes": ("kubernetes", "k8s"),
    "Go": ("golang", " go "),
    "Rust": ("rust",),
    "Ruby": ("ruby", "rails"),
    "AWS": ("aws", "amazon web services"),
    "GCP": ("gcp", "google cloud"),
}

HIGH_BAR_COMPANIES = {
    "OpenAI",
    "Anthropic",
    "Stripe",
    "Meta",
    "Google",
    "Apple",
    "Databricks",
    "Snowflake",
    "Datadog",
    "Palantir",
    "NVIDIA",
}

ROLE_TAGS = {
    "frontend": ("frontend", "front end", "ui engineer"),
    "backend": ("backend", "back end", "api"),
    "full_stack": ("full stack", "full-stack"),
    "product_engineering": ("product engineer", "product engineering"),
    "new_grad": ("new grad", "university graduate", "recent graduate", "class of 2027"),
}

MISMATCH_HINTS = (
    "firmware",
    "embedded",
    "data analyst",
    "it support",
    "site reliability",
    "sre",
    "devops",
    "research scientist",
)


def _text(job: NormalizedJob) -> str:
    return f"{job.title} {job.description_text} {job.location_text or ''}".lower()


def extract_matching_skills(job: NormalizedJob, profile: CandidateProfile) -> tuple[list[str], list[str]]:
    """Return the overlapping and missing skills from a controlled catalog."""

    text = _text(job)
    candidate_skills = set(profile.skills)
    matching: list[str] = []
    missing: list[str] = []
    for skill, patterns in SKILL_PATTERNS.items():
        present = any(pattern in text for pattern in patterns)
        if present and skill in candidate_skills:
            matching.append(skill)
        elif present and skill not in candidate_skills:
            missing.append(skill)
    return matching[:6], missing[:6]


def classify_tags(job: NormalizedJob) -> list[str]:
    """Generate coarse category tags for downstream filtering."""

    text = _text(job)
    tags: list[str] = []
    for tag, patterns in ROLE_TAGS.items():
        if any(pattern in text for pattern in patterns):
            tags.append(tag)
    if job.is_remote:
        tags.append("remote")
    if any(term in text for term in ("software engineer i", "associate software engineer", "entry level")):
        tags.append("entry_level")
    return sorted(set(tags))


def _fit_score(job: NormalizedJob, profile: CandidateProfile, company_priority: int) -> tuple[int, dict[str, int]]:
    text = _text(job)
    breakdown = defaultdict(int)

    if any(term in text for term in ("software engineer", "software developer", "product engineer")):
        breakdown["role_match"] += 22
    if any(term in text for term in ("frontend", "front end", "react", "next.js")):
        breakdown["role_match"] += 5
    if any(term in text for term in ("backend", "back end", "api", "node", "python")):
        breakdown["role_match"] += 5

    if any(term in text for term in ("new grad", "university graduate", "recent graduate", "new college graduate")):
        breakdown["graduation_match"] += 15
    if "2027" in text:
        breakdown["graduation_match"] += 5
    elif any(term in text for term in ("0-1 years", "0 to 1 years", "1 year", "new college graduate")):
        breakdown["graduation_match"] += 6
    if any(term in text for term in ("early career", "entry level", "engineer i", "associate software engineer")):
        breakdown["entry_level_signal"] += 8

    matching_skills, _ = extract_matching_skills(job, profile)
    breakdown["skill_overlap"] += min(18, len(matching_skills) * 3)

    if any(term in text for term in ("api", "web application", "customer", "product", "frontend", "backend")):
        breakdown["product_profile"] += 6
    if any(term in text for term in ("collaborate", "ship", "customer-facing")):
        breakdown["experience_signal"] += 2

    if job.is_remote or any(location.lower() in (job.location_text or "").lower() for location in profile.preferred_locations):
        breakdown["location_match"] += 4

    if any(term in text for term in ("senior", "staff", "lead", "principal", "5+ years", "7+ years")):
        breakdown["seniority_penalty"] -= 35
    elif any(term in text for term in ("2+ years", "3+ years")):
        breakdown["seniority_penalty"] -= 18
    else:
        breakdown["seniority_match"] += 4

    if any(term in text for term in MISMATCH_HINTS):
        breakdown["role_penalty"] -= 40

    if company_priority == 1:
        breakdown["brand_bonus"] += 3
    elif company_priority == 2:
        breakdown["brand_bonus"] += 2

    total = sum(breakdown.values())
    explicit_entry_title = any(
        term in job.title.lower()
        for term in (
            "new grad",
            "new graduate",
            "recent graduate",
            "university graduate",
            "early career",
            "entry level",
            "entry-level",
        )
    )
    target_year_entry_title = str(profile.graduation_year) in job.title and any(
        term in job.title.lower() for term in ("associate", "software engineer", "software developer")
    )
    if not any(term in text for term in MISMATCH_HINTS):
        score_floor = 65 if explicit_entry_title else 60 if target_year_entry_title else 0
        if total < score_floor:
            breakdown["explicit_entry_floor"] += score_floor - total
            total = score_floor
    return max(0, min(100, total)), dict(breakdown)


def _difficulty_score(
    job: NormalizedJob,
    company_name: str,
    company_priority: int,
    matching_skills: list[str],
    missing_skills: list[str],
) -> tuple[int, dict[str, int]]:
    text = _text(job)
    breakdown = defaultdict(int)
    breakdown["baseline"] = 25

    if company_name in HIGH_BAR_COMPANIES:
        breakdown["company_bar"] += 28
    elif company_priority == 1:
        breakdown["company_bar"] += 14
    elif company_priority == 2:
        breakdown["company_bar"] += 9

    if any(term in text for term in ("distributed systems", "compiler", "security engineering", "graphics", "c++")):
        breakdown["niche_requirements"] += 12
    breakdown["missing_skills"] += min(20, len(missing_skills) * 4)

    if any(term in text for term in ("new grad", "entry level", "university graduate", "recent graduate")):
        breakdown["competition"] += 10
    if any(term in text for term in ("leetcode", "algorithm", "data structures", "system design")):
        breakdown["interview_bar"] += 8
    if any(term in text for term in ("undefined", "various teams", "multiple product areas")):
        breakdown["ambiguity"] += 5

    if len(matching_skills) >= 5:
        breakdown["match_discount"] -= 5

    total = sum(breakdown.values())
    return max(0, min(100, total)), dict(breakdown)


def recommend(fit_score: int, difficulty_score: int, text: str) -> Recommendation:
    """Map scores to an application recommendation."""

    if any(term in text for term in MISMATCH_HINTS):
        return Recommendation.SKIP
    if fit_score >= 80:
        return Recommendation.APPLY_NOW
    if fit_score >= 65:
        return Recommendation.APPLY_IF_INTERESTED
    if fit_score >= 45:
        return Recommendation.LOW_PRIORITY
    return Recommendation.SKIP


def build_heuristic_ranking(
    *,
    job: NormalizedJob,
    profile: CandidateProfile,
    company_priority: int,
) -> RankingResult:
    """Return a conservative heuristic ranking result."""

    matching_skills, missing_skills = extract_matching_skills(job, profile)
    fit_score, fit_breakdown = _fit_score(job, profile, company_priority)
    difficulty_score, difficulty_breakdown = _difficulty_score(
        job,
        job.company_name,
        company_priority,
        matching_skills,
        missing_skills,
    )
    text = _text(job)
    recommendation = recommend(fit_score, difficulty_score, text)
    tags = classify_tags(job)
    if company_priority == 1:
        tags.append("priority_company")
    if difficulty_score >= 70:
        tags.append("reach")
    tags = sorted(set(tags))
    _FIT_LABELS: dict[str, str] = {
        "role_match": "role type matches your target",
        "graduation_match": "explicitly targets new grads / class of 2027",
        "entry_level_signal": "entry-level signal present",
        "skill_overlap": "strong skill overlap",
        "product_profile": "product-focused engineering role",
        "experience_signal": "experience signals align",
        "location_match": "location matches your preference",
        "seniority_match": "no seniority red flags",
        "brand_bonus": "priority company",
        "explicit_entry_floor": "explicitly labeled as an entry-level role",
    }
    _DIFFICULTY_LABELS: dict[str, str] = {
        "baseline": "standard entry-level bar",
        "company_bar": "competitive / selective employer",
        "niche_requirements": "niche technical requirements",
        "missing_skills": "some skill gaps detected",
        "competition": "high expected applicant volume",
        "interview_bar": "rigorous technical interview signal",
        "ambiguity": "role scope is unclear",
    }
    positive_fit = [_FIT_LABELS.get(k, k) for k, v in fit_breakdown.items() if v > 0]
    fit_summary = (
        f"Fit {fit_score}/100 — {'; '.join(positive_fit)}." if positive_fit else f"Fit {fit_score}/100 — limited overlap with target profile."
    )
    positive_diff = [_DIFFICULTY_LABELS.get(k, k) for k, v in difficulty_breakdown.items() if v > 0]
    difficulty_summary = (
        f"Difficulty {difficulty_score}/100 — {'; '.join(positive_diff)}." if positive_diff else f"Difficulty {difficulty_score}/100 — standard entry-level expectations."
    )
    return RankingResult(
        fit_score=fit_score,
        difficulty_score=difficulty_score,
        recommendation=recommendation,
        fit_summary=fit_summary,
        difficulty_summary=difficulty_summary,
        top_matching_skills=matching_skills,
        missing_or_weaker_skills=missing_skills,
        tags=tags,
        scorer="heuristic",
        confidence=0.78,
    )
