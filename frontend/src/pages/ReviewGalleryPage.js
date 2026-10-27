import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getUserReviews } from '../api/apiService';

function ReviewGalleryPage() {
  const [data, setData] = useState({ items: [], page: 1, pages: 1, total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    getUserReviews(page)
      .then((res) => setData(res.data))
      .catch(() => setError('Reviews load nahi ho paye.'))
      .finally(() => setLoading(false));
  }, [page]);

  if (loading) return <div className="text-center mt-10">Loading reviews...</div>;
  if (error) return <div className="text-center mt-10 text-red-500">{error}</div>;

  // FE-M1: pehle PENDING bhi green (NOT OUT colour) dikhta tha,
  // aur confidence null par "Confidence: %" dikhta tha. FE-H7:
  // umpires_call flag ho to amber.
  const colorFor = (r) =>
    r.analysis_data?.umpires_call ? 'text-amber-500'
    : r.decision === 'OUT' ? 'text-red-500'
    : r.decision === 'NOT OUT' ? 'text-green-500'
    : 'text-amber-500';

  return (
    <div className="max-w-4xl mx-auto mt-10">
      <h1 className="text-3xl font-bold mb-6">My Reviews ({data.total})</h1>
      {data.items.length === 0 ? (
        <p className="text-gray-400">Abhi koi review nahi hai. Pehle ek video upload karo.</p>
      ) : (
        <div className="space-y-4">
          {data.items.map((r) => (
            <Link
              key={r.id}
              to={`/reviews/${r.id}`}
              className="block bg-gray-800 p-4 rounded-lg hover:bg-gray-700 transition"
            >
              <div className="flex justify-between items-center">
                <div>
                  <span className={`text-2xl font-bold ${colorFor(r)}`}>{r.decision}</span>
                  {r.analysis_data?.umpires_call && (
                    <span className="text-amber-400 ml-2 text-sm font-bold">UMPIRE'S CALL</span>
                  )}
                  <span className="text-gray-400 ml-3">Confidence: {r.confidence ?? '—'}{r.confidence != null ? '%' : ''}</span>
                </div>
                <span className="text-gray-500 text-sm">
                  {r.created_at ? new Date(r.created_at).toLocaleString() : ''}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
      {data.pages > 1 && (
        <div className="flex justify-center items-center gap-4 mt-6">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="bg-gray-700 px-4 py-2 rounded disabled:opacity-40 hover:bg-gray-600"
          >
            Prev
          </button>
          <span className="text-gray-400">Page {data.page} / {data.pages}</span>
          <button
            disabled={page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
            className="bg-gray-700 px-4 py-2 rounded disabled:opacity-40 hover:bg-gray-600"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

export default ReviewGalleryPage;
