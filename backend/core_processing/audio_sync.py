"""
Auto audio sync — multi-camera videos ko automatically sync karo.

Problem: 4-6 phones alag-alag time par recording shuru karte hain.
Solution: Audio me taali (clap) ki spike dhoondo — sab videos me
same taali same time par bajti hai!

Kaise kaam karta hai:
1. Har video se audio nikalo
2. Audio me sabse tez spike dhoondo (taali)
3. Sab videos ko us spike par align karo
4. Offset (seconds) return karo — video ko kitna aage/peeche karna hai

Usage:
    from core_processing.audio_sync import sync_videos
    offsets = sync_videos(['cam0.mp4', 'cam1.mp4', 'cam2.mp4', 'cam3.mp4'])
    # offsets = {'cam0.mp4': 0.0, 'cam1.mp4': 1.23, ...}
    # cam1 ko 1.23 sec peeche karna hai (ya cam0 ko aage)
"""

import subprocess
import numpy as np
import os
import tempfile


def extract_audio(video_path, sr=44100):
    """
    Video se mono audio nikalo (numpy array).
    Returns: (audio_array, sample_rate)
    """
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # ffmpeg se wav nikalo
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', video_path,
            '-ac', '1',  # mono
            '-ar', str(sr),  # sample rate
            '-f', 'wav',
            tmp_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        # wav padho (simple parser — 16-bit PCM)
        with open(tmp_path, 'rb') as f:
            data = f.read()

        # WAV header skip karo (44 bytes for standard PCM)
        # Pehle 'data' chunk dhoondo
        data_start = data.find(b'data')
        if data_start == -1:
            return None, sr
        data_start += 8  # 'data' + size

        audio = np.frombuffer(data[data_start:], dtype=np.int16).astype(np.float32)
        audio = audio / 32768.0  # normalize to [-1, 1]

        return audio, sr
    except Exception as e:
        print(f"Audio extract fail ({video_path}): {e}")
        return None, sr
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def find_clap(audio, sr, min_gap_sec=1.0):
    """
    Audio me sabse tez spike (taali) dhoondo.
    Returns: sample index ya None
    """
    if audio is None or len(audio) == 0:
        return None

    # Envelope: absolute value ka moving average
    window = int(sr * 0.01)  # 10ms window
    envelope = np.convolve(np.abs(audio),
                           np.ones(window)/window, mode='same')

    # Threshold: mean + 3*std (spike detection)
    threshold = np.mean(envelope) + 3 * np.std(envelope)

    # Threshold se upar wale regions dhoondo
    above = envelope > threshold
    if not np.any(above):
        return None

    # Pehla bada spike dhoondo
    # Groups banao
    indices = np.where(above)[0]
    if len(indices) == 0:
        return None

    # Sabse tez point
    peak_idx = indices[np.argmax(envelope[indices])]
    return int(peak_idx)


def sync_videos(video_paths, sr=44100):
    """
    Kai videos ko audio clap par sync karo.

    Returns: {video_path: offset_seconds}
    Pehle video ko reference (0.0) mano, baakiyon ka offset do.
    Positive offset = is video ko itne sec AAGE badhana hai (ya reference ko peeche)
    """
    if not video_paths:
        return {}

    print(f"Syncing {len(video_paths)} videos...")
    clap_times = {}

    for vp in video_paths:
        audio, rate = extract_audio(vp, sr)
        clap_sample = find_clap(audio, rate)
        if clap_sample is not None:
            clap_times[vp] = clap_sample / rate
            print(f"  {os.path.basename(vp)}: clap at {clap_times[vp]:.2f}s")
        else:
            print(f"  {os.path.basename(vp)}: NO CLAP FOUND!")

    if not clap_times:
        print("Kisi me clap nahi mila — manual sync karna padega.")
        return {vp: 0.0 for vp in video_paths}

    # Pehle video ko reference banao
    ref = video_paths[0]
    ref_time = clap_times.get(ref, 0)

    offsets = {}
    for vp in video_paths:
        if vp in clap_times:
            # Is video ka clap ref se kitna late/early hai
            offsets[vp] = clap_times[vp] - ref_time
        else:
            offsets[vp] = 0.0  # sync nahi ho paya

    return offsets


def apply_offset_info(offsets):
    """
    Offsets ko human-readable banao.
    """
    lines = ["Video Sync Offsets:"]
    for vp, off in offsets.items():
        name = os.path.basename(vp)
        if off > 0:
            lines.append(f"  {name}: {off:.2f}s LATE — {off:.2f}s trim karo shuru se")
        elif off < 0:
            lines.append(f"  {name}: {abs(off):.2f}s EARLY — reference ko trim karo")
        else:
            lines.append(f"  {name}: synced (reference)")
    return "\n".join(lines)
