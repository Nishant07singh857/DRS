"""
Ball physics & cricket intelligence — trajectory se delivery ka poora analysis.

YOLO ball ko DHOONDTA hai (har frame me kahan hai).
Ye module samajhta hai ball ne KIYA kya:
  - speed (km/h)
  - bounce point (kahan pitch hui)
  - swing (hawa me lateral movement, bounce se PEHLE)
  - seam/spin (bounce ke BAAD lateral movement)
  - delivery type (yorker, bouncer, outswinger, leg-spin...)

Input: trajectory = [(x, y), ...] pixels me, time-ordered.
Coordinate system: x right ki taraf, y NEECHE ki taraf (image coords).
Batsman right side me hai (x bada = batsman ki taraf).

Ye deterministic hai — same trajectory => same result.
"""

# --- Constants ---
# Standard cricket dimensions (meters)
STUMP_HEIGHT_M = 0.711  # 28 inches
PITCH_LENGTH_M = 20.12  # 22 yards

# Speed categories (km/h) — men's professional cricket
SPEED_EXPRESS = 140
SPEED_FAST = 130
SPEED_MEDIUM_FAST = 120
SPEED_MEDIUM = 110

# Lateral movement thresholds (fraction of frame width)
# Isse kam deviation = seedhi ball
SWING_THRESHOLD = 0.008
SPIN_THRESHOLD = 0.008


def _smooth(trajectory, window=3):
    """Chhoti noise hatane ke liye moving average."""
    if len(trajectory) <= window:
        return list(trajectory)
    out = []
    h = window // 2
    for i in range(len(trajectory)):
        lo, hi = max(0, i - h), min(len(trajectory), i + h + 1)
        xs = [p[0] for p in trajectory[lo:hi]]
        ys = [p[1] for p in trajectory[lo:hi]]
        out.append((sum(xs) / len(xs), sum(ys) / len(ys)))
    return out


def detect_bounce(trajectory):
    """
    Bounce ka frame dhoondo — jahan ball sabse neeche (y max) jaakar upar aati hai.
    Returns: bounce ka index, ya None (agar bounce nahi dikhi — full toss / yorker).
    """
    pts = _smooth(trajectory)
    if len(pts) < 5:
        return None
    # Vertical velocity ka sign change dhoondo (+ se -)
    # Pehle aadhe me max y dhoondo (bounce aam taur par beech me hoti hai)
    # CV-M11 (partial): plateau-tolerant — a flat-bottomed bounce (equal
    # neighbouring y) now counts. A bounce exactly at the trajectory edge
    # is still NOT claimed: the track end is indistinguishable from pad
    # impact there, so edge bounces remain deferred (see report).
    best_i, best_y = None, -1
    for i in range(2, len(pts) - 2):
        y = pts[i][1]
        # Local maximum check (plateau-tolerant)
        if y >= pts[i - 1][1] and y >= pts[i - 2][1] and \
           y >= pts[i + 1][1] and y >= pts[i + 2][1] and \
           (y > pts[i - 1][1] or y > pts[i + 1][1]):
            if y > best_y:
                best_y, best_i = y, i
    return best_i


def pixels_per_meter_from_stump_height(stump_height_px):
    """Calibrated scale: stump height in pixels / 0.711 m (CV-H7)."""
    if stump_height_px is None or stump_height_px <= 0:
        raise ValueError("stump_height_px must be > 0")
    return stump_height_px / STUMP_HEIGHT_M


def pixels_per_meter_from_pitch_length(pitch_length_px):
    """Calibrated scale: pitch length in pixels / 20.12 m (CV-H7)."""
    if pitch_length_px is None or pitch_length_px <= 0:
        raise ValueError("pitch_length_px must be > 0")
    return pitch_length_px / PITCH_LENGTH_M


