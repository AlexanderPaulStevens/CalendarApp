import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { CalendarPage } from './pages/CalendarPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, retry: 1 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<CalendarPage />} />
          <Route path="/recipes" element={<Navigate to="/?panel=meals" replace />} />
          <Route path="/fridge" element={<Navigate to="/?panel=fridge" replace />} />
          <Route path="/inventory" element={<Navigate to="/?panel=fridge" replace />} />
          <Route path="/shopping" element={<Navigate to="/?panel=shopping" replace />} />
          <Route path="/rules" element={<Navigate to="/?panel=rules" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
