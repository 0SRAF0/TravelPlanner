import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authService } from '../../../services/authService.ts';

/**
 * Authentication Callback Page
 *
 * This page handles the OAuth callback from Google.
 * It receives the authorization code, exchanges it for a JWT token,
 * and redirects the user to the appropriate page.
 */
export const GoogleOAuthCallback = () => {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(true);

  useEffect(() => {
    const handleCallback = async () => {
      try {
        // Parse URL parameters
        const params = new URLSearchParams(window.location.search);
        const code = params.get('code');
        const errorParam = params.get('error');

        // Handle OAuth errors
        if (errorParam) {
          setError('Authentication was cancelled or failed');
          setIsProcessing(false);
          return;
        }

        // Validate authorization code
        if (!code) {
          setError('No authorization code received');
          setIsProcessing(false);
          return;
        }

        // Exchange code for JWT token
        const authResponse = await authService.exchangeCodeForToken(code);

        // Save token and user info
        authService.saveToken(authResponse.access_token);
        authService.saveUser(authResponse.user);

        // Update header by triggering storage event
        window.dispatchEvent(new Event('storage'));

        // Redirect to dashboard
        navigate('/dashboard', { replace: true });

      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to complete authentication';
        setError(errorMessage);
        setIsProcessing(false);
        console.error('Authentication error:', err);
      }
    };

    handleCallback();
  }, [navigate]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center ">
        <div className="max-w-md w-full p-8 bg-white rounded-xl shadow-lg text-center">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg
              className="w-8 h-8 text-red-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Authentication Error</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-secondary border-t-accent rounded-full animate-spin mx-auto mb-4"></div>
        <h2 className="text-xl font-semibold text-gray-900 mb-2">
          {isProcessing ? 'Completing authentication...' : 'Redirecting...'}
        </h2>
        <p className="text-gray-600">Please wait</p>
      </div>
    </div>
  );
};

