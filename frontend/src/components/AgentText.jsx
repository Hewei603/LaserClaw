import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function AgentText({ children }) {
  return <div className="wb-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
    table: ({ children }) => <div className="wb-table-wrap"><table>{children}</table></div>,
  }}>{children || ''}</ReactMarkdown></div>;
}
