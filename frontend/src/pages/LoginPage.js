import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../App';

function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="bg-gray-800 p-4 shadow-md flex justify-between items-center">
      <Link to="/" className="text-2xl font-bold text-white">AI Umpire PRO-X</Link>
      <nav className="flex items-center space-x-4">
        {user ? (
          <>
            <Link to="/reviews" className="text-gray-300 hover:text-white">My Reviews</Link>
            <span className="text-indigo-400">Welcome, {user.username}</span>
            <button onClick={handleLogout} className="bg-red-600 px-3 py-1 rounded hover:bg-red-700">Logout</button>
          </>
        ) : (
          <>
            <Link to="/login" className="text-gray-300 hover:text-white">Login</Link>
            <Link to="/register" className="bg-indigo-600 px-3 py-1 rounded hover:bg-indigo-7ax00">Register</Link>
          </>
        )}
      </nav>
    </header>
  );
}

export default Header;
