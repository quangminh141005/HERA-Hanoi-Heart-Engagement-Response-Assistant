import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from './components/AppShell';
import { HomeRoute } from './routes/HomeRoute';
import { WidgetRoute } from './routes/WidgetRoute';

export function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <AppShell>
            <HomeRoute />
          </AppShell>
        }
      />
      <Route
        path="/widget/v1"
        element={
          <AppShell compact>
            <WidgetRoute />
          </AppShell>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
