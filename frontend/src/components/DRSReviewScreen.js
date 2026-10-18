import React from 'react';

/**
 * DRSReviewScreen — umpire review screen (P2).
 * 3D trajectory + evidence + decision panel.
 */
function DRSReviewScreen({ review }) {
  if (!review) {
    return <div style={styles.empty}>Review select karo</div>;
  }

  const statusColor = {
    pending: '#f59e0b', processing: '#3b82f6', completed: '#22c55e',
    inconclusive: '#eab308', confirmed: '#10b981', failed: '#ef4444',
  }[review.status] || '#6b7280';

  const decisionColor = {
    'OUT': '#ef4444', 'NOT OUT': '#22c55e', 'INCONCLUSIVE': '#eab308',
  }[review.final_decision || review.ai_recommendation] || '#fff';

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <span style={styles.type}>{review.review_type} REVIEW</span>
        <span style={{ ...styles.status, backgroundColor: statusColor }}>
          {review.status.toUpperCase()}
        </span>
      </div>

      {/* Original call vs AI */}
      <div style={styles.vsRow}>
        <div style={styles.callBox}>
          <div style={styles.label}>On-field Call</div>
          <div style={styles.call}>{review.original_call || '—'}</div>
        </div>
        <div style={styles.arrow}>→</div>
        <div style={styles.callBox}>
          <div style={styles.label}>AI Recommendation</div>
          <div style={styles.call}>{review.ai_recommendation || '...'}</div>
          {review.ai_confidence != null && (
            <div style={styles.conf}>{review.ai_confidence}% confident</div>
          )}
        </div>
        <div style={styles.arrow}>→</div>
        <div style={{ ...styles.callBox, borderColor: decisionColor }}>
          <div style={styles.label}>Final Decision</div>
          <div style={{ ...styles.call, color: decisionColor }}>
            {review.is_locked ? (review.final_decision || '—') : 'Pending...'}
          </div>
          {review.is_locked && <div style={styles.locked}>🔒 LOCKED</div>}
        </div>
      </div>

      {/* Evidence */}
      {review.evidence && Object.keys(review.evidence).length > 0 && (
        <div style={styles.evidence}>
          <div style={styles.label}>Evidence</div>
          <pre style={styles.pre}>
            {JSON.stringify(review.evidence, null, 2)}
          </pre>
        </div>
      )}

      {/* Confirmation note */}
      {review.confirmation_note && (
        <div style={styles.note}>
          📝 Umpire note: {review.confirmation_note}
        </div>
      )}
    </div>
  );
}

const styles = {
  container: {
    backgroundColor: '#0f172a', color: '#fff', borderRadius: 12,
    padding: 20, fontFamily: 'system-ui', maxWidth: 700,
  },
  empty: { padding: 40, textAlign: 'center', opacity: 0.5 },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 16,
  },
  type: { fontSize: 20, fontWeight: 'bold' },
  status: {
    padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 'bold',
  },
  vsRow: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 },
  callBox: {
    flex: 1, backgroundColor: '#1e293b', borderRadius: 8, padding: 12,
    textAlign: 'center', border: '2px solid transparent',
  },
  label: { fontSize: 11, opacity: 0.6, marginBottom: 4 },
  call: { fontSize: 22, fontWeight: 'bold' },
  conf: { fontSize: 12, opacity: 0.7, marginTop: 4 },
  arrow: { fontSize: 20, opacity: 0.5 },
  locked: { fontSize: 11, color: '#10b981', marginTop: 4, fontWeight: 'bold' },
  evidence: { backgroundColor: '#1e293b', borderRadius: 8, padding: 12 },
  pre: { fontSize: 12, overflow: 'auto', margin: 0 },
  note: {
    marginTop: 12, backgroundColor: '#1e3a5f', borderRadius: 8,
    padding: 10, fontSize: 13,
  },
};

export default DRSReviewScreen;
