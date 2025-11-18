import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { GoogleOAuth } from './components/GoogleOAuth.tsx';
import { authService } from '../../services/authService.ts';
import logoWhite from '../../../assets/icon-logo-white.svg';
import Notification from '../../components/notification/Notification';

/**
 * Login Page
 *
 * Displays the login interface with Google OAuth option.
 */
export const SignIn = () => {
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Redirect if already authenticated
  useEffect(() => {
    if (authService.isAuthenticated()) {
      navigate('/dashboard', { replace: true });
    }
  }, [navigate]);

  const handleError = (errorMessage: string) => {
    setError(errorMessage);
    // Clear error after 5 seconds
    setTimeout(() => setError(null), 5000);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br ">
      <div className="max-w-md w-full mx-4">
        <div className="bg-white rounded-2xl shadow-xl p-8 space-y-8">
          {/* Header */}
          <div className="text-center">
            <div className="flex justify-center mb-4">
              <div className="w-16 h-16 bg-primary rounded-full flex items-center justify-center">
                <img src={logoWhite} alt="Travel Planner logo" className="w-8 h-8" />
              </div>
            </div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Welcome to Travel Planner</h1>
            <p className="text-gray-600">Sign in to start planning your next adventure</p>
          </div>

          

          {/* Google Login Button */}
          <div className="space-y-4">
            <GoogleOAuth onError={handleError} />
          </div>

          {/* Divider */}
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-300"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white text-gray-500">Secure authentication with Google</span>
            </div>
          </div>

          {/* Footer */}
          <div className="text-center text-sm text-gray-600">
            <p>
              By signing in, you agree to our{' '}
              <a href="/terms" className="text-accent hover:underline">
                Terms of Service
              </a>{' '}
              and{' '}
              <a href="/privacy" className="text-accent hover:underline">
                Privacy Policy
              </a>
            </p>
          </div>
        </div>

        {/* Additional Info */}
        <div className="mt-8 text-center">
          <p className="text-sm text-gray-600">
            🌍 Plan trips • 📅 Create itineraries • ✈️ Track adventures
          </p>
        </div>
      </div>
      <Notification
        isVisible={!!error}
        message={error || ''}
        type="error"
        onClose={() => setError(null)}
      />
    </div>
  );
};
