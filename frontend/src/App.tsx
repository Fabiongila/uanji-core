import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, Loading } from "@/components/ui";
import { NativeNotifications } from "@/features/native";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Projects = lazy(() => import("@/pages/Projects"));
const ProjectDetail = lazy(() => import("@/pages/ProjectDetail"));
const Tasks = lazy(() => import("@/pages/Tasks"));
const TaskDetail = lazy(() => import("@/pages/TaskDetail"));
const Agenda = lazy(() => import("@/pages/Agenda"));
const Planning = lazy(() => import("@/pages/Planning"));
const Review = lazy(() => import("@/pages/Review"));
const Notes = lazy(() => import("@/pages/Notes"));
const Knowledge = lazy(() => import("@/pages/Knowledge"));
const Templates = lazy(() => import("@/pages/Templates"));
const Automations = lazy(() => import("@/pages/Automations"));
const AutomationEditor = lazy(() => import("@/pages/AutomationEditor"));
const History = lazy(() => import("@/pages/History"));
const Metrics = lazy(() => import("@/pages/Metrics"));
const Activity = lazy(() => import("@/pages/Activity"));
const Assistant = lazy(() => import("@/pages/Assistant"));
const Integrations = lazy(() => import("@/pages/Integrations"));
const Vault = lazy(() => import("@/pages/Vault"));
const Backups = lazy(() => import("@/pages/Backups"));
const Settings = lazy(() => import("@/pages/Settings"));

const S = ({ children }: { children: ReactNode }) => <Suspense fallback={<Loading />}>{children}</Suspense>;

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<S><Dashboard /></S>} />
        <Route path="projects" element={<S><Projects /></S>} />
        <Route path="projects/:id" element={<S><ProjectDetail /></S>} />
        <Route path="tasks" element={<S><Tasks /></S>} />
        <Route path="tasks/:id" element={<S><TaskDetail /></S>} />
        <Route path="agenda" element={<S><Agenda /></S>} />
        <Route path="planning" element={<S><Planning /></S>} />
        <Route path="review" element={<S><Review /></S>} />
        <Route path="notes" element={<S><Notes /></S>} />
        <Route path="notes/:id" element={<S><Notes /></S>} />
        <Route path="knowledge" element={<S><Knowledge /></S>} />
        <Route path="templates" element={<S><Templates /></S>} />
        <Route path="templates/:id" element={<S><Templates /></S>} />
        <Route path="automations" element={<S><Automations /></S>} />
        <Route path="automations/:id" element={<S><AutomationEditor /></S>} />
        <Route path="history" element={<S><History /></S>} />
        <Route path="metrics" element={<S><Metrics /></S>} />
        <Route path="activity" element={<S><Activity /></S>} />
        <Route path="assistant" element={<S><Assistant /></S>} />
        <Route path="integrations" element={<S><Integrations /></S>} />
        <Route path="vault" element={<S><Vault /></S>} />
        <Route path="backups" element={<S><Backups /></S>} />
        <Route path="settings" element={<S><Settings /></S>} />
        <Route path="*" element={<EmptyState title="Página não encontrada" description="O endereço não corresponde a nenhuma área." />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <NativeNotifications />
      <AppRoutes />
    </BrowserRouter>
  );
}
