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
    # Phase 1 (SEC-C3): creator/owner — see match.Team.user_id note.
    # CalibrationProfile is owned via its camera.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
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

    # One-to-one: har camera ka apna calibration profile (spec G)
    calibration_profile = db.relationship(
        'CalibrationProfile', back_populates='camera',
        uselist=False, cascade='all, delete-orphan')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        d = {
            'id': self.id, 'name': self.name, 'role': self.role,
            'resolution': self.resolution, 'fps': self.fps,
            'status': self.status, 'battery_pct': self.battery_pct,
            'storage_gb_free': self.storage_gb_free,
            'dropped_frames': self.dropped_frames,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'is_healthy': self.status in ('online', 'recording') and (self.battery_pct or 100) > 20,
        }
        prof = self.calibration_profile
        d['calibrated'] = bool(prof and prof.is_calibrated)
        d['reprojection_error'] = prof.reprojection_error if prof else None
        return d

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


class CalibrationProfile(db.Model):
    """
    Spec G: Camera calibration data.

    Har camera ka intrinsic (lens) + extrinsic (pose) calibration
    yahan JSON me store hota hai. DLT solve se projection matrix
    nikalti hai — wahi multi_camera_fusion / triangulation use karta hai.
    """
    __tablename__ = 'calibration_profiles'

    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'),
                          unique=True, nullable=False)
    camera = db.relationship('Camera', back_populates='calibration_profile')

    # Sab kuch ek JSON me: intrinsics, extrinsics, correspondences,
    # projection_matrix — taaki API flexible rahe
    data = db.Column(db.JSON, default=dict)

    reprojection_error = db.Column(db.Float)  # pixels (mean)
    is_calibrated = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def to_dict(self):
        d = self.data or {}
        return {
            'id': self.id,
            'camera_id': self.camera_id,
            'calibrated': self.is_calibrated,
            'is_calibrated': self.is_calibrated,  # alias
            'reprojection_error': self.reprojection_error,
            'has_intrinsics': 'intrinsics' in d,
            'has_extrinsics': 'extrinsics' in d,
            'n_correspondences': len((d.get('correspondences') or {}).get('image_points') or []),
            'intrinsics': d.get('intrinsics'),
            'extrinsics': d.get('extrinsics'),
            'projection_matrix': d.get('projection_matrix'),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
