"""
URL Classifier Utility — Categorizes URLs into functional domain types for evidence verification:
- CODE_REPOSITORY: GitHub, GitLab, Bitbucket
- CERTIFICATE_CREDENTIAL: Credly, Coursera, Udemy, AWS, edX, Google Cloud
- DESIGN_PORTFOLIO: Behance, Dribbble, Figma, Notion, Medium, Substack, Personal domains
- COMPETITIVE_DATA: Kaggle, LeetCode, CodeChef, Codeforces, HackerRank
- PROFESSIONAL_SOCIAL: LinkedIn, Google Scholar, ResearchGate
- GENERIC_WEBSITE: Any other valid HTTP/HTTPS link
"""

from urllib.parse import urlparse


def classify_url(url: str) -> str:
    """
    Categorizes an evidence URL based on hostname and path structure.
    Returns domain type string.
    """
    if not url:
        return "GENERIC_WEBSITE"

    url_clean = url.strip().lower()
    if not (url_clean.startswith("http://") or url_clean.startswith("https://")):
        url_clean = "https://" + url_clean

    try:
        parsed = urlparse(url_clean)
        hostname = parsed.netloc.lower()
    except Exception:
        return "GENERIC_WEBSITE"

    # 1. Code Repositories
    if any(domain in hostname for domain in ["github.com", "gitlab.com", "bitbucket.org", "sourceforge.net"]):
        return "CODE_REPOSITORY"

    # 2. Certificates & Credentials
    if any(domain in hostname for domain in ["credly.com", "coursera.org", "udemy.com", "edx.org", "aws.amazon.com", "cloud.google.com", "pluralsight.com"]):
        return "CERTIFICATE_CREDENTIAL"

    # 3. Competitive Data & Coding Platforms
    if any(domain in hostname for domain in ["kaggle.com", "leetcode.com", "codeforces.com", "codechef.com", "hackerrank.com", "topcoder.com"]):
        return "COMPETITIVE_DATA"

    # 4. Design & Creative Portfolios
    if any(domain in hostname for domain in ["behance.net", "dribbble.com", "figma.com", "notion.site", "medium.com", "substack.com", "hashnode.dev", "dev.to"]):
        return "DESIGN_PORTFOLIO"

    # 5. Professional Social & Academic
    if any(domain in hostname for domain in ["linkedin.com", "scholar.google.com", "researchgate.net"]):
        return "PROFESSIONAL_SOCIAL"

    # Default for custom personal domains (e.g. devanshu.dev, myportfolio.com)
    return "DESIGN_PORTFOLIO" if any(kw in hostname for kw in ["portfolio", "dev", "io", "me", "site"]) else "GENERIC_WEBSITE"
