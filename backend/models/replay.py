"""
Replay Library — StreetDRS spec module O (poora karo).

O5. Event bookmarks: bounce, edge, impact, wicket
O8. Highlight generation: boundaries, wickets, close calls
O11. Replay library: search by match/player/over/event
"""

from extensions import db
from datetime import datetime

BOOKMARK_TYPES = {'bounce', 'edge', 'impact', 'wicket', 'appeal',
                  'boundary', 'six', 'milestone', 'custom'}


class Bookmark(db.Model):
    """O5: Video me event markers."""
    __tablename__ = 'bookmarks'

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'))
    delivery_id = db.Column(db.Integer, db.ForeignKey('deliveries.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    bookmark_type = db.Column(db.String(20), nullable=False)
    timestamp_s = db.Column(db.Float, nullable=False)  # video me time
    frame_number = db.Column(db.Integer)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'))
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'match_id': self.match_id,
            'bookmark_type': self.bookmark_type,
            'timestamp_s': self.timestamp_s,
            'frame_number': self.frame_number,
            'note': self.note,
        }


class Highlight(db.Model):
    """O8: Auto/manual highlight clips."""
    __tablename__ = 'highlights'

    id = db.Column(db.Integer, primary_key=True)
    # Phase 1 (SEC-C3): set at generation time from the match owner.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'))
    title = db.Column(db.String(200), nullable=False)

    # Clip boundaries
    start_s = db.Column(db.Float, nullable=False)
    end_s = db.Column(db.Float, nullable=False)
    event_type = db.Column(db.String(20))  # wicket/boundary/review/six

    # Source
    source_video = db.Column(db.String(255))
    clip_path = db.Column(db.String(255))  # trimmed clip ka path
    auto_generated = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title,
            'start_s': self.start_s, 'end_s': self.end_s,
            'event_type': self.event_type,
            'duration_s': round(self.end_s - self.start_s, 1),
            'auto_generated': self.auto_generated,
        }


def auto_highlights(match_id, deliveries):
    """
    O8: Deliveries se auto highlights banao.
    Wickets, boundaries, 6s → highlight clips.
    deliveries: list of Delivery.to_dict()
    Returns: list of Highlight (unsaved — caller saves)
    """
    highlights = []
    for d in deliveries:
        hl = None
        ts = d.get('ball_number', 0) * 30  # approx: 30s per ball
        over = d.get('over_number', 0)

        if d.get('is_wicket'):
            hl = Highlight(
                match_id=match_id,
                title=f"WICKET! Over {over} — {d.get('wicket_type', '')}",
                start_s=max(0, ts - 10), end_s=ts + 10,
                event_type='wicket', auto_generated=True,
            )
        elif d.get('runs_off_bat') == 6:
            hl = Highlight(
                match_id=match_id,
                title=f"SIX! Over {over}",
                start_s=max(0, ts - 8), end_s=ts + 12,
                event_type='six', auto_generated=True,
            )
        elif d.get('runs_off_bat') == 4:
            hl = Highlight(
                match_id=match_id,
                title=f"FOUR! Over {over}",
                start_s=max(0, ts - 8), end_s=ts + 10,
                event_type='boundary', auto_generated=True,
            )

        if hl:
            highlights.append(hl)

    return highlights
