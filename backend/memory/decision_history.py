"""Decision history view (F46): chains of decisions linked by `supersedes`."""
from __future__ import annotations

from backend.models import Decision


def decision_chains(decisions: list[Decision]) -> list[list[Decision]]:
    by_id = {d.decision_id: d for d in decisions}
    chains = []
    for d in decisions:
        if d.supersedes:  # not a chain head
            continue
        chain = [d]
        cur = d
        while cur.superseded_by and cur.superseded_by in by_id:
            cur = by_id[cur.superseded_by]
            chain.append(cur)
        chains.append(chain)
    return chains


def current_decisions(decisions: list[Decision]) -> list[Decision]:
    return [d for d in decisions if d.status in ("confirmed", "uncertain")]
