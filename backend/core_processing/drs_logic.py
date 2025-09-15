import random

def analyze_lbw_rules(tracking_data, frame_width):
    """
    ट्रैकिंग डेटा के आधार पर LBW के नियमों का विश्लेषण करता है।
    """
    ball_pos = tracking_data.get("ball")
    if not ball_pos:
        return None

    # स्क्रीन निर्देशांक के आधार पर ज़ोन परिभाषित करें
    stumps_zone = (frame_width * 0.4, frame_width * 0.6)
    pitch_outside_leg_zone = frame_width * 0.7  # दाएं हाथ के बल्लेबाज़ के लिए

    impact_x = ball_pos[0]
    
    # नियमों का अनुकरण करें
    is_pitch_in_line = impact_x < pitch_outside_leg_zone
    is_impact_in_line = stumps_zone[0] < impact_x < stumps_zone[1]
    is_hitting_wickets = is_impact_in_line and random.choice([True, True, False]) # थोड़ा रैंडमनेस

    confidence = 60 + random.uniform(0, 40)
    final_decision = "NOT OUT"

    if is_pitch_in_line and is_impact_in_line and is_hitting_wickets:
        if confidence > 75:
            final_decision = "OUT"
        elif confidence > 50:
            final_decision = "UMPIRE'S CALL"
        else:
            final_decision = "NOT OUT" # संदेह का लाभ
    
    return {
        "final_decision": final_decision,
        "confidence": round(confidence, 2),
        "pitch_in_line": is_pitch_in_line,
        "impact_in_line": is_impact_in_line,
        "hitting_wickets": is_hitting_wickets
    }
