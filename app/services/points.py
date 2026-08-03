"""Scoring rules for solved crackmes.

PROVISIONAL: the point system is still being designed (issue #127 lists first
blood on old crackmes, writeup points, author-funded bounties and decay-by-solve-
count as candidates). Only the base "solve an auto-validated crackme" award is
implemented so far, and the numbers here are expected to change.

Everything about the formula lives in this module so a later change is one edit.
Awards are snapshotted onto the solve record at solve time (see
:mod:`app.models.solve`), so tuning the formula re-prices future solves without
silently rewriting everyone's score history.
"""

# Points per difficulty level: a level 3 crackme is worth 300.
POINTS_PER_DIFFICULTY = 100

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 6


def solve_difficulty(crackme):
    """Return the difficulty level a solve of ``crackme`` is priced at.

    Prefers the ``official_difficulty`` a reviewer assigned when approving the
    crackme -- issue #127 wants that number fixed, immune to the community
    difficulty rating drifting after the fact. Crackmes approved before the
    reviewer form existed have no official difficulty, so those fall back to the
    community rating, rounded and clamped into the 1-6 scale.
    """
    official = crackme.get('official_difficulty')
    if official:
        return _clamp(int(official))

    return _clamp(round(crackme.get('difficulty') or 0))


def points_for_solve(crackme):
    """Return the points awarded for solving ``crackme``."""
    return solve_difficulty(crackme) * POINTS_PER_DIFFICULTY


def _clamp(difficulty):
    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, difficulty))
