import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { supabase } from "./lib/supabase";
import AuthView from "./views/AuthView";
import Dashboard from "./views/Dashboard";
import "./index.css";

function App() {
  const [session, setSession] = useState(null);
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);
  return session ? <Dashboard /> : <AuthView />;
}

createRoot(document.getElementById("root")).render(<App />);
