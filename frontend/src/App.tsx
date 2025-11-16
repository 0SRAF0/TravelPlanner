import { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import './App.css'
import Header from "./components/header/Header.tsx";
import { ChatButton } from "./components/chat";
import { SignIn } from "./pages/signIn/SignIn.tsx";
import { GoogleOAuthCallback } from "./pages/signIn/components/GoogleOAuthCallback.tsx";
import { authService } from "./services/authService.ts";

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
          <Route path="/" element={""} />
          <Route path="/sign-in" element={<SignIn />} />
          <Route path="/auth/callback" element={<GoogleOAuthCallback />} />
        </Routes>
        {isAuthenticated && <ChatButton />}
      </div>
    </Router>
  )
}

export default App
