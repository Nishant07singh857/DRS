"""
DRS LBW decision logic — DETERMINISTIC.

Same input => same output, hamesha. Koi randomness nahi.
Ball trajectory ke aakhri points se linear extrapolation karke
"hitting wickets" ka andaza lagaya jata hai (Hawk-Eye jaisa simplified model).
"""


def _linearity(trajectory):
    """
    Aakhri points kitne seedhi line me hain — 0.0 (zigzag) se 1.0 (perfect line).
    R-squared jaisa simple measure.
    """
    pts = trajectory[-8:]
    if len(pts) < 3:
        return 0.5
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    var_x = sum((x - mx) ** 2 for x in xs)
    if var_x < 1e-9:
        return 0.5
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var_x
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    if ss_tot < 1e-9:
        return 1.0
    return max(0.0, min(1.0, 1 - ss_res / ss_tot))


def _predict_path(trajectory, stumps_zone, frame_width, max_steps=300):
    """
    Trajectory ke aakhri 2 points se direction nikaal kar ball ka rasta
    aage badhao. Returns: (hitting: bool, path: [[x, y], ...]).
    Path visualization ke liye chahiye hota hai.
    """
    if len(trajectory) < 2:
        return False, []
    (x1, y1), (x2, y2) = trajectory[-2], trajectory[-1]
    dx, dy = x2 - x1, y2 - y1
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return False, []
    # Direction normalize karo taaki step size stable rahe
    length = (dx ** 2 + dy ** 2) ** 0.5
    step_x, step_y = dx / length * 4.0, dy / length * 4.0
    px, py = float(x2), float(y2)
    path = []
    hitting = False
    for _ in range(max_steps):
        px += step_x
        py += step_y
        if not (0 < px < frame_width):
            break
        path.append([round(px, 1), round(py, 1)])
        if stumps_zone[0] < px < stumps_zone[1]:
            hitting = True
            break
    return hitting, path


def analyze_lbw_rules(tracking_data, frame_width, frame_height=None):
    """
    Tracking data ke aadhar par LBW rules ka deterministic analysis.

    tracking_data: {"ball": (x, y) | None, "trajectory": [(x, y), ...], ...}
    Returns: decision dict ya None (agar ball dikhi hi nahi).
    Dict me visualization ke liye coordinates bhi hote hain.
    """
    trajectory = tracking_data.get("trajectory") or []
    ball_pos = tracking_data.get("ball")

    if not ball_pos or len(trajectory) < 3:
        return None

    # Zones — frame ke relative. (Stump detection judne par ye calibrate honge.)
    stumps_zone = (frame_width * 0.4, frame_width * 0.6)
    pitch_outside_leg_x = frame_width * 0.7  # right-hand batsman ke liye

    pitch_point = trajectory[0]
    impact_x = ball_pos[0]

    is_pitch_in_line = pitch_point[0] < pitch_outside_leg_x
    is_impact_in_line = stumps_zone[0] < impact_x < stumps_zone[1]
    is_hitting_wickets, predicted_path = _predict_path(
        trajectory, stumps_zone, frame_width
    )
    is_hitting_wickets = is_impact_in_line and is_hitting_wickets

    # Confidence measurement quality se: trajectory jitni lambi aur seedhi,
    # faisla utna bharosemand.
    r2 = _linearity(trajectory)
    length_bonus = 10 if len(trajectory) >= 10 else (5 if len(trajectory) >= 5 else 0)
    confidence = round(min(97.0, 50.0 + 35.0 * r2 + length_bonus), 2)

    final_decision = "NOT OUT"
    if is_pitch_in_line and is_impact_in_line and is_hitting_wickets:
        if confidence > 75:
            final_decision = "OUT"
        elif confidence > 50:
            final_decision = "UMPIRE'S CALL"
        # else: shak ka fayda batsman ko => NOT OUT

    # Cricket intelligence: delivery ka physics analysis
    # (speed, swing, spin, bounce, delivery type)
    try:
        from core_processing.ball_physics import analyze_delivery as _analyze_delivery
        _delivery = _analyze_delivery(trajectory, fps=30, frame_width=frame_width)
    except Exception:
        _delivery = None

    return {
        "final_decision": final_decision,
        "confidence": confidence,
        "pitch_in_line": is_pitch_in_line,
        "impact_in_line": is_impact_in_line,
        "hitting_wickets": is_hitting_wickets,
        "trajectory_points": len(trajectory),
        # Visualization ke liye coordinates (frame pixels me)
        "frame_width": frame_width,
        "frame_height": frame_height,
        "pitch_point": [pitch_point[0], pitch_point[1]],
        "impact_point": [ball_pos[0], ball_pos[1]],
        "stumps_zone": [stumps_zone[0], stumps_zone[1]],
        "trajectory": [[p[0], p[1]] for p in trajectory[-30:]],
        "predicted_path": predicted_path,
        # Ball physics — speed, swing, spin, delivery type
        "delivery_analysis": _delivery,
    }
