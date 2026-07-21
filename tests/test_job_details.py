from newgrad_notifier.normalization.job_details import extract_job_details


def test_extract_job_details_surfaces_application_decision_fields():
    details = extract_job_details(
        title="Software Engineer, New Grad 2027",
        description=(
            "Hybrid role. Salary is $120,000 - $145,000 per year. We cannot provide visa sponsorship. "
            "Applicants must be a U.S. citizen and eligible for a security clearance. Apply by August 15, 2026. "
            "Candidates should graduate in 2027."
        ),
        location="New York, NY",
        is_remote=False,
    )

    assert details["salary"] == "$120,000 - $145,000 per year"
    assert details["work_mode"] == "Hybrid"
    assert details["sponsorship"] == "Not offered"
    assert details["citizenship"] == "U.S. citizenship required"
    assert details["clearance"] == "Must be eligible for clearance"
    assert details["graduation_years"] == ["2027"]
    assert details["application_deadline"] == "August 15, 2026"
