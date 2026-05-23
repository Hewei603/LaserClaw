import React from 'react';
import { BrowserRouter as Router, Link, Route, Routes } from 'react-router-dom';
import AgentWorkspace from './pages/AgentWorkspace';
import CaseDetail from './pages/CaseDetail';
import CaseForm from './pages/CaseForm';
import CasesList from './pages/CasesList';
import Home from './pages/Home';
import LabDocuments from './pages/LabDocuments';
import { LanguageProvider, useLanguage } from './LanguageContext';
import './App.css';
import logo from './assets/logo.png';

function NavBar() {
  const { lang, setLang, t } = useLanguage();
  return (
    <nav className="navbar">
      <div className="nav-container">
        <img src={logo} alt="LaserClaw Logo" className="logo" />
        <div className="nav-links">
          <Link to="/">{t('nav.home')}</Link>
          <Link to="/agent">{t('nav.agent')}</Link>
          <Link to="/cases">{t('nav.cases')}</Link>
          <Link to="/cases/new">{t('nav.newCase')}</Link>
          <Link to="/lab-documents">{t('nav.labDocs')}</Link>
          <button
            className="lang-toggle"
            onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
          >
            {lang === 'zh' ? 'EN' : '中文'}
          </button>
        </div>
      </div>
    </nav>
  );
}

function FooterText() {
  const { t } = useLanguage();
  return <p>{t('common.footer')}</p>;
}

function App() {
  return (
    <LanguageProvider>
      <Router>
        <div className="app">
          <NavBar />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/agent" element={<AgentWorkspace />} />
              <Route path="/cases" element={<CasesList />} />
              <Route path="/cases/new" element={<CaseForm />} />
              <Route path="/cases/:id" element={<CaseDetail />} />
              <Route path="/cases/:id/edit" element={<CaseForm />} />
              <Route path="/lab-documents" element={<LabDocuments />} />
            </Routes>
          </main>
          <footer className="footer">
            <FooterText />
          </footer>
        </div>
      </Router>
    </LanguageProvider>
  );
}


export default App;
