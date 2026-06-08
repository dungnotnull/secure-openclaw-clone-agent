import { Routes, Route } from 'react-router-dom';
import { AuthProvider } from '@/hooks/useAuth';
import { ToastProvider } from '@/components/Toast';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { AuthGuard } from '@/components/AuthGuard';
import Layout from '@/components/Layout';
import Dashboard from '@/pages/Dashboard';
import NewTask from '@/pages/NewTask';
import TaskDetail from '@/pages/TaskDetail';
import Login from '@/pages/Login';
import Register from '@/pages/Register';

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route
              element={
                <AuthGuard>
                  <Layout />
                </AuthGuard>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/tasks/new" element={<NewTask />} />
              <Route path="/tasks/:taskId" element={<TaskDetail />} />
            </Route>
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}
