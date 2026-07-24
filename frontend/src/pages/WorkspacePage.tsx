import { Navigate } from 'react-router-dom';

export default function WorkspacePage() {
  return <Navigate to="/settings?tab=documents" replace />;
}
