"""
Camera Management — StreetDRS spec module E.

Multi-camera setup ke liye device registry:
- E1: Camera register karo (ID, position, role)
- E3: Live status (resolution, fps, connected)
- E5: Health monitoring (dropped frames, battery, storage)
- E7: Recording control
- E8: Failover (ek camera gaya to baki continue)
"""

from extensions import db
from datetime import datetime

CAMERA_ROLES = {'main', 'side', 'behind_wicket', 'wide_angle', 'overhead', 'mobile'}
CAMERA_STATUS = {'online', 'offline', 'recording', 'error', 'low_battery'}


class Camera(db.Model):
    __tablename__ = 'cameras'

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('venues.id'))
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'))

    name = db.Column(db.String(50), nullable=False)  # "Camera 1"
    role = db.Column(db.String(20), default='main')
    device_id = db.Column(db.String(100))  # phone ka unique ID

    # Config (E4)
    resolution = db.Column(db.String(20), default='1080p')
    fps = db.Column(db.Integer, default=60)

    # Health (E5)
    status = db.Column(db.String(20), default='offline')
    battery_pct = db.Column(db.Integer)
    storage_gb_free = db.Column(db.Float)
    dropped_frames = db.Column(db.Integer, default=0)
    last_heartbeat = db.Column(db.DateTime)

    # Calibration link (G)
    calibration_profile_id = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'role': self.role,
            'resolution': self.resolution, 'fps': self.fps,
            'status': self.status, 'battery_pct': self.battery_pct,
            'storage_gb_free': self.storage_gb_free,
            'dropped_frames': self.dropped_frames,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'is_healthy': self.status in ('online', 'recording') and (self.battery_pct or 100) > 20,
        }

    def heartbeat(self, battery=None, storage=None, dropped=0):
        """E5: Camera alive hai — health update karo."""
        self.last_heartbeat = datetime.utcnow()
        if battery is not None:
            self.battery_pct = battery
        if storage is not None:
            self.storage_gb_free = storage
        self.dropped_frames = (self.dropped_frames or 0) + dropped
        if self.status == 'offline':
            self.status = 'online'
