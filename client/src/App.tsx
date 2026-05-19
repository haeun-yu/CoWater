import { Route, Routes } from 'react-router-dom';
import { Shell } from './components/layout/Shell';
import {
  AnalyticsPage,
  ChatPage,
  DashboardPage,
  DevicePage,
  EventLogPage,
  MissionPage,
  PolicyPage,
  ProposalPage,
  SettingsPage,
  UsersPage,
} from './pages';

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/ops" element={<DashboardPage />} />
        <Route path="/alerts" element={<EventLogPage />} />
        <Route path="/proposal" element={<ProposalPage />} />
        <Route path="/mission" element={<MissionPage />} />
        <Route path="/mission/:missionId" element={<MissionPage />} />
        <Route path="/device" element={<DevicePage />} />
        <Route path="/device/:deviceId" element={<DevicePage />} />
        <Route path="/policy" element={<PolicyPage />} />
        <Route path="/events" element={<EventLogPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/chat" element={<ChatPage />} />
      </Routes>
    </Shell>
  );
}
