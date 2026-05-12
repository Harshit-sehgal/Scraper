import json
import csv

INPUT_FILE = "/home/harshit/Documents/Work/Money/scraper/chennai_leads.json"
OUTPUT_FILE = "/home/harshit/Documents/Work/Money/scraper/chennai_interior_designers.csv"


def clean_phone(p):
    if not p:
        return ""
    p = str(p).strip()
    if len(p) > 30 and sum(c.isdigit() for c in p) < 7:
        return ""
    if p.lower() in ("offers", "company", "gallery", "testimonials", "blogs", "contact"):
        return ""
    return p


def clean_leads(input_file=INPUT_FILE, output_file=OUTPUT_FILE):
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        valid_leads = []
        seen_names = set()

        for item in data:
            name = (item.get("company_name") or "").strip()
            if not name or name in seen_names or "File not found" in name or "Copyright" in name or len(name) < 3:
                continue

            phone = clean_phone(item.get("contact_phone", ""))
            email = (item.get("email") or "").strip()
            address = (item.get("address") or "").strip()

            if phone or (email and len(email) < 50 and "@" in email):
                seen_names.add(name)
                valid_leads.append({
                    "company_name": name,
                    "phone": phone,
                    "email": email if "@" in email else "",
                    "address_or_location": address[:100] + "..." if len(address) > 100 else address
                })

        valid_leads.sort(key=lambda x: (bool(x["phone"]), x["company_name"]), reverse=True)

        fieldnames = ["company_name", "phone", "email", "address_or_location"]
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in valid_leads:
                writer.writerow({k: row.get(k, "") for k in fieldnames})

        print(f"Cleaned JSON into CSV! Found {len(valid_leads)} high-quality leads.")
    except Exception as e:
        print(f"Error processing keys: {e}")


if __name__ == "__main__":
    clean_leads()
