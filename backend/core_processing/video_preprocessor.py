import cv2

def preprocess_for_ai(frame):
    """
    AI मॉडल को देने से पहले फ्रेम की गुणवत्ता में सुधार करता है।

    Args:
        frame: OpenCV BGR इमेज।

    Returns:
        संसाधित (Processed) BGR इमेज।
    """
    # 1. कंट्रास्ट को बढ़ाना (CLAHE) - यह खराब रोशनी में मदद करता है।
    # इमेज को LAB कलर स्पेस में बदलें ताकि केवल चमक (Luminance) पर काम किया जा सके।
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l_channel)
    
    merged_channels = cv2.merge((cl, a_channel, b_channel))
    processed_frame = cv2.cvtColor(merged_channels, cv2.COLOR_LAB2BGR)

    # 2. शोर कम करना (Denoising) - यह grainy वीडियो को साफ़ करता है।
    # processed_frame = cv2.fastNlMeansDenoisingColored(processed_frame, None, 10, 10, 7, 21)
    
    return processed_frame