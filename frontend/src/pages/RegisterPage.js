import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register as apiRegister } from '../api/apiService';
import { useAuth } from '../App';

function RegisterPage() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 6) {
      setError('Password kam se kam 6 characters ka ho.');
      return;
    }
    try {
      await apiRegister({ username, email, password });
      // Register ke baad auto-login
      const result = await login({ username, password });
      if (result.success) {
        navigate('/');
      } else {
        navigate('/login');
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Registration failed');
    }
  };

  return (
    <div className="max-w-md mx-auto mt-16 bg-gray-800 p-8 rounded-lg shadow-lg">
      <h1 className="text-3xl font-bold mb-6 text-center">Register</h1>
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
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full p-3 rounded bg-gray-700 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          required
        />
        <input
          type="password"
          placeholder="Password (min 6 chars)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-3 rounded bg-gray-700 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          required
        />
        <button type="submit" className="w-full bg-indigo-600 p-3 rounded font-bold hover:bg-indigo-700">
          Create Account
        </button>
      </form>
      <p className="text-center mt-4 text-gray-400">
        Pehle se account hai? <Link to="/login" className="text-indigo-400 hover:underline">Login karo</Link>
      </p>
    </div>
  );
}

export default RegisterPage;
