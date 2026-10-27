import React, { useState } from 'react';
import { getPitchMap, getOverSummary } from '../api/apiService';

/**
 * PitchMapTool — FE-H6: pitch-map / over-summary endpoints (Phase 3
 * me bane) ka pehla UI surface. Ye endpoints stateless transforms
 * hain — caller body me deliveries deta hai, koi DB row nahi padhi
 * jaati — isliye tool me balls manually add hoti hain (pitch_x:
 * stumps se bowler ki taraf metres, 0–10; pitch_y: lateral metres,
 * + = off side for RHB). Review ke analysis_data me metres nahi
 * hote (sirf pixels), isliye usse pitch coordinates invent nahi
 * kiye jaate.
 *
 * PDF download ka koi claim nahi: backend me PDF endpoint hai hi
 * nahi — over-summary HTML report milta hai, jise browser se print
 * karke PDF banaya ja sakta hai.
 */
const OUTCOMES = ['dot', 'run', 'boundary', 'wicket', 'wide', 'noball'];

function PitchMapTool() {
  const [balls, setBalls] = useState([]);
  const [pitchX, setPitchX] = useState('4.5');
  const [pitchY, setPitchY] = useState('0.1');
  const [outcome, setOutcome] = useState('dot');
  const [speed, setSpeed] = useState('');
  const [runs, setRuns] = useState('0');
  const [pitchMap, setPitchMap] = useState(null);
  const [overSummary, setOverSummary] = useState(null);
  const [error, setError] = useState('');

  const addBall = (e) => {
    e.preventDefault();
    const x = parseFloat(pitchX);
    const y = parseFloat(pitchY);
    if (!Number.isFinite(x) || x < 0 || x > 10) {
      setError('pitch_x 0–10 metres ke andar hona chahiye.');
      return;
    }
    if (!Number.isFinite(y)) {
      setError('pitch_y numeric hona chahiye.');
      return;
    }
    setError('');
    setBalls((prev) => [
      ...prev,
      {
        pitch_x: x,
        pitch_y: y,
        outcome,
        speed_kmh: speed === '' ? null : parseFloat(speed),
        runs: parseInt(runs, 10) || 0,
      },
    ]);
  };

  const buildPitchMap = async () => {
    setError('');
    try {
      const res = await getPitchMap({
        bowler_name: 'Bowler',
        deliveries: balls.map((b) => ({
          pitch_x: b.pitch_x,
          pitch_y: b.pitch_y,
          outcome: b.outcome,
          speed_kmh: b.speed_kmh,
        })),
      });
      setPitchMap(res.data);
    } catch (err) {
      setError(err.response?.data?.message || 'Pitch map ban nahi paya.');
    }
  };

  const buildOverSummary = async () => {
    setError('');
    try {
      const res = await getOverSummary({
        over_number: 1,
        bowler: 'Bowler',
        batsman: 'Batsman',
        balls: balls.map((b) => ({
          outcome: b.outcome,
          runs: b.runs,
          delivery_analysis: b.speed_kmh != null ? { speed_kmh: b.speed_kmh } : {},
        })),
      });
      setOverSummary(res.data);
    } catch (err) {
      setError(err.response?.data?.message || 'Over summary ban nahi paya.');
    }
  };

  return (
    <div className="bg-gray-800 p-6 rounded-xl border border-gray-700">
      <h2 className="text-2xl font-semibold mb-2">Pitch Map &amp; Over Summary</h2>
      <p className="text-sm text-gray-400 mb-4">
        Balls add karo, phir backend ke pitch-map / over-summary endpoints se
        SVG aur stats banao. PDF download nahi hai — over-summary HTML report
        milta hai, jise browser print se PDF banaya ja sakta hai.
      </p>

      <form onSubmit={addBall} className="flex flex-wrap gap-2 mb-4">
        <label className="text-sm text-gray-300">
          Pitch (m, 0–10)
          <input type="number" step="0.1" min="0" max="10" value={pitchX}
            onChange={(e) => setPitchX(e.target.value)}
            className="block bg-gray-700 rounded p-2 text-white w-24" />
        </label>
        <label className="text-sm text-gray-300">
          Line (m, +off)
          <input type="number" step="0.1" value={pitchY}
            onChange={(e) => setPitchY(e.target.value)}
            className="block bg-gray-700 rounded p-2 text-white w-24" />
        </label>
        <label className="text-sm text-gray-300">
          Outcome
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)}
            className="block bg-gray-700 rounded p-2 text-white">
            {OUTCOMES.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        </label>
        <label className="text-sm text-gray-300">
          Speed (km/h)
          <input type="number" step="0.1" value={speed}
            onChange={(e) => setSpeed(e.target.value)}
            className="block bg-gray-700 rounded p-2 text-white w-24" />
        </label>
        <label className="text-sm text-gray-300">
          Runs
          <input type="number" min="0" value={runs}
            onChange={(e) => setRuns(e.target.value)}
            className="block bg-gray-700 rounded p-2 text-white w-20" />
        </label>
        <button type="submit" className="self-end bg-indigo-600 px-4 py-2 rounded font-bold hover:bg-indigo-700">
          Ball Add Karo
        </button>
      </form>

      {balls.length > 0 && (
        <p className="text-sm text-gray-400 mb-4">
          {balls.length} ball(s): {balls.map((b, i) => `#${i + 1} ${b.pitch_x}m/${b.pitch_y}m ${b.outcome}`).join(' · ')}
          {' '}
          <button onClick={() => { setBalls([]); setPitchMap(null); setOverSummary(null); }}
            className="text-indigo-400 hover:underline ml-2">Clear</button>
        </p>
      )}

      {error && <p className="bg-red-500/20 text-red-400 p-3 rounded mb-4">{error}</p>}

      <div className="flex gap-2 mb-4">
        <button disabled={balls.length === 0} onClick={buildPitchMap}
          className="bg-emerald-600 px-4 py-2 rounded font-bold hover:bg-emerald-500 disabled:opacity-50">
          Pitch Map Banao
        </button>
        <button disabled={balls.length === 0} onClick={buildOverSummary}
          className="bg-amber-600 px-4 py-2 rounded font-bold hover:bg-amber-500 disabled:opacity-50">
          Over Summary Banao
        </button>
      </div>

      {pitchMap && (
        <div className="mt-4">
          <h3 className="font-semibold mb-2">Pitch Map — {pitchMap.bowler}</h3>
          <div className="bg-white rounded p-2 max-w-md" dangerouslySetInnerHTML={{ __html: pitchMap.svg }} />
          <pre className="text-sm text-gray-300 mt-2 whitespace-pre-wrap">
            {JSON.stringify(pitchMap.stats, null, 2)}
          </pre>
        </div>
      )}

      {overSummary && (
        <div className="mt-4">
          <h3 className="font-semibold mb-2">Over Summary</h3>
          <pre className="text-sm text-gray-300 mb-2 whitespace-pre-wrap">
            {JSON.stringify(overSummary.summary, null, 2)}
          </pre>
          <iframe title="Over summary report" sandbox=""
            srcDoc={overSummary.html}
            className="w-full h-96 bg-white rounded" />
        </div>
      )}
    </div>
  );
}

export default PitchMapTool;
