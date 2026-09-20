import re
from dataclasses import dataclass

import httpx

_API = "https://explorers-rate-tables.bankrate.com/api/home-lending"
_TIMEOUT_S = 30
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Offer:
    lender: str
    rate: float
    apr: float
    points: float
    term: str

    def matches(self, text: str) -> bool:
        return lender_in(self.lender, text) and rate_in(self.rate, text)


def _params(
    loan_amount: int, property_value: int, credit_score: int, zip_code: str, points: str = "ZERO", term_ids=(2,)
) -> tuple[tuple[str, str], ...]:
    flat: list[tuple[str, str]] = [
        ("creditScore", str(credit_score)),
        ("debtToIncomeRatio", "0"),
        ("isCashOut", "false"),
        ("loanAmount", str(loan_amount)),
        ("mortgageBalance", str(loan_amount)),
        ("partnerId", "br3"),
        ("pointsRange", points),
        ("productCategories", "MORTGAGE_REFINANCE"),
        ("productFamilies", "CONVENTIONAL"),
        ("propertyType", "SINGLE_FAMILY"),
        ("propertyUse", "PRIMARY_RESIDENCE"),
        ("propertyValue", str(property_value)),
    ]
    flat += [("termIds", str(t)) for t in term_ids]
    flat.append(("zipCode", zip_code))
    return tuple(sorted(flat))


def fetch_offers(
    loan_amount: int, property_value: int, credit_score: int, zip_code: str, points: str = "ZERO"
) -> list[Offer]:
    response = httpx.get(
        _API,
        params=_params(loan_amount, property_value, credit_score, zip_code, points),
        headers={"Accept": "application/json", "User-Agent": _UA},
        timeout=_TIMEOUT_S,
        follow_redirects=True,
    )
    response.raise_for_status()
    return parse_offers(response.json())


def parse_offers(payload: dict) -> list[Offer]:
    data = payload.get("data") or {}
    institutions = data.get("institutions") or {}
    offers: list[Offer] = []
    for product in data.get("products") or []:
        offering = product.get("offering") or {}
        rate = offering.get("rate")
        if rate is None:
            continue
        lender = (institutions.get(str(product.get("institutionId"))) or {}).get("name") or ""
        offers.append(
            Offer(
                lender=lender,
                rate=float(rate),
                apr=float(offering.get("apr") or 0.0),
                points=float(offering.get("points") or 0.0),
                term=str(product.get("name") or ""),
            )
        )
    return sorted(offers, key=lambda o: (o.rate, o.apr))


def best_zero_point(offers: list[Offer]) -> Offer | None:
    zero = [o for o in offers if o.points == 0]
    return zero[0] if zero else None


def rate_in(rate: float, text: str) -> bool:
    return bool(re.search(rf"(?<![\d.]){re.escape(f'{rate:g}')}(?![\d])\s*%?", text or ""))


def lender_in(lender: str, text: str) -> bool:
    words = list(re.findall(r"[A-Za-z]{3,}", lender or ""))
    if not words:
        return False
    haystack = (text or "").lower()
    return all(w.lower() in haystack for w in words)
