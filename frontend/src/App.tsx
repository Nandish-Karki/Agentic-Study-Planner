import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Verify from "./pages/Verify";
import ResetPassword from "./pages/ResetPassword";
import Dashboard from "./pages/Dashboard";
import NewPlan from "./pages/NewPlan";
import PlanView from "./pages/PlanView";
import Legal from "./pages/Legal";
import { type ReactNode } from "react";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <FullScreen>Loading…</FullScreen>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function FullScreen({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen grid place-items-center text-slate-400 font-inter">
      {children}
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/verify" element={<Verify />} />
      <Route path="/reset" element={<ResetPassword />} />
      <Route path="/legal/privacy" element={<Legal doc="privacy" title="Privacy Policy" />} />
      <Route path="/legal/tos" element={<Legal doc="tos" title="Terms & Conditions" />} />
      <Route
        path="/app"
        element={
          <Protected>
            <Dashboard />
          </Protected>
        }
      />
      <Route
        path="/app/new"
        element={
          <Protected>
            <NewPlan />
          </Protected>
        }
      />
      <Route
        path="/app/plan/:id"
        element={
          <Protected>
            <PlanView />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
