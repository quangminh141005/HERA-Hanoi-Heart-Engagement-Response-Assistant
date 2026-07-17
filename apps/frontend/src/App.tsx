import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from './components/AppShell';
import { HomeRoute } from './routes/HomeRoute';

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}

