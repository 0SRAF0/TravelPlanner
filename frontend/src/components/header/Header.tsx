import { useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import Button from "../button";
import { authService, type UserInfo } from "../../services/authService.ts";
import LogoFull from '../../../assets/full-logo.svg';

const maskEmail = (email: string, minLocalLength: number = 12): string => {
  if (!email) return '';
  const atIndex = email.indexOf('@');
  if (atIndex === -1) return email;
  const local = email.slice(0, atIndex);
  const domain = email.slice(atIndex + 1);
  if (local.length <= minLocalLength) return email;
  const head = local.slice(0, 4);
  const tail = local.slice(-2);
  return `${head}***${tail}@${domain}`;
};

export default function Header() {
  const navigate = useNavigate();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [imageLoadError, setImageLoadError] = useState(false);

  // Fix Google profile picture URL to include size parameter
  const getProfilePicture = (picture?: string) => {
    if (!picture) return null;
    console.log('Original picture URL:', picture);
    // Google profile images need size parameter (e.g., =s96-c)
    if (picture.includes('googleusercontent.com') && picture.endsWith('=s')) {
      const fixedUrl = `${picture}96-c`;
      console.log('Fixed picture URL:', fixedUrl);
      return fixedUrl;
    }
    console.log('Using picture URL as-is:', picture);
    return picture;
  };

  useEffect(() => {
    // Check if user is authenticated on component mount
    const loadUser = () => {
      const userData = authService.getUser();
      console.log('Loaded user data:', userData);
      setUser(userData);
      setImageLoadError(false);
    };

    loadUser();

    // Listen for storage changes (login/logout in other tabs)
    window.addEventListener('storage', loadUser);
    return () => window.removeEventListener('storage', loadUser);
  }, []);

  const handleHomepageClick = () => {
    navigate('/');
  };

  const handleSignInClick = () => {
    navigate('/sign-in');
  };

  const handleLogout = async () => {
    const token = authService.getToken();
    if (token) {
      await authService.logout(token);
    }
    setUser(null);
    setShowDropdown(false);
    navigate('/');
  };

  const handleDashboard = () => {
    setShowDropdown(false);
    navigate('/dashboard');
  };

  return (
    <header className="flex justify-between items-center px-6 py-6">
      <div className="flex items-center">
        <img
          src={LogoFull}
          alt="Travel Planner"
          className="h-10 w-auto cursor-pointer"
          onClick={handleHomepageClick}
        />
      </div>
      <div className="flex items-center space-x-4">
        {user ? (
          // Authenticated user menu
          <div className="relative">
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="flex items-center space-x-3 hover:opacity-80 transition-opacity"
            >
              {getProfilePicture(user.picture) && !imageLoadError ? (
                <img
                  src={getProfilePicture(user.picture)!}
                  alt={user.name}
                  className="w-8 h-8 rounded-full"
                  onError={(e) => {
                    // Fallback to initials if image fails to load
                    console.error('Image failed to load:', e.currentTarget.src);
                    setImageLoadError(true);
                  }}
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center text-gray-600 text-xs font-semibold">
                  {user.given_name?.[0] || user.name?.[0] || '?'}
                </div>
              )}
              <span className="text-sm font-medium text-gray-700">
                {user.given_name || user.name}
              </span>
              <svg
                className={`w-4 h-4 text-gray-500 transition-transform ${showDropdown ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Dropdown Menu */}
            {showDropdown && (
              <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg py-2 z-50 border border-gray-200">
                <div className="px-4 py-2 border-b border-gray-100">
                  <p className="text-sm font-medium text-gray-900">{user.name}</p>
                  <p className="text-xs text-gray-500">{maskEmail(user.email)}</p>
                </div>
                <button
                  onClick={handleDashboard}
                  className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  Dashboard
                </button>
                <button
                  onClick={handleLogout}
                  className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        ) : (
          // Not authenticated
          <Button text="Sign In" onClick={handleSignInClick} />
        )}
      </div>
    </header>
  );
}