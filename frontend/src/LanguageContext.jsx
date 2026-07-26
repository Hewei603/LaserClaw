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

  // enum translator: maps backend English enum values to the current language
  const ENUM_ZH = {
    completed: '已完成', failed: '失败', running: '运行中', needs_input: '待补参数',
    pending: '待运行', draft: '草稿', ready: '就绪',
    high: '高', medium: '中', low: '低',
    inside: '带内', outside: '带外', edge: '带边',
    'Mirror M1': '腔镜 M1', 'Mirror M2': '腔镜 M2',
    'Crystal entrance': '晶体入射面', 'Crystal exit': '晶体出射面',
    uncertain: '待确认', damaged: '损坏', ok: '正常',
    private: '私有', project: '项目内', organization: '组织内',
  };
  const te = (value) => (lang === 'zh' && ENUM_ZH[value]) || value;

  return (
    <LanguageContext.Provider value={{ lang, setLang, t, te }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
