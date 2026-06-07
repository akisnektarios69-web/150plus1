"""Greek electoral law — reinforced proportional representation (ενισχυμένη αναλογική).

Rules applied since the June 2023 election:
  * 3% national threshold to win seats.
  * First party < 25%  -> all 300 seats allocated purely proportionally.
  * First party >= 25%  -> bonus = 20 seats, +1 per 0.5 point above 25%,
    capped at 50 seats (reached at 40%).
  * Remaining (300 - bonus) seats are distributed among parties above the
    threshold using the largest-remainder (Hare) method.

`shares` is a list of percentages aligned to config.PARTIES order.
Returns (seats list, first_party_index, bonus).
"""
from config import SEATS, THRESHOLD


def first_party_bonus(pct: float) -> int:
    if pct < 25:
        return 0
    return min(50, 20 + int((pct - 25) // 0.5))


def allocate(shares):
    n = len(shares)
    seats = [0] * n
    eligible = [(i, p) for i, p in enumerate(shares) if p >= THRESHOLD]
    if not eligible:
        return seats, 0, 0

    sum_elig = sum(p for _, p in eligible)
    first_i, first_p = max(eligible, key=lambda o: o[1])
    bonus = first_party_bonus(first_p)
    remaining = SEATS - bonus

    quotas = [(i, remaining * p / sum_elig) for i, p in eligible]
    rema = []
    allocated = 0
    for i, q in quotas:
        base = int(q)
        seats[i] = base
        allocated += base
        rema.append((i, q - base))

    left = remaining - allocated
    rema.sort(key=lambda o: o[1], reverse=True)
    for k in range(left):
        seats[rema[k][0]] += 1

    seats[first_i] += bonus
    return seats, first_i, bonus
