import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../App';

function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <header className="bg-gray-900/90 backdrop-blur border-b border-gray-800 px-4 md:px-8 py-4 flex justify-between items-center sticky top-0 z-50">
      <Link to="/" className="flex items-center gap-2">
        <span className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-500 to-emerald-500 flex items-center justify-center font-black text-white text-lg shadow-lg">
          D
        </span>
        <span className="text-xl font-bold text-white tracking-tight">AI Umpire <span className="text-indigo-400">PRO-X</span></span>
      </Link>
      <nav className="flex items-center space-x-3 md:space-x-5">
        {user ? (
          <>
            <Link to="/upload" className="text-gray-300 hover:text-white font-medium">Upload</Link>
            <Link to="/reviews" className="text-gray-300 hover:text-white font-medium">My Reviews</Link>
            <span className="text-indigo-400 hidden sm:inline">Welcome, {user.username}</span>
            <button onClick={handleLogout} className="bg-red-600 px-4 py-1.5 rounded-lg hover:bg-red-700 font-medium transition">Logout</button>
          </>
        ) : (
          <>
            <Link to="/login" className="text-gray-300 hover:text-white font-medium">Login</Link>
            <Link to="/register" className="bg-indigo-600 px-4 py-1.5 rounded-lg hover:bg-indigo-500 font-medium transition">Register</Link>
          </>
        )}
      </nav>
    </header>
  );
}

export default Header;
