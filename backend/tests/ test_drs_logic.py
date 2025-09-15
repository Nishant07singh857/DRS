import numpy as np

def check_impact(ball_pos, pad_pos):
    """
    जाँचता है कि बॉल और पैड के बीच इम्पैक्ट हुआ है या नहीं।
    """
    if ball_pos is None or pad_pos is None:
        return False
    
    distance = np.sqrt((ball_pos[0] - pad_pos[0])**2 + (ball_pos[1] - pad_pos[1])**2)
    
    # दूरी की सीमा को आपकी वीडियो के रिज़ॉल्यूशन के अनुसार समायोजित करें
    IMPACT_THRESHOLD = 50 
    return distance < IMPACT_THRESHOLD


def analyze_lbw_decision(trajectory, impact_point, frame_width):
    """
    ट्रैजेक्टरी और इम्पैक्ट पॉइंट के आधार पर LBW का अंतिम निर्णय लेता है।
    """
    if not trajectory or len(trajectory) < 3:
        return {"final_decision": "NOT DETERMINED", "reason": "Insufficient trajectory data"}

    # 1. पिचिंग पॉइंट का पता लगाएँ (ट्रैजेक्टरी का पहला बिंदु)
    pitch_point = trajectory[0]

    # 2. इम्पैक्ट पॉइंट
    impact_x = impact_point[0]
    
    # स्क्रीन पर क्रिकेट के नियमों के ज़ोन को परिभाषित करें
    stumps_zone_x = (frame_width * 0.4, frame_width * 0.6)
    pitch_outside_leg_x = frame_width * 0.7  # दाएं हाथ के बल्लेबाज़ के लिए

    # नियम लागू करें
    is_pitch_in_line = pitch_point[0] < pitch_outside_leg_x
    is_impact_in_line = stumps_zone_x[0] < impact_x < stumps_zone_x[1]

    # 3. विकेट्स से टकराने का अनुमान (सरलीकृत रैखिक एक्सट्रपलेशन)
    # ट्रैजेक्टरी के अंतिम कुछ बिंदुओं के आधार पर भविष्य के पथ का अनुमान लगाएँ
    last_points = trajectory[-3:]
    dx = last_points[-1][0] - last_points[0][0]
    dy = last_points[-1][1] - last_points[0][1]
    
    is_hitting_wickets = False
    if abs(dx) > 1: # अगर बॉल सीधी चल रही है
        slope = dy / dx
        # मान लीजिए स्टंप्स y=450 पर हैं
        stump_y = 450
        predicted_x_at_stumps = impact_point[0] + (stump_y - impact_point[1]) / slope
        if stumps_zone_x[0] < predicted_x_at_stumps < stumps_zone_x[1]:
            is_hitting_wickets = True
    
    # आत्मविश्वास और अंतिम निर्णय
    confidence = 75.0 # बेस कॉन्फिडेंस
    final_decision = "NOT OUT"
    
    if is_pitch_in_line and is_impact_in_line and is_hitting_wickets:
        final_decision = "OUT"
    elif not is_pitch_in_line:
        confidence = 100.0 # निश्चित रूप से नॉट आउट
    
    return {
        "final_decision": final_decision,
        "confidence": confidence,
        "pitch_in_line": is_pitch_in_line,
        "impact_in_line": is_impact_in_line,
        "hitting_wickets": is_hitting_wickets
    }