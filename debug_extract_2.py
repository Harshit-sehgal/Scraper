from app.semantic_segmentation import extract_candidate_values
text = "Lufthansa 238"
cands = extract_candidate_values(text)
print("Before filtering:")
for c in cands:
    print(f"'{c.raw}': {c.primary_type}")

# The logic I added:
cands = sorted(cands, key=lambda x: len(x.raw), reverse=True)
unique_cands = []
for c in cands:
    is_sub = False
    for other in unique_cands:
        if c.raw in other.raw and c.raw != other.raw:
            is_sub = True
            break
    if not is_sub:
        unique_cands.append(c)
cands = unique_cands

print("\nAfter filtering (current logic):")
for c in cands:
    print(f"'{c.raw}': {c.primary_type}")

# Proposed logic: prefer non-TEXT types for same/overlapping span
print("\nProposed logic (prefer specific types):")
cands = extract_candidate_values(text)
# For each raw string, if there are multiple candidates, prefer non-TEXT ones
best_cands = {}
for c in cands:
    if c.raw not in best_cands or (best_cands[c.raw].primary_type.value == 'text' and c.primary_type.value != 'text'):
        best_cands[c.raw] = c

# Now handle substring overlaps: if a shorter string has a specific type, 
# and a longer string containing it is just 'TEXT', prefer the specific ones.
# Actually, the best is to just remove the 'text' candidate if other more specific candidates exist.
final = []
has_specific = any(c.primary_type.value != 'text' for c in cands)
for c in cands:
    if has_specific and c.primary_type.value == 'text' and len(cands) > 1:
        continue
    final.append(c)

for c in final:
    print(f"'{c.raw}': {c.primary_type}")
