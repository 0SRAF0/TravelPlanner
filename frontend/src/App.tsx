import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import './App.css'
import Header from "./components/header/Header.tsx";
import { SignIn } from "./pages/signIn/SignIn.tsx";
import { GoogleOAuthCallback } from "./pages/signIn/components/GoogleOAuthCallback.tsx";

function App() {

  return (
    <Router>
      <div className="App">
        <Header />
        <Routes>
          <Route path="/" element={""} />
          <Route path="/sign-in" element={<SignIn />} />
          <Route path="/auth/callback" element={<GoogleOAuthCallback />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App
