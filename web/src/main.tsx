import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, RequireAuth } from './auth'
import Login from './pages/Login'
import Register from './pages/Register'
import Welcome from './pages/Welcome'
import Shell from './pages/Shell'
import Dashboard from './pages/Dashboard'
import Episode from './pages/Episode'
import Interview from './pages/Interview'
import Access from './pages/Access'
import Patients from './pages/Patients'
import Profile from './pages/Profile'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/welcome" element={<RequireAuth><Welcome /></RequireAuth>} />
          <Route path="/" element={<RequireAuth><Shell /></RequireAuth>}>
            <Route index element={<Dashboard />} />
            <Route path="episode/:id" element={<Episode />} />
            <Route path="episode/:id/interview" element={<Interview />} />
            <Route path="access" element={<Access />} />
            <Route path="patients" element={<Patients />} />
            <Route path="profile" element={<Profile />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </StrictMode>,
)
