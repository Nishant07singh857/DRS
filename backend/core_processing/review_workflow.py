"""
Umpire Control Center — Review workflow (StreetDRS spec module N).

Workflow (jaise ICC me hota hai):
1. On-field umpire review request karta hai → status='pending'
2. System process karta hai → status='processing'
3. AI recommendation aati hai → status='completed' (ya 'inconclusive')
4. Third umpire confirm karta hai → accept/reject/override → locked!

States: pending → processing → completed/failed/inconclusive → confirmed (locked)
"""

from extensions import db
from datetime import datetime

# Review types (N2)
REVIEW_TYPES = {'LBW', 'EDGE', 'RUNOUT', 'STUMPING', 'WIDE', 'NOBALL', 'BOUNDARY'}

# Queue states (N3)
REVIEW_STATES = {'pending', 'processing', 'completed', 'failed',
                 'inconclusive', 'confirmed'}

# Decisions
DECISIONS = {'OUT', 'NOT OUT', 'INCONCLUSIVE'}


class ReviewWorkflow:
    """
    Review state machine — galat transition reject karta hai.
    (Pure Python — testing easy, DB independent)
    """

    # Allowed transitions
    TRANSITIONS = {
        'pending': {'processing', 'failed'},
        'processing': {'completed', 'failed', 'inconclusive'},
        'completed': {'confirmed', 'inconclusive'},
        'inconclusive': {'confirmed'},  # human phir bhi decide kar sakta hai
        'failed': {'pending'},  # retry!
        'confirmed': set(),  # locked — koi transition nahi!
    }

    @classmethod
    def can_transition(cls, from_state, to_state):
        return to_state in cls.TRANSITIONS.get(from_state, set())

    @classmethod
    def transition(cls, review, to_state):
        """Review ka state change karo. Galat ho to error."""
        if not cls.can_transition(review.status, to_state):
            raise ValueError(
                f"Invalid transition: {review.status} → {to_state}. "
                f"Allowed: {cls.TRANSITIONS.get(review.status)}"
            )
        review.status = to_state
        review.updated_at = datetime.utcnow()
        return review


def validate_review_request(review_type, original_call=None):
    """Review request validate karo."""
    if review_type not in REVIEW_TYPES:
        raise ValueError(
            f"Invalid review type: {review_type}. "
            f"Valid: {sorted(REVIEW_TYPES)}"
        )
    if original_call and original_call not in {'OUT', 'NOT OUT'}:
        raise ValueError(f"Invalid original call: {original_call}")
    return True
