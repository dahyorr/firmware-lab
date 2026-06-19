import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import Home from './pages/Home'
import RunPage from './pages/RunPage'
import ReportsPage from './pages/ReportsPage'
import ReportDetail from './pages/ReportDetail'

function Nav() {
  const loc = useLocation()
  const link = (to: string, label: string) => (
    <Link
      to={to}
      className={`px-3 py-1 rounded text-sm transition-colors ${
        loc.pathname.startsWith(to) && to !== '/'
          ? 'bg-green-700 text-white'
          : loc.pathname === '/' && to === '/'
          ? 'bg-green-700 text-white'
          : 'text-gray-400 hover:text-white'
      }`}
    >
      {label}
    </Link>
  )
  return (
    <header className="flex items-center gap-4 px-6 py-3 border-b border-gray-800 bg-gray-900">
      <Link to="/" className="text-green-400 font-bold tracking-widest text-sm mr-4">
        FIRMSCAN
      </Link>
      {link('/', 'Analyse')}
      {link('/reports', 'Reports')}
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex flex-col h-screen overflow-hidden">
        <Nav />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/run/:runId" element={<RunPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/reports/:filename" element={<ReportDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
