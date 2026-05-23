import React, { createContext, useContext, useState } from 'react';
import { translations } from './i18n';

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState('zh');

  const t = (key) => {
    const parts = key.split('.');
    let obj = translations[lang];
    for (const part of parts) {
      if (obj == null) return key;
      obj = obj[part];
    }
    return obj ?? key;
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
