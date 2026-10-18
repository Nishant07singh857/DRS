import React, { useRef, useState, useEffect } from 'react';

/**
 * VideoReviewPlayer — international third umpire jaisa video review tool.
 *
 * Features:
 * - Slow motion (0.25x, 0.5x, 1x, 2x)
 * - Frame-by-frame stepping (←/→)
 * - Zoom in/out (video par)
 * - Timeline with event markers (bookmarks)
 * - Keyboard shortcuts
 */

const SPEEDS = [0.25, 0.5, 1, 2];

function VideoReviewPlayer({ videoUrl, bookmarks = [], fps = 30 }) {
  const videoRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(2); // 1x
  const [zoom, setZoom] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const speed = SPEEDS[speedIdx];

  useEffect(() => {
    const v = videoRef.current;
    if (v) v.playbackRate = speed;
  }, [speed]);

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) { v.play(); setPlaying(true); }
    else { v.pause(); setPlaying(false); }
  };

  const stepFrame = (dir) => {
    const v = videoRef.current;
    if (!v) return;
    v.pause(); setPlaying(false);
    v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + (dir / fps)));
  };

  const jumpTo = (t) => {
    const v = videoRef.current;
    if (v) v.currentTime = t;
  };

  const cycleSpeed = () => setSpeedIdx((speedIdx + 1) % SPEEDS.length);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if (e.key === ' ') { e.preventDefault(); togglePlay(); }
      else if (e.key === 'ArrowRight') stepFrame(1);
      else if (e.key === 'ArrowLeft') stepFrame(-1);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  const fmt = (s) => {
    const m = Math.floor(s / 60);
    const sec = (s % 60).toFixed(1);
    return `${m}:${sec.padStart(4, '0')}`;
  };

  return (
    <div style={styles.container}>
      {/* Video with zoom */}
      <div style={styles.videoWrap}>
        <video
          ref={videoRef}
          src={videoUrl}
          style={{ ...styles.video, transform: `scale(${zoom})` }}
          onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
          onLoadedMetadata={(e) => setDuration(e.target.duration)}
          onEnded={() => setPlaying(false)}
        />
        {/* Zoom controls overlay */}
        <div style={styles.zoomControls}>
          <button style={styles.zbtn} onClick={() => setZoom(Math.max(1, zoom - 0.5))}>−</button>
          <span style={styles.zoomLabel}>{Math.round(zoom * 100)}%</span>
          <button style={styles.zbtn} onClick={() => setZoom(Math.min(4, zoom + 0.5))}>+</button>
          {zoom > 1 && (
            <button style={styles.zbtn} onClick={() => setZoom(1)}>Reset</button>
          )}
        </div>
        {/* Speed badge */}
        {speed !== 1 && (
          <div style={styles.speedBadge}>{speed}x SLOW-MO</div>
        )}
      </div>

      {/* Timeline with bookmarks */}
      <div style={styles.timeline}>
        <input
          type="range" min={0} max={duration || 100} step={0.033}
          value={currentTime}
          onChange={(e) => jumpTo(parseFloat(e.target.value))}
          style={styles.scrubber}
        />
        <div style={styles.markers}>
          {bookmarks.map((b, i) => (
            <div
              key={i}
              title={`${b.bookmark_type} @ ${fmt(b.timestamp_s)}`}
              onClick={() => jumpTo(b.timestamp_s)}
              style={{
                ...styles.marker,
                left: `${(b.timestamp_s / (duration || 1)) * 100}%`,
                backgroundColor: b.bookmark_type === 'wicket' ? '#ef4444'
                  : b.bookmark_type === 'edge' ? '#f59e0b' : '#3b82f6',
              }}
            />
          ))}
        </div>
        <div style={styles.timeRow}>
          <span>{fmt(currentTime)}</span>
          <span>{fmt(duration)}</span>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controls}>
        <button style={styles.btn} onClick={() => stepFrame(-1)} title="← 1 frame back">⏮</button>
        <button style={styles.btnMain} onClick={togglePlay}>
          {playing ? '⏸' : '▶'}
        </button>
        <button style={styles.btn} onClick={() => stepFrame(1)} title="→ 1 frame forward">⏭</button>
        <button style={styles.btn} onClick={cycleSpeed} title="Playback speed">
          {speed}x
        </button>
      </div>

      <div style={styles.hint}>
        Space = play/pause · ←/→ = frame step · Click markers to jump
      </div>
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: '#0f172a', borderRadius: 12, padding: 16,
    fontFamily: 'system-ui', color: '#fff', maxWidth: 720,
  },
  videoWrap: {
    position: 'relative', backgroundColor: '#000', borderRadius: 8,
    overflow: 'hidden', aspectRatio: '16/9',
  },
  video: { width: '100%', height: '100%', objectFit: 'contain', transition: 'transform 0.2s' },
  zoomControls: {
    position: 'absolute', top: 8, right: 8, display: 'flex',
    gap: 4, alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.6)',
    borderRadius: 6, padding: 4,
  },
  zbtn: {
    backgroundColor: '#374151', color: '#fff', border: 'none',
    borderRadius: 4, padding: '4px 10px', cursor: 'pointer', fontSize: 14,
  },
  zoomLabel: { fontSize: 12, minWidth: 40, textAlign: 'center' },
  speedBadge: {
    position: 'absolute', top: 8, left: 8, backgroundColor: '#7c3aed',
    padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 'bold',
  },
  timeline: { marginTop: 12, position: 'relative' },
  scrubber: { width: '100%', cursor: 'pointer' },
  markers: { position: 'relative', height: 0 },
  marker: {
    position: 'absolute', top: -14, width: 8, height: 8, borderRadius: '50%',
    transform: 'translateX(-50%)', cursor: 'pointer', border: '1px solid #fff',
  },
  timeRow: {
    display: 'flex', justifyContent: 'space-between',
    fontSize: 12, opacity: 0.7, marginTop: 4,
  },
  controls: {
    display: 'flex', gap: 8, justifyContent: 'center',
    alignItems: 'center', marginTop: 12,
  },
  btn: {
    backgroundColor: '#1e293b', color: '#fff', border: 'none',
    borderRadius: 8, padding: '10px 16px', cursor: 'pointer', fontSize: 16,
  },
  btnMain: {
    backgroundColor: '#2563eb', color: '#fff', border: 'none',
    borderRadius: '50%', width: 52, height: 52, cursor: 'pointer', fontSize: 20,
  },
  hint: { textAlign: 'center', fontSize: 11, opacity: 0.5, marginTop: 8 },
};

export default VideoReviewPlayer;
