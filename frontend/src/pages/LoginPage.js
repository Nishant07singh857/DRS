import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../App';

function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const result = await login({ username, password });
    if (result.success) {
      navigate('/');
    } else {
      setError(result.message);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-16 bg-gray-800 p-8 rounded-lg shadow-lg">
      <h1 className="text-3xl font-bold mb-6 text-center">Login</h1>
      {error && <p className="bg-red-500/20 text-red-400 p-3 rounded mb-4">{error}</p>}
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full p-3 rounded bg-gray-700 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-3 rounded bg-gray-700 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          required
        />
        <button type="submit" className="w-full bg-indigo-600 p-3 rounded font-bold hover:bg-indigo-700">
          Login
        </button>
      </form>
      <p className="text-center mt-4 text-gray-400">
        Account nahi hai? <Link to="/register" className="text-indigo-400 hover:underline">Register karo</Link>
      </p>
    </div>
  );
}

export default LoginPage;
