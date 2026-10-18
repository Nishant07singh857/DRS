"""
UltraEdge-style Audio Analysis — StreetDRS spec module L.

Stump mic se bat-ball contact detect karo:
1. Audio me transient spikes dhoondo (L6)
2. Har spike ko classify karo: bat-ball / pad / bat-ground / noise (L7)
3. Video se align karo: kya ball us time bat ke paas thi? (L8)

Important (spec): Audio AKELA proof nahi hai!
Hamesha video evidence ke saath combine karo.

Usage:
    from core_processing.ultra_edge import UltraEdge
    ue = UltraEdge(sample_rate=44100)
    spikes = ue.detect_spikes(audio)  # [(time_s, amplitude, ...), ...]
    result = ue.classify_spike(spike, ball_near_bat=True)
    # → {'type': 'bat_ball', 'confidence': 85, ...}
"""

import math


class UltraEdge:
    def __init__(self, sample_rate=44100):
        self.sr = sample_rate

    def detect_spikes(self, audio, threshold_sigma=4.0, min_gap_s=0.1):
        """
        L6: Transient spikes dhoondo.
        audio: list/array of samples (float)
        Returns: [{'time_s': ..., 'amplitude': ..., 'duration_s': ...}, ...]
        """
        n = len(audio)
        if n == 0:
            return []

        # Baseline: mean + std
        mean = sum(audio) / n
        var = sum((x - mean) ** 2 for x in audio) / n
        std = math.sqrt(var) if var > 0 else 1e-10
        threshold = mean + threshold_sigma * std

        spikes = []
        i = 0
        min_gap = int(min_gap_s * self.sr)

        while i < n:
            if abs(audio[i]) > threshold:
                # Spike shuru — end dhoondo
                start = i
                peak = abs(audio[i])
                peak_idx = i
                while i < n and abs(audio[i]) > mean + 2 * std:
                    if abs(audio[i]) > peak:
                        peak = abs(audio[i])
                        peak_idx = i
                    i += 1
                end = i
                spikes.append({
                    'time_s': round(peak_idx / self.sr, 3),
                    'amplitude': round(peak, 3),
                    'duration_s': round((end - start) / self.sr, 4),
                    'snr': round(peak / (std + 1e-10), 1),  # signal-to-noise
                })
                i += min_gap  # gap skip karo (double-count nahi)
            else:
                i += 1

        return spikes

    def classify_spike(self, spike, ball_near_bat=False,
                       bat_swinging=False):
        """
        L7: Spike classify karo.
        L8: Video context use karo (ball bat ke paas thi?)

        Returns: {'type': ..., 'confidence': ..., 'reasoning': ...}
        """
        snr = spike.get('snr', 0)
        dur = spike.get('duration_s', 0)

        # Bat-ball: sharp, short, high SNR
        # Pad: duller, thoda lamba
        # Bat-ground: medium, lamba
        # Noise: low SNR ya bahut lamba

        if snr < 5:
            return {'type': 'noise', 'confidence': 70,
                    'reasoning': f'SNR {snr} bahut kam — background noise'}

        if dur > 0.05:
            return {'type': 'noise', 'confidence': 60,
                    'reasoning': f'Duration {dur*1000:.0f}ms bahut lambi — contact nahi'}

        # Video alignment (L8) — sabse important!
        if ball_near_bat and bat_swinging:
            if snr > 15 and dur < 0.01:
                return {'type': 'bat_ball', 'confidence': 88,
                        'reasoning': f'Sharp spike (SNR {snr}), ball bat ke paas thi — EDGE!'}
            elif snr > 8:
                return {'type': 'bat_ball', 'confidence': 70,
                        'reasoning': 'Spike + ball near bat — possible edge'}
            else:
                return {'type': 'pad_or_bat', 'confidence': 55,
                        'reasoning': 'Weak spike, ball paas thi — unclear contact'}

        if ball_near_bat and not bat_swinging:
            return {'type': 'pad_ball', 'confidence': 65,
                    'reasoning': 'Ball body ke paas, bat nahi hila — pad contact?'}

        if not ball_near_bat:
            return {'type': 'noise', 'confidence': 75,
                    'reasoning': 'Spike hai lekin ball bat se door thi — false positive'}

        return {'type': 'unknown', 'confidence': 30,
                'reasoning': 'Insufficient evidence'}

    def analyze_contact(self, audio, ball_near_bat_frames=None,
                        bat_swing_frames=None, fps=30):
        """
        Full pipeline: spikes → classify → video align.

        ball_near_bat_frames: [10, 11, 12] — kin frames me ball bat ke paas thi
        bat_swing_frames: [8, 9, 10, 11] — bat kab hila

        Returns: list of contact events
        """
        spikes = self.detect_spikes(audio)
        events = []

        for sp in spikes:
            frame = int(sp['time_s'] * fps)
            near = (ball_near_bat_frames and
                    any(abs(frame - f) <= 2 for f in ball_near_bat_frames))
            swinging = (bat_swing_frames and
                        any(abs(frame - f) <= 3 for f in bat_swing_frames))

            cls = self.classify_spike(sp, ball_near_bat=near,
                                      bat_swinging=swinging)
            events.append({
                'time_s': sp['time_s'],
                'frame': frame,
                **cls,
            })

        # Sirf interesting events (bat_ball ya pad_ball)
        contacts = [e for e in events
                    if e['type'] in ('bat_ball', 'pad_ball', 'pad_or_bat')]
        return {
            'total_spikes': len(spikes),
            'contact_events': contacts,
            'all_spikes': spikes,
        }