def estimate_speed(trajectory, fps=30, pixels_per_meter=None,
                   stump_height_px=None, pitch_length_px=None):
    """
    Ball ki average speed km/h me, smoothed PATH LENGTH se (CV-H7).

    The old first-to-last chord under-measured curved/bouncing paths.
    Speed is now the smoothed polyline length over a known time base
    ((n-1)/fps seconds); fps is the EFFECTIVE fps of the sampled points,
    not the camera fps, when frames are skipped (see tasks.py, CV-C5).

    Calibration (CV-H7): pass a real pixels_per_meter, or derive it with
    stump_height_px / pitch_length_px. If none is given, 50 px/m
    (broadcast andaza) is still used BUT the caller must treat the result
    as uncalibrated — see analyze_delivery's 'speed_calibrated' flag.
    Never pass a silently guessed value as a calibrated measurement.

    CV-H8: fps <= 0 or pixels_per_meter <= 0 raises ValueError up front
    (the old code divided first and guarded afterwards, crashing with
    ZeroDivisionError, and a negative scale returned a negative speed).
    """
    if fps is None or fps <= 0:
        raise ValueError(f"fps must be > 0, got {fps!r}")
    if pixels_per_meter is not None and pixels_per_meter <= 0:
        raise ValueError(f"pixels_per_meter must be > 0, got {pixels_per_meter!r}")
    if stump_height_px is not None and stump_height_px <= 0:
        raise ValueError("stump_height_px must be > 0")
    if pitch_length_px is not None and pitch_length_px <= 0:
        raise ValueError("pitch_length_px must be > 0")
    if len(trajectory) < 2:
        return None
    if pixels_per_meter is None:
        if stump_height_px is not None:
            pixels_per_meter = pixels_per_meter_from_stump_height(stump_height_px)
        elif pitch_length_px is not None:
            pixels_per_meter = pixels_per_meter_from_pitch_length(pitch_length_px)
        else:
            pixels_per_meter = 50  # broadcast side-view andaza (uncalibrated)
    pts = _smooth([(float(p[0]), float(p[1])) for p in trajectory])
    pixel_dist = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        pixel_dist += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    meters = pixel_dist / pixels_per_meter
    seconds = (len(pts) - 1) / fps
    if seconds <= 0:
        return None
    return round(meters / seconds * 3.6, 1)


def _segment_angle(trajectory, start_idx, end_idx):
    """Segment ki overall disha (degrees me, x-axis se)."""
    if end_idx <= start_idx:
        return 0.0
    x0, y0 = trajectory[start_idx]
    x1, y1 = trajectory[end_idx]
    import math
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def measure_lateral(trajectory, start_idx, end_idx, frame_width):
    """
    Diye gaye segment me SEEDHI LINE SE deviation (swing/spin ka asli measure).
    Ball pitch ki taraf badhta hi hai — total x movement swing NAHI hai.
    Asli swing = straight path se kitna hata.

    Returns: (max_deviation_px, direction)
    direction: 'out' (expected se ek taraf), 'in' (doosri taraf), 'straight'
    """
    if end_idx <= start_idx or end_idx >= len(trajectory):
        return 0.0, 'straight'
    seg = trajectory[start_idx:end_idx + 1]
    n = len(seg)
    if n < 3:
        return 0.0, 'straight'
    x0, y0 = seg[0]
    x1, y1 = seg[-1]
    # CV-C3 + CV-H7: deviation is the SIGNED PERPENDICULAR distance from
    # the chord (start -> end), evaluated at each point's ARC-LENGTH
    # position along the segment — not at its time/index position.
    # The old code used t = i/(n-1) (time-uniform) and then decided
    # direction from a sign-sum that, for any consistent curve, shares
    # max_dev's sign — so both branches returned 'in' (+30px and -30px
    # curves both -> (30.0, 'in')). Direction is now max_dev's sign
    # alone: positive perpendicular deviation -> 'in', negative -> 'out'.
    # Arc-length parametrisation stops along-track speed variation
    # (acceleration, bounce slowdown) masquerading as lateral movement.
    import math
    chord_len = math.hypot(x1 - x0, y1 - y0)
    if chord_len < 1e-9:
        return 0.0, 'straight'
    # Cumulative path length up to each point
    cum = [0.0]
    for (xa, ya), (xb, yb) in zip(seg, seg[1:]):
        cum.append(cum[-1] + math.hypot(xb - xa, yb - ya))
    total = cum[-1] if cum[-1] > 1e-9 else 1.0
    # Unit chord direction and its perpendicular (signed cross product)
    ux, uy = (x1 - x0) / chord_len, (y1 - y0) / chord_len
    max_dev = 0.0
    for (x, y), s in zip(seg, cum):
        # Point on the chord at this arc-length fraction
        f = s / total
        cx, cy = x0 + f * (x1 - x0), y0 + f * (y1 - y0)
        # Signed perpendicular deviation: cross(chord_dir, point - chord_pt)
        dev = ux * (y - cy) - uy * (x - cx)
        # NOTE: sign convention — for a chord running left->right this is
        # the deviation's component perpendicular to travel; the sign is
        # what the direction label keys on, consistently for both signs.
        # To keep the historical 'in'/'out' mapping for the common
        # side-view case, flip so a curve bulging to one side is 'in'
        # and the mirrored curve is 'out' (see tests for both signs).
        dev = -dev
        if abs(dev) > abs(max_dev):
            max_dev = dev
    thresh = frame_width * 0.008
    if max_dev > thresh:
        direction = 'in'
    elif max_dev < -thresh:
        direction = 'out'
    else:
        direction = 'straight'
        max_dev = 0.0
    return round(abs(max_dev), 1), direction


