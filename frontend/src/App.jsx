import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Home from './pages/Home';
import CasesList from './pages/CasesList';
import CaseDetail from './pages/CaseDetail';
import CaseForm from './pages/CaseForm';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app">
        <nav className="navbar">
          <div className="nav-container">
            <Link to="/" className="nav-brand">
              [Fufan Lab] LaserClaw
            </Link>
            <div className="nav-links">
              <Link to="/">首页</Link>
              <Link to="/cases">实验案例</Link>
              <Link to="/cases/new">新建案例</Link>
            </div>
          </div>
        </nav>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/cases" element={<CasesList />} />
            <Route path="/cases/new" element={<CaseForm />} />
            <Route path="/cases/:id" element={<CaseDetail />} />
            <Route path="/cases/:id/edit" element={<CaseForm />} />
          </Routes>
        </main>

        <footer className="footer">
          <p>&copy; 2026 Fufan Lab - LaserClaw 激光实验辅助系统</p>
        </footer>
      </div>
    </Router>
  );
}

export default App;
