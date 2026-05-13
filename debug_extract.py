from app.semantic_segmentation import extract_candidate_values
text = "Lufthansa 238"
cands = extract_candidate_values(text)
for c in cands:
    print(f"'{c.raw}': {c.primary_type}")