def classify_delivery(speed_kmh, bounce_norm, swing_px, spin_px,
                       swing_dir, spin_dir, frame_width):
    """
    Delivery ka prakar batao.
    bounce_norm: 0.0 (bowler) se 1.0 (batsman) — bounce kahan hui
    Returns: (delivery_type, description)
    """
    swing_frac = abs(swing_px) / frame_width if frame_width else 0
    spin_frac = abs(spin_px) / frame_width if frame_width else 0
    has_swing = swing_frac > SWING_THRESHOLD
    has_spin = spin_frac > SPIN_THRESHOLD

    # Length (CV-M6: no-bounce is a genuine full toss, not 'full' —
    # the old code made the 'Full toss' branch below unreachable)
    if bounce_norm is None:
        length = 'full_toss'  # bina bounce — full toss
    elif bounce_norm < 0.35:
        length = 'short'
    elif bounce_norm < 0.62:
        length = 'good'
    elif bounce_norm < 0.85:
        length = 'full'
    else:
        length = 'yorker'

    # Speed category
    if speed_kmh is None:
        pace = 'unknown'
    elif speed_kmh >= SPEED_EXPRESS:
        pace = 'express'
    elif speed_kmh >= SPEED_FAST:
        pace = 'fast'
    elif speed_kmh >= SPEED_MEDIUM_FAST:
        pace = 'medium-fast'
    elif speed_kmh >= SPEED_MEDIUM:
        pace = 'medium'
    else:
        pace = 'slow'

    # Delivery type — pehle khaas cases
    parts = []
    if length == 'yorker':
        parts.append('Yorker')
    elif length == 'short' and (speed_kmh or 0) >= SPEED_FAST:
        parts.append('Bouncer')
    elif length == 'short':
        parts.append('Short ball')
    elif length == 'good':
        parts.append('Good length')
    elif length == 'full':
        parts.append('Fuller delivery')
    elif length == 'full_toss':
        parts.append('Full toss')
    else:
        parts.append('Full toss')

    # Movement
    if has_swing:
        parts.append('Outswinger' if swing_dir == 'out' else 'Inswinger')
    if has_spin:
        # Bounce ke baad movement = spin (slow) ya seam (fast)
        if (speed_kmh or 0) < SPEED_MEDIUM:
            parts.append('Leg-spin' if spin_dir == 'in' else 'Off-spin')
        else:
            parts.append('Seam movement')

    # Agar kuch khaas nahi to seedhi ball
    if len(parts) == 1 and parts[0] in ('Good length', 'Fuller delivery'):
        if not has_swing and not has_spin:
            parts.append('(straight)')

    delivery_type = ' + '.join(parts)
    desc = f"{pace} pace" if pace != 'unknown' else "pace unknown"
    if speed_kmh:
        desc += f" ({speed_kmh} km/h)"
    return delivery_type, desc


