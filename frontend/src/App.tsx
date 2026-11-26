import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from './auth'
import { ToastProvider, reportError } from './components/Toast'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Guard } from './components/Layouts'
import Login from './pages/Login'
import BrokerPolicies from './pages/broker/Policies'
import IssuePolicy from './pages/broker/IssuePolicy'
import BrokerPolicy from './pages/broker/PolicyDetail'
import Customers from './pages/broker/Customers'
import Integrations from './pages/broker/Integrations'
import PortalHome from './pages/portal/Home'
import PortalPolicy from './pages/portal/Policy'

// Every failed query or mutation is reported as a toast, wherever it was triggered.
const qc = new QueryClient({
  queryCache: new QueryCache({ onError: reportError }),
  mutationCache: new MutationCache({ onError: reportError }),
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
      <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/broker" element={<Guard role="broker" />}>
              <Route index element={<BrokerPolicies />} />
              <Route path="new" element={<IssuePolicy />} />
              <Route path="customers" element={<Customers />} />
              <Route path="integrations" element={<Integrations />} />
              <Route path="policies/:id" element={<BrokerPolicy />} />
            </Route>
            <Route path="/portal" element={<Guard role="customer" />}>
              <Route index element={<PortalHome />} />
              <Route path="policies/:id" element={<PortalPolicy />} />
            </Route>
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
      </ErrorBoundary>
      </ToastProvider>
    </QueryClientProvider>
  )
}
