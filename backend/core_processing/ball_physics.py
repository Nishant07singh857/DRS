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
    best_i, best_y = None, -1
    for i in range(2, len(pts) - 2):
        y = pts[i][1]
        # Local maximum check
        if y > pts[i - 1][1] and y > pts[i - 2][1] and \
           y > pts[i + 1][1] and y > pts[i + 2][1]:
            if y > best_y:
                best_y, best_i = y, i
    return best_i


def estimate_speed(trajectory, fps=30, pixels_per_meter=None):
    """
    Ball ki average speed km/h me.
    pixels_per_meter: calibration — KITNA zaroori hai!
      - Broadcast side view (poori pitch ~1000px): ~50 px/m
      - Close-up view: zyada hoga
      - Stumps (0.711m) dikhe to: stump_height_px / 0.711
    None ho to 50 default (broadcast andaza).
    """
    if len(trajectory) < 2:
        return None
    if pixels_per_meter is None:
        pixels_per_meter = 50  # broadcast side-view andaza
    (x1, y1), (x2, y2) = trajectory[0], trajectory[-1]
    pixel_dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    meters = pixel_dist / pixels_per_meter
    seconds = (len(trajectory) - 1) / fps
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
    # Har point ka straight-line se deviation
    max_dev = 0.0
    dev_sign_sum = 0.0
    for i, (x, y) in enumerate(seg):
        t = i / (n - 1)
        # Straight line interpolation (x aur y dono me)
        # Deviation perpendicular direction me — yahan x me measure karte hain
        # kyunki side view me lateral movement x-deviation bankar dikhta hai
        expected_x = x0 + t * (x1 - x0)
        dev = x - expected_x
        if abs(dev) > abs(max_dev):
            max_dev = dev
        # Beech ke points ka sign (curve ki disha)
        if 0.25 < t < 0.75:
            dev_sign_sum += dev
    # Direction: beech me kis taraf curve hua
    thresh = frame_width * 0.008
    if max_dev > thresh:
        direction = 'in' if dev_sign_sum > 0 else 'out'
    elif max_dev < -thresh:
        direction = 'out' if dev_sign_sum > 0 else 'in'
    else:
        direction = 'straight'
        max_dev = 0.0
    # Sign normalize: positive = ek taraf
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

    # Length
    if bounce_norm is None:
        length = 'full'  # bina bounce — full toss / yorker
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


def analyze_delivery(trajectory, fps=30, pixels_per_meter=None, frame_width=None):
    """
    Poora delivery analysis — ek call me sab kuch.

    Returns dict:
    {
      'speed_kmh': float | None,
      'bounce_index': int | None,
      'bounce_norm': float | None,   # 0=bowler, 1=batsman
      'swing_px': float, 'swing_direction': str,
      'spin_px': float, 'spin_direction': str,
      'delivery_type': str, 'pace_desc': str,
    }
    """
    if not trajectory or len(trajectory) < 5:
        return None
    traj = [(float(p[0]), float(p[1])) for p in trajectory]
    fw = frame_width or 1280

    bounce_i = detect_bounce(traj)

    # Bounce normalize: trajectory ke x-range me bounce kahan
    xs = [p[0] for p in traj]
    x_min, x_max = min(xs), max(xs)
    x_range = max(1, x_max - x_min)
    bounce_norm = None
    if bounce_i is not None:
        bounce_norm = round((traj[bounce_i][0] - x_min) / x_range, 3)

    # Swing: shuru se bounce tak (ya aakhir tak agar bounce nahi)
    # Seedhi line se deviation = asli swing
    swing_end = bounce_i if bounce_i is not None else len(traj) - 1
    swing_px, swing_dir = measure_lateral(traj, 0, swing_end, fw)

    # Spin/seam: bounce se aakhir tak
    # Do tareeke: (1) segment ke andar curve, (2) bounce par angle change
    if bounce_i is not None and bounce_i < len(traj) - 2:
        spin_px, spin_dir = measure_lateral(traj, bounce_i, len(traj) - 1, fw)
        # Angle change at bounce — tez turn pakadne ke liye
        pre_angle = _segment_angle(traj, max(0, bounce_i - 5), bounce_i)
        post_angle = _segment_angle(traj, bounce_i, min(len(traj) - 1, bounce_i + 5))
        angle_change = abs(post_angle - pre_angle)
        # 8+ degree ka turn = significant spin/seam
        if angle_change > 8 and spin_px < fw * 0.01:
            # Angle se spin magnitude ka andaza
            spin_px = round(fw * 0.012 * (angle_change / 15), 1)
            # Direction: post-bounce x drift ki disha
            x_pre = traj[bounce_i][0] - traj[max(0, bounce_i - 3)][0]
            x_post = traj[min(len(traj)-1, bounce_i + 3)][0] - traj[bounce_i][0]
            # Agar post-bounce x-tezi badli to turn hua
            spin_dir = 'in' if x_post > x_pre * 1.3 else ('out' if x_post < x_pre * 0.7 else spin_dir)
    else:
        spin_px, spin_dir = 0.0, 'straight'

    speed = estimate_speed(traj, fps, pixels_per_meter)

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
    }
