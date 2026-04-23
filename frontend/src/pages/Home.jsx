import React from 'react';
import { Link } from 'react-router-dom';

function Home() {
  return (
    <div>
      <h1>欢迎使用 LaserClaw</h1>
      <p style={{ marginTop: '1rem', marginBottom: '2rem', color: '#b0b0b0' }}>
        LaserClaw 是一个垂直AI代理应用，用于激光实验辅助。
        它提供实验计划、ReZonator模式草稿、故障排查、案例记录和报告生成等功能。
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
        <div className="card">
          <h2 className="card-title">🔬 实验案例管理</h2>
          <p className="card-content">
            创建、查看、编辑和删除激光实验案例。记录实验目标、腔型、参数和观察到的症状。
          </p>
          <Link to="/cases" className="btn btn-primary" style={{ marginTop: '1rem', display: 'inline-block' }}>
            查看案例
          </Link>
        </div>

        <div className="card">
          <h2 className="card-title">📋 实验计划生成</h2>
          <p className="card-content">
            基于实验目标和腔型，自动生成结构化的实验步骤计划。
          </p>
        </div>

        <div className="card">
          <h2 className="card-title">🎯 ReZonator模式草稿</h2>
          <p className="card-content">
            根据腔型和参数，生成ReZonator模式/模板草稿，加速实验设计。
          </p>
        </div>

        <div className="card">
          <h2 className="card-title">🔧 故障排查</h2>
          <p className="card-content">
            基于观察到的症状，提供可能的原因分析和解决方案建议。
          </p>
        </div>

        <div className="card">
          <h2 className="card-title">📊 报告生成</h2>
          <p className="card-content">
            自动生成结构化的实验报告，包含目标、步骤、结果和结论。
          </p>
        </div>

        <div className="card">
          <h2 className="card-title">📎 附件管理</h2>
          <p className="card-content">
            上传和查看实验相关的图片、笔记、数据文件和ReZonator模式文件。
          </p>
        </div>
      </div>

      <div className="disclaimer" style={{ marginTop: '2rem' }}>
        <strong>⚠️ 重要提示：</strong>
        LaserClaw 是实验工作流辅助系统，不是直接硬件控制系统。
        所有AI生成的内容都是启发式建议，需要人工验证。
        不要将生成的内容视为实验验证的结果。
      </div>

      <div style={{ marginTop: '2rem', textAlign: 'center' }}>
        <Link to="/cases/new" className="btn btn-primary" style={{ fontSize: '1.1rem', padding: '0.75rem 2rem' }}>
          创建新案例
        </Link>
      </div>
    </div>
  );
}

export default Home;
