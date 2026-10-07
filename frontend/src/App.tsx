import { Routes, Route } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Topics from "@/pages/Topics";
import Articles from "@/pages/Articles";
import Schedule from "@/pages/Schedule";
import Prompts from "@/pages/Prompts";
import Wizard from "@/pages/Wizard";
import Health from "@/pages/Health";
import Audit from "@/pages/Audit";
import ManualWorkbench from "@/pages/ManualWorkbench";
import AuthGate from "@/components/AuthGate";

export default function App() {
  return (
    <AuthGate><Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/topics" element={<Topics />} />
        <Route path="/articles" element={<Articles />} />
        <Route path="/manual" element={<ManualWorkbench />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/prompts" element={<Prompts />} />
        <Route path="/wizard" element={<Wizard />} />
        <Route path="/health" element={<Health />} />
        <Route path="/audit" element={<Audit />} />
      </Route>
    </Routes></AuthGate>
  );
}
