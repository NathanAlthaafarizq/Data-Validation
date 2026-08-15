import csv
import io
from datetime import datetime

VALID_STATUSES = {"completed", "pending", "cancelled", "refunded"}
SUSPICIOUS_KEYWORDS = ["drop table", "delete from", "--", ";", "<script"]


def load_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def parse_date(date_str):
    """Try to parse an ISO-ish date string. Returns datetime or None."""
    if not date_str:
        return None
    cleaned = date_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def check_suspicious(text):
    if not text:
        return False
    lowered = text.lower()
    return any(kw in lowered for kw in SUSPICIOUS_KEYWORDS)


def validate_users(rows):
    """Returns dict: {row_id: {"errors": [...], "warnings": [...]}}"""
    results = {}
    seen_ids = set()
    duplicate_check = {}

    for row in rows:
        errors = []
        warnings = []
        row_id = row.get("id", "?")

        if row_id in seen_ids:
            errors.append(f"duplicate id ({row_id})")
        seen_ids.add(row_id)

        name = row.get("name", "")
        if name is None or name.strip() == "":
            errors.append("name is empty or whitespace-only")
        elif check_suspicious(name):
            warnings.append(f"name contains suspicious content ({name!r})")

        email = row.get("email", "")
        if not email or "@" not in email or "." not in email.split("@")[-1]:
            errors.append(f"invalid or missing email ({email!r})")

        age_raw = row.get("age", "")
        if age_raw is None or age_raw.strip() == "":
            errors.append("age is missing")
        else:
            try:
                age = int(age_raw)
                if age < 0:
                    errors.append(f"age is negative ({age})")
                elif age > 120:
                    errors.append(f"age is an unrealistic outlier ({age})")
            except ValueError:
                errors.append(f"age is not a valid integer ({age_raw!r})")

        created_at = row.get("created_at", "")
        parsed = parse_date(created_at)
        if created_at and parsed is None:
            errors.append(f"created_at is not a valid date ({created_at!r})")
        elif parsed:
            if parsed.year < 2000:
                warnings.append(f"created_at looks suspiciously old ({created_at})")
            elif parsed > datetime.now(parsed.tzinfo):
                warnings.append(f"created_at is in the future ({created_at})")

        key = (name.strip().lower() if name else "", email.strip().lower() if email else "")
        if key in duplicate_check and key != ("", ""):
            warnings.append(f"duplicate name+email as row {duplicate_check[key]}")
        else:
            duplicate_check[key] = row_id

        results[row_id] = {"errors": errors, "warnings": warnings}

    return results


def validate_orders(rows, valid_user_ids):
    results = {}

    for row in rows:
        errors = []
        warnings = []
        row_id = row.get("id", "?")

        user_id = row.get("user_id", "")
        if user_id not in valid_user_ids:
            errors.append(f"orphaned foreign key: user_id {user_id!r} not found in users")

        product = row.get("product_name", "")
        if not product or product.strip() == "":
            errors.append("product_name is empty")
        elif check_suspicious(product):
            warnings.append(f"product_name contains suspicious content ({product!r})")

        qty_raw = row.get("quantity", "")
        try:
            qty = int(qty_raw)
            if qty < 0:
                errors.append(f"quantity is negative ({qty})")
            elif qty == 0:
                warnings.append("quantity is zero")
        except ValueError:
            errors.append(f"quantity is not a valid integer ({qty_raw!r})")

        price_raw = row.get("price", "")
        try:
            price = float(price_raw)
            if price < 0:
                errors.append(f"price is negative ({price})")
        except ValueError:
            errors.append(f"price is not a valid number ({price_raw!r})")

        status = row.get("status", "")
        if not status or status.strip() == "":
            errors.append("status is empty")
        elif status not in VALID_STATUSES:
            errors.append(f"status is not a recognized value ({status!r})")

        order_date = row.get("order_date", "")
        parsed = parse_date(order_date)
        if order_date and parsed is None:
            errors.append(f"order_date is not a valid date ({order_date!r})")
        elif parsed:
            if parsed.year < 2000:
                warnings.append(f"order_date looks suspiciously old ({order_date})")
            elif parsed > datetime.now(parsed.tzinfo):
                warnings.append(f"order_date is in the future ({order_date})")

        results[row_id] = {"errors": errors, "warnings": warnings}

    return results


def print_report(title, results):
    total = len(results)
    clean = sum(1 for r in results.values() if not r["errors"] and not r["warnings"])
    with_errors = sum(1 for r in results.values() if r["errors"])
    with_warnings_only = sum(1 for r in results.values() if r["warnings"] and not r["errors"])

    print(f"\n=== {title} ===")
    print(f"Total: {total}  |  Clean: {clean}  |  Errors: {with_errors}  |  Warnings only: {with_warnings_only}")

    for row_id, r in results.items():
        if r["errors"] or r["warnings"]:
            print(f"  Row {row_id}:")
            for e in r["errors"]:
                print(f"    [ERROR]   {e}")
            for w in r["warnings"]:
                print(f"    [WARNING] {w}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3:
        # Real usage: python validator.py users.csv orders.csv
        with open(sys.argv[1], encoding="utf-8") as f:
            users = load_csv(f.read())
        with open(sys.argv[2], encoding="utf-8") as f:
            orders = load_csv(f.read())
    else:
        print("Usage: python validator.py <users.csv> <orders.csv>")
        print("No files given — running with no data.")
        users, orders = [], []

    user_results = validate_users(users)
    print_report("Users Validation", user_results)

    valid_user_ids = {u["id"] for u in users}
    order_results = validate_orders(orders, valid_user_ids)
    print_report("Orders Validation", order_results)