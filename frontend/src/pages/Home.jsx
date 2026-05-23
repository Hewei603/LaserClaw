import React from 'react';
import { Link } from 'react-router-dom';
import { useLanguage } from '../LanguageContext';

function Home() {
  const { t } = useLanguage();
  return (
    <div className="home-page">
      <div className="home-hero">
        <div className="home-hero-badge">{t('home.badge')}</div>
        <h1 className="home-hero-title">{t('home.title')}</h1>
        <p className="home-hero-subtitle">
          {t('home.subtitle')}<br />
          {t('home.subtitle2')}
        </p>
      </div>

      <div className="home-card-wrap">
        <div className="home-main-card">
          <div className="home-main-card-icon">🔬</div>
          <h2 className="home-main-card-title">{t('home.casesMgmt')}</h2>
          <p className="home-main-card-desc">{t('home.casesDesc')}</p>
          <div className="home-main-card-actions">
            <Link to="/cases" className="btn btn-primary home-btn">{t('home.viewCases')}</Link>
            <Link to="/cases/new" className="btn btn-secondary home-btn">{t('home.newCase')}</Link>
          </div>
        </div>

        <div className="home-side-cards">
          <Link to="/agent" className="home-side-card">
            <span className="home-side-card-icon">🤖</span>
            <div>
              <div className="home-side-card-title">{t('home.agentTitle')}</div>
              <div className="home-side-card-desc">{t('home.agentDesc')}</div>
            </div>
          </Link>
          <Link to="/lab-documents" className="home-side-card">
            <span className="home-side-card-icon">📚</span>
            <div>
              <div className="home-side-card-title">{t('home.labDocsTitle')}</div>
              <div className="home-side-card-desc">{t('home.labDocsDesc')}</div>
            </div>
          </Link>
        </div>
      </div>

      <p className="home-disclaimer">{t('home.disclaimer')}</p>
    </div>
  );
}

export default Home;