def analyze_delivery(trajectory, fps=30, pixels_per_meter=None, frame_width=None,
                     stump_height_px=None, pitch_length_px=None,
                     bowler_x=None, batsman_x=None):
    """
    Poora delivery analysis — ek call me sab kuch.

    CV-H8: frame_width=0 no longer silently maps to 1280 — a bad
    frame_width raises ValueError (None still means "unknown", 1280).
    CV-H7: pass stump_height_px or pitch_length_px (or pixels_per_meter)
    for a calibrated speed; otherwise 'speed_calibrated' is False and the
    speed is an uncalibrated broadcast-andaza figure. Pass bowler_x /
    batsman_x (calibrated pitch/stump coordinates) to normalise the bounce
    against pitch geometry instead of the tracked x-range; otherwise
    'bounce_calibrated' is False and a truncated trajectory shifts the
    length thresholds.

    Returns dict:
    {
      'speed_kmh': float | None,
      'bounce_index': int | None,
      'bounce_norm': float | None,   # 0=bowler, 1=batsman
      'swing_px': float, 'swing_direction': str,
      'spin_px': float, 'spin_direction': str,
      'delivery_type': str, 'pace_desc': str,
      'speed_calibrated': bool, 'bounce_calibrated': bool,
      'bounce_angle_change_deg': float,
    }
    """
    if not trajectory or len(trajectory) < 5:
        return None
    if frame_width is not None and frame_width <= 0:
        raise ValueError(f"frame_width must be > 0, got {frame_width!r}")
    traj = [(float(p[0]), float(p[1])) for p in trajectory]
    fw = frame_width if frame_width is not None else 1280

    bounce_i = detect_bounce(traj)

    # Bounce normalize (CV-H7): calibrated pitch geometry wins; the
    # tracked x-range fallback is kept only as an explicitly flagged
    # uncalibrated approximation.
    bounce_norm = None
    bounce_calibrated = False
    if bounce_i is not None:
        if bowler_x is not None and batsman_x is not None and batsman_x != bowler_x:
            bounce_norm = round(
                (traj[bounce_i][0] - bowler_x) / (batsman_x - bowler_x), 3)
            bounce_norm = max(0.0, min(1.0, bounce_norm))
            bounce_calibrated = True
        else:
            xs = [p[0] for p in traj]
            x_min, x_max = min(xs), max(xs)
            x_range = max(1, x_max - x_min)
            bounce_norm = round((traj[bounce_i][0] - x_min) / x_range, 3)

    # Swing: shuru se bounce tak (ya aakhir tak agar bounce nahi)
    swing_end = bounce_i if bounce_i is not None else len(traj) - 1
    swing_px, swing_dir = measure_lateral(traj, 0, swing_end, fw)

    # Spin/seam: bounce se aakhir tak — MEASURED deviation only (CV-M7).
    # The old code overwrote a small measured spin_px with a formula
    # derived from the bounce angle change, manufacturing spin from a
    # pad deflection or tracking glitch. Angle change is now reported
    # separately and never overwrites the measured deviation.
    angle_change = 0.0
    if bounce_i is not None and bounce_i < len(traj) - 2:
        spin_px, spin_dir = measure_lateral(traj, bounce_i, len(traj) - 1, fw)
        pre_angle = _segment_angle(traj, max(0, bounce_i - 5), bounce_i)
        post_angle = _segment_angle(traj, bounce_i, min(len(traj) - 1, bounce_i + 5))
        angle_change = round(abs(post_angle - pre_angle), 1)
    else:
        spin_px, spin_dir = 0.0, 'straight'

    speed_calibrated = (
        pixels_per_meter is not None
        or stump_height_px is not None
        or pitch_length_px is not None
    )
    speed = estimate_speed(traj, fps, pixels_per_meter,
                           stump_height_px=stump_height_px,
                           pitch_length_px=pitch_length_px)

    dtype, pdesc = classify_delivery(speed, bounce_norm, swing_px, spin_px,
                                      swing_dir, spin_dir, fw)

    return {
        'speed_kmh': speed,
        'bounce_index': bounce_i,
        'bounce_norm': bounce_norm,
        'swing_px': swing_px,
        'swing_direction': swing_dir,
        'spin_px': spin_px,
        'spin_direction': spin_dir,
        'delivery_type': dtype,
        'pace_desc': pdesc,
        'speed_calibrated': speed_calibrated,
        'bounce_calibrated': bounce_calibrated,
        'bounce_angle_change_deg': angle_change,
    }
