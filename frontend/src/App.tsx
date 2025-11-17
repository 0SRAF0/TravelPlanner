import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';
import Header from './components/header/Header.tsx';
import { SignIn } from './pages/signIn/SignIn.tsx';
import Dashboard from './pages/dashboard/dashboard.tsx';
import { GoogleOAuthCallback } from './pages/signIn/components/GoogleOAuthCallback.tsx';
import { Home } from './pages/home/home.tsx';
import TripDetail from './pages/trip/TripDetail.tsx';
import PreferenceForm from './pages/preferences/PreferenceForm.tsx';
import { Chat } from './pages/chat/Chat.tsx';
import { authService } from './services/authService.ts';
import { useEffect, useState } from "react";
import { ChatButton } from "./components/chat";

// Protected Route Component
const ProtectedHome = () => {
  const isAuthenticated = authService.isAuthenticated();

  return isAuthenticated ? <Dashboard /> : <Home />;
};

// Protected Route Wrapper
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = authService.isAuthenticated();

  if (!isAuthenticated) {
    window.location.href = '/sign-in';
    return null;
  }

  return <>{children}</>;
};

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(authService.isAuthenticated());

  useEffect(() => {
    const checkAuth = () => {
      setIsAuthenticated(authService.isAuthenticated());
    };

    // Check on mount
    checkAuth();

    // Listen for storage changes (login/logout in other tabs or same tab)
    window.addEventListener('storage', checkAuth);
    // Also listen for custom events
    window.addEventListener('auth-change', checkAuth);

    return () => {
      window.removeEventListener('storage', checkAuth);
      window.removeEventListener('auth-change', checkAuth);
    };
  }, []);

  return (
    <Router>
      <div className="App">
        <Header />
        <Routes>
          <Route path="/" element={<ProtectedHome />} />
          <Route path="/sign-in" element={<SignIn />} />
          <Route path="/auth/callback" element={<GoogleOAuthCallback />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/trip/:tripId"
            element={
              <ProtectedRoute>
                <TripDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/trip/:tripId/preferences"
            element={
              <ProtectedRoute>
                <PreferenceForm
                  tripId={window.location.pathname.split('/')[2]}
                  userId={JSON.parse(localStorage.getItem('user_info') || '{}').id}
                />
              </ProtectedRoute>
            }
          />
          <Route
            path="/trip/:tripId/chat"
            element={
              <ProtectedRoute>
                <Chat />
              </ProtectedRoute>
            }
          />
        </Routes>
        {isAuthenticated && <ChatButton />}
      </div>
    </Router>
  );
}

export default App;
