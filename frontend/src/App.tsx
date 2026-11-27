import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { RequireAuth } from "./lib/auth";
import { ActivityPage } from "./pages/ActivityPage";
import { AssessmentPage } from "./pages/AssessmentPage";
import { LoginPage, RegisterPage } from "./pages/AuthPages";
import { LearnPage } from "./pages/LearnPage";
import { MePage } from "./pages/MePage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { PlanPage } from "./pages/PlanPage";
import { ProgressPage } from "./pages/ProgressPage";
import { SubjectPage } from "./pages/SubjectPage";
import { TodayPage } from "./pages/TodayPage";
import { TopicPage } from "./pages/TopicPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/today" element={<TodayPage />} />
          <Route path="/learn" element={<LearnPage />} />
          <Route path="/learn/subjects/:subjectId" element={<SubjectPage />} />
          <Route path="/learn/topics/:topicId" element={<TopicPage />} />
          <Route path="/assessment/:topicId/:mode" element={<AssessmentPage />} />
          <Route path="/activity/:recommendationId" element={<ActivityPage />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/progress" element={<ProgressPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/me" element={<MePage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/today" replace />} />
    </Routes>
  );
}
