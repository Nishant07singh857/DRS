import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getReviewById } from '../api/apiService';
import HawkEyeVisualizer from '../components/HawkEyeVisualizer';

function ReviewDetailPage() {
  const { id } = useParams();
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getReviewById(id)
      .then((response) => setReview(response.data))
      .catch(() => setError('Review load nahi ho paya.'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="text-center mt-10">Loading review details...</div>;
  if (error) return <div className="text-center mt-10 text-red-500">{error}</div>;
  if (!review) return <div className="text-center mt-10">Review not found.</div>;

  const analysis = review.analysis_data || {};
  const decisionText = analysis.final_decision || review.decision || 'N/A';
  const decisionColor =
    decisionText === 'OUT'
      ? 'text-red-500'
      : decisionText === "UMPIRE'S CALL"
        ? 'text-amber-500'
        : 'text-green-500';

  const checks = [
    { label: 'Pitching', ok: analysis.pitch_in_line, yes: 'IN-LINE', no: 'OUTSIDE LEG' },
    { label: 'Impact', ok: analysis.impact_in_line, yes: 'IN-LINE', no: 'OUTSIDE' },
    { label: 'Wickets', ok: analysis.hitting_wickets, yes: 'HITTING', no: 'MISSING' },
  ];

  return (
    <div className="container mx-auto max-w-6xl">
      <Link to="/reviews" className="text-indigo-400 hover:underline">&larr; Back to reviews</Link>
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-2 mt-4 mb-8">
        <div>
          <h1 className="text-4xl font-bold">Review Details</h1>
          <p className="text-gray-400 mt-1">
            Analyzed {review.created_at ? new Date(review.created_at).toLocaleString() : 'N/A'}
          </p>
        </div>
        <span className={`text-2xl font-black uppercase px-5 py-2 rounded-lg bg-gray-800 border border-gray-700 ${decisionColor}`}>
          {decisionText}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <HawkEyeVisualizer analysis={analysis} />
          <p className="text-gray-500 text-sm mt-3">
            Tracked ball path (white), predicted path after impact (dashed), pitch &amp; impact markers.
            Trajectory {analysis.trajectory_points ?? '—'} points se bani hai.
          </p>
        </div>

        <div className="bg-gray-800 p-6 rounded-xl shadow-lg h-fit border border-gray-700">
          <h2 className="text-2xl font-semibold border-b border-gray-700 pb-3 mb-4">Umpire's Decision</h2>
          <div className="text-center my-6">
            <p className={`text-6xl font-black uppercase ${decisionColor}`}>{decisionText}</p>
            <div className="mt-4">
              <div className="flex justify-between text-sm text-gray-400 mb-1">
                <span>Confidence</span>
                <span>{analysis.confidence ?? review.confidence ?? 'N/A'}%</span>
              </div>
              <div className="bg-gray-700 rounded-full h-2.5">
                <div
                  className="h-2.5 rounded-full bg-gradient-to-r from-indigo-500 to-emerald-400"
                  style={{ width: `${analysis.confidence ?? review.confidence ?? 0}%` }}
                />
              </div>
            </div>
          </div>

          <div className="space-y-3 text-lg">
            {checks.map((c) => (
              <div key={c.label} className={`flex justify-between items-center p-3 rounded-lg ${c.ok ? 'bg-green-500/15 border border-green-500/30' : 'bg-red-500/15 border border-red-500/30'}`}>
                <span className="text-gray-300">{c.label}</span>
                <span className="font-bold flex items-center gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full ${c.ok ? 'bg-green-400' : 'bg-red-400'}`} />
                  {c.ok ? c.yes : c.no}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ReviewDetailPage;
