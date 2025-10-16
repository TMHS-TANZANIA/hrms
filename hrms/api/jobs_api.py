import frappe

@frappe.whitelist(allow_guest=True)
def get_published_jobs():
    """
    Returns all published and open job openings for public display (e.g. WordPress site)
    """
    jobs = frappe.get_all(
        "Job Opening",
        filters={"publish": 1, "status": "Open"},
        fields=[
            "name",
            "job_title",
            "department",
            "designation",
            "employment_type",
            "location",
            "description",
            "route",
            "company",
            "currency",
            "lower_range",
            "upper_range",
            "salary_per",
            "posted_on",
            "closes_on",
            "publish_salary_range"
        ],
        order_by="posted_on desc"
    )
    return jobs
