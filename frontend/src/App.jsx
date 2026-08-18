import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Link, Route, Routes } from 'react-router-dom';
import apiClient from './api/client';
import AgentWorkspace from './pages/AgentWorkspace';
import CaseDetail from './pages/CaseDetail';
import CaseForm from './pages/CaseForm';
import CasesList from './pages/CasesList';
import Home from './pages/Home';
import InventoryPage from './pages/InventoryPage';
import LiteraturePage from './pages/LiteraturePage';
import LabDocuments from './pages/LabDocuments';
import { LanguageProvider, useLanguage } from './LanguageContext';
import { EXPECTED_BACKEND_VERSION } from './expectedBackend';
import './App.css';
import './print.css';
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
          <Link to="/inventory">{t('nav.inventory')}</Link>
          <Link to="/literature">{t('nav.literature')}</Link>
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

function ProviderBanner() {
  const { t } = useLanguage();
  const [provider, setProvider] = useState(null);
  const [backendVersion, setBackendVersion] = useState(undefined); // undefined = not yet answered

  useEffect(() => {
    let cancelled = false;
    apiClient.get('/health')
      .then((res) => {
        if (cancelled) return;
        setProvider(res.data?.provider || null);
        // Pre-2.1 backends report no version at all — that is exactly the
        // stale-process case this banner exists for, so map it to null.
        setBackendVersion(res.data?.version || null);
      })
      .catch(() => {});      // unreachable backend already yields page-level errors
    return () => { cancelled = true; };
  }, []);

  // The launcher-started backend keeps serving old code until its window is
  // closed; the user cannot tell from the page alone, so tell them loudly.
  const versionBanner = (backendVersion !== undefined && backendVersion !== EXPECTED_BACKEND_VERSION)
    ? (
      <div className="error" style={{ margin: '0.5rem 1rem' }}>
        ⚠ {t('banner.backendOutdated')}
        {backendVersion ? `（${t('banner.backendVersion')} ${backendVersion} ≠ ${EXPECTED_BACKEND_VERSION}）` : ''}
      </div>
    )
    : null;

  if (!provider) return versionBanner;
  // Mock output is indistinguishable from a real model's by tone — the user
  // must always be able to see which one produced what they are reading.
  if (provider.error) {
    return (
      <>
        {versionBanner}
        <div className="error" style={{ margin: '0.5rem 1rem' }}>{t('banner.providerError')}{provider.error}</div>
      </>
    );
  }
  if (provider.is_mock) {
    return (
      <>
        {versionBanner}
        <div className="disclaimer" style={{ margin: '0.5rem 1rem' }}>
          ⚠ {t('banner.demo')}
        </div>
      </>
    );
  }
  return versionBanner;
}

function App() {
  return (
    <LanguageProvider>
      <Router>
        <div className="app">
          <NavBar />
          <ProviderBanner />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/agent" element={<AgentWorkspace />} />
              <Route path="/cases" element={<CasesList />} />
              <Route path="/cases/new" element={<CaseForm />} />
              <Route path="/cases/:id" element={<CaseDetail />} />
              <Route path="/cases/:id/edit" element={<CaseForm />} />
              <Route path="/lab-documents" element={<LabDocuments />} />
              <Route path="/inventory" element={<InventoryPage />} />
              <Route path="/literature" element={<LiteraturePage />} />
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
