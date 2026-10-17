import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadVideo, getTaskStatus } from '../api/apiService';

const POLL_INTERVAL_MS = 2000;

function UploadPage() {
  const [file, setFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [stage, setStage] = useState('idle'); // idle | uploading | processing | done | error
  const [progress, setProgress] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const pollTimer = useRef(null);
  const navigate = useNavigate();

  const handleFileChange = (e) => {
    setFile(e.target.files[0] || null);
    setError('');
  };

  const pollStatus = (taskId) => {
    pollTimer.current = setInterval(async () => {
      try {
        const res = await getTaskStatus(taskId);
        const { state, result: taskResult } = res.data;
        if (state === 'PROGRESS') {
          setProgress(taskResult);
        } else if (state === 'SUCCESS') {
          clearInterval(pollTimer.current);
          setResult(taskResult);
          setStage('done');
        } else if (state === 'FAILURE') {
          clearInterval(pollTimer.current);
          setError(typeof taskResult === 'string' ? taskResult : 'Processing failed');
          setStage('error');
        }
        // PENDING: bas wait karo
      } catch (err) {
        clearInterval(pollTimer.current);
        setError('Status check failed');
        setStage('error');
      }
    }, POLL_INTERVAL_MS);
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) {
      setError('Pehle ek video file chuno.');
      return;
    }
    setError('');
    setStage('uploading');
    setUploadProgress(0);
    try {
      const formData = new FormData();
      formData.append('video', file);
      const res = await uploadVideo(formData, (evt) => {
        if (evt.total) setUploadProgress(Math.round((evt.loaded * 100) / evt.total));
      });
      setStage('processing');
      pollStatus(res.data.task_id);
    } catch (err) {
      setError(err.response?.data?.message || 'Upload failed');
      setStage('error');
    }
  };

  const decision = result?.result;

  return (
    <div className="max-w-2xl mx-auto mt-10">
      <h1 className="text-3xl font-bold mb-6">Upload Video for LBW Analysis</h1>

      <form onSubmit={handleUpload} className="bg-gray-800 p-6 rounded-lg shadow-lg space-y-4">
        <input
          type="file"
          accept="video/mp4,video/avi,video/quicktime,video/x-matroska,video/webm,.mp4,.avi,.mov,.mkv,.webm"
          onChange={handleFileChange}
          className="w-full text-gray-300 file:mr-4 file:p-3 file:rounded file:border-0 file:bg-indigo-600 file:text-white hover:file:bg-indigo-700"
        />
        <button
          type="submit"
          disabled={stage === 'uploading' || stage === 'processing'}
          className="w-full bg-indigo-600 p-3 rounded font-bold hover:bg-indigo-700 disabled:opacity-50"
        >
          {stage === 'uploading' ? 'Uploading...' : stage === 'processing' ? 'Processing...' : 'Analyze Video'}
        </button>
      </form>

      {error && <p className="bg-red-500/20 text-red-400 p-3 rounded mt-4">{error}</p>}

      {stage === 'uploading' && (
        <div className="mt-4">
          <p className="text-gray-400 mb-2">Uploading: {uploadProgress}%</p>
          <div className="bg-gray-700 rounded h-3">
            <div className="bg-indigo-500 h-3 rounded transition-all" style={{ width: `${uploadProgress}%` }} />
          </div>
        </div>
      )}

      {stage === 'processing' && (
        <div className="mt-4 bg-gray-800 p-4 rounded">
          <p className="text-gray-300">
            {progress?.status || 'Processing video...'}
            {progress?.total ? ` (${progress.current}/${progress.total})` : ''}
          </p>
          {progress?.total > 0 && (
            <div className="bg-gray-700 rounded h-3 mt-2">
              <div
                className="bg-green-500 h-3 rounded transition-all"
                style={{ width: `${Math.round((progress.current / progress.total) * 100)}%` }}
              />
            </div>
          )}
        </div>
      )}

      {stage === 'done' && (
        <div className="mt-4 bg-gray-800 p-6 rounded-lg">
          <h2 className="text-2xl font-bold mb-2">Analysis Complete</h2>
          {decision ? (
            <>
              <p className={`text-5xl font-bold my-4 ${decision.final_decision === 'OUT' ? 'text-red-500' : decision.final_decision === "UMPIRE'S CALL" ? 'text-amber-500' : 'text-green-500'}`}>
                {decision.final_decision}
              </p>
              <p className="text-gray-400">Confidence: {decision.confidence}%</p>
              <button
                onClick={() => navigate('/reviews')}
                className="mt-4 bg-indigo-600 px-4 py-2 rounded hover:bg-indigo-700"
              >
                View in My Reviews
              </button>
            </>
          ) : (
            <p className="text-gray-400">Video me ball detect nahi hui — koi decision nahi bana.</p>
          )}
        </div>
      )}
    </div>
  );
}

export default UploadPage;
