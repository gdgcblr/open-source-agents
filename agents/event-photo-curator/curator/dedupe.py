"""Connected perceptual-hash groups, used as diversity hints, never hard rejection."""
from .loader import Photo


def group_duplicates(photos: list[Photo], distance: int) -> int:
    valid = [p for p in photos if p.phash is not None]
    parents = list(range(len(valid)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    # shortcut: pairwise O(n²) comparisons, use a hash index for very large events.
    for i, photo in enumerate(valid):
        for j in range(i):
            if photo.phash - valid[j].phash <= distance:
                parents[root(i)] = root(j)
    groups = {}
    for i, photo in enumerate(valid):
        groups.setdefault(root(i), []).append(photo)
    duplicates = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        group = f'burst-{members[0].path.name}'
        duplicates += len(members) - 1
        for photo in members:
            photo.duplicate_group = group
    return duplicates


def select_diverse(photos: list[Photo], top: int) -> list[Photo]:
    """Prioritize different groups, then fill available slots by AI score."""
    ranked = sorted((p for p in photos if p.assessment),
                    key=lambda p: (-p.assessment['score'], -p.sharpness, p.path.name))
    selected, deferred, seen = [], [], set()
    for photo in ranked:
        group = photo.duplicate_group or photo.digest
        if group in seen:
            deferred.append(photo)
        else:
            selected.append(photo)
            seen.add(group)
    return (selected[:top] + deferred[:max(0, top - len(selected))])[:top]
