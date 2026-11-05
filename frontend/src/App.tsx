import { useEffect, useState } from "react";

import { loadSession, logout, type Session } from "./lib/auth";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";

export default function App() {
  const [session, setSession] = useState<Session | null>(() => loadSession());

  useEffect(() => {
    const expire = () => setSession(null);
    window.addEventListener("aiwf:auth-expired", expire);
    return () => window.removeEventListener("aiwf:auth-expired", expire);
  }, []);

  if (!session) {
    return <LoginPage onLogin={setSession} />;
  }

  return (
    <HomePage
      session={session}
      onLogout={() => {
        void logout();
        setSession(null);
      }}
    />
  );
}