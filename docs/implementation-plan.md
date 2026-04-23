# LaserClaw MVP Implementation Plan

## Overview
LaserClaw is a vertical AI-agent application for laser experiment assistance. This plan outlines the concrete implementation steps to build a production-ready MVP.

## Success Criteria (16 items)
1. ✅ Clean, modular, well-documented codebase
2. ✅ App runs locally with Docker Compose
3. ✅ Working FastAPI backend
4. ✅ Working React frontend
5. ✅ PostgreSQL integrated correctly
6. ✅ User can create, view, edit, delete experiment cases
7. ✅ User can enter experiment goals, cavity type, key parameters, symptoms
8. ✅ System generates structured experiment plan
9. ✅ System generates ReZonator schema/template draft
10. ✅ System generates troubleshooting suggestions from symptoms
11. ✅ System generates and saves experiment report
12. ✅ Users can upload and view attachments
13. ✅ Repo includes seeded demo data
14. ✅ AI features support mock/demo mode
15. ✅ README includes overview, architecture, setup, demo flow, roadmap
16. ✅ Core backend tests pass

## Architecture

### Tech Stack
- **Backend**: FastAPI + SQLAlchemy + Pydantic
- **Frontend**: React 18 + Vite + React Router + Axios
- **Database**: PostgreSQL 15
- **Deployment**: Docker Compose
- **Storage**: Local filesystem for attachments
- **AI Provider**: Abstraction layer with mock provider for demo mode

### Directory Structure
```
LaserClaw/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI应用入口
│   │   ├── config.py            # 配置管理
│   │   ├── database.py          # 数据库连接
│   │   ├── models/              # SQLAlchemy模型
│   │   ├── schemas/             # Pydantic模式
│   │   ├── api/                 # API路由
│   │   ├── services/            # 业务逻辑
│   │   │   ├── planner.py       # 实验计划生成
│   │   │   ├── rezonator.py    # ReZonator模板生成
│   │   │   ├── troubleshooter.py # 故障排查
│   │   │   └── reporter.py      # 报告生成
│   │   └── providers/           # AI提供者抽象
│   ├── tests/                   # pytest测试
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── pages/               # 页面组件
│   │   ├── components/          # 可复用组件
│   │   └── api/                 # API客户端
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
├── docker-compose.yml
├── docs/
│   ├── implementation-plan.md
│   └── BLOCKERS.md
├── README.md
└── CLAUDE.md
```

## Phase 1: Foundation (Tasks #1, #2)

### 1.1 Backend Scaffolding
- Create FastAPI application structure
- Set up SQLAlchemy with PostgreSQL
- Define database models:
  - `ExperimentCase`: id, title, description, cavity_type, goal, parameters (JSON), symptoms (JSON), created_at, updated_at
  - `Attachment`: id, case_id, filename, filepath, file_type, uploaded_at
  - `GeneratedContent`: id, case_id, content_type (plan/rezonator/troubleshooting/report), content (JSON), generated_at
- Create Pydantic schemas for request/response validation
- Set up CORS middleware

### 1.2 Frontend Scaffolding
- Initialize Vite + React project
- Set up React Router for navigation
- Create basic layout with dark theme (#13111c background)
- Add "[Fufan Lab]" prefix to HTML title
- Set up Axios for API calls

### 1.3 Docker Compose Setup
- PostgreSQL service with volume persistence
- Backend service with hot reload
- Frontend service with hot reload
- Network configuration
- Environment variables

### 1.4 Database Initialization
- Alembic migrations setup
- Initial schema creation
- Connection testing

## Phase 2: Core CRUD (Task #3)

### 2.1 Backend API Endpoints
- `POST /api/cases` - Create experiment case
- `GET /api/cases` - List all cases
- `GET /api/cases/{id}` - Get case details
- `PUT /api/cases/{id}` - Update case
- `DELETE /api/cases/{id}` - Delete case

### 2.2 Frontend Case Management
- Cases list page with table/cards
- Case detail page
- Case creation form
- Case edit form
- Delete confirmation dialog

## Phase 3: Experiment Intake (Task #4)

### 3.1 Structured Input Form
- Experiment goal (text area)
- Cavity type (dropdown: linear/ring/bow-tie/custom)
- Key parameters (dynamic key-value pairs):
  - Wavelength
  - Pump power
  - Crystal type
  - Mirror specifications
  - Cavity length
- Observed symptoms (multi-select + custom text):
  - No output
  - Unstable output
  - Mode hopping
  - Thermal effects
  - Alignment drift
  - Custom symptom

### 3.2 Backend Validation
- Parameter validation rules
- Symptom categorization
- Data persistence

## Phase 4: AI Features (Task #5)

### 4.1 Provider Abstraction
```python
# providers/base.py
class AIProvider(ABC):
    @abstractmethod
    async def generate_plan(self, case_data: dict) -> dict:
        pass

    @abstractmethod
    async def generate_rezonator_schema(self, case_data: dict) -> dict:
        pass

    @abstractmethod
    async def generate_troubleshooting(self, symptoms: list) -> dict:
        pass

    @abstractmethod
    async def generate_report(self, case_data: dict) -> dict:
        pass
```

### 4.2 Mock Provider Implementation
- Rule-based plan generation with templates
- ReZonator schema templates based on cavity type
- Symptom-to-solution mapping table
- Report template with placeholders
- All outputs labeled as "启发式建议" (heuristic suggestion)

### 4.3 Service Layer
- `PlannerService`: Generates step-by-step experiment plan
- `RezonatorService`: Generates ReZonator schema/template draft
- `TroubleshooterService`: Analyzes symptoms and suggests solutions
- `ReporterService`: Generates structured experiment report

### 4.4 API Endpoints
- `POST /api/cases/{id}/generate-plan`
- `POST /api/cases/{id}/generate-rezonator`
- `POST /api/cases/{id}/generate-troubleshooting`
- `POST /api/cases/{id}/generate-report`

## Phase 5: Attachments (Task #6)

### 5.1 Backend Implementation
- File upload endpoint: `POST /api/cases/{id}/attachments`
- File download endpoint: `GET /api/attachments/{id}`
- File list endpoint: `GET /api/cases/{id}/attachments`
- File delete endpoint: `DELETE /api/attachments/{id}`
- Local storage in `backend/uploads/` directory
- File type validation (images, PDFs, text files, .rez files)
- File size limits

### 5.2 Frontend Implementation
- File upload component with drag-and-drop
- Attachment list with preview
- Image viewer
- File download links

## Phase 6: Demo Data (Task #7)

### 6.1 Seed Script
Create `backend/seed_data.py` with 3-5 sample cases:
1. **Ti:Sapphire Ring Cavity** - Successful alignment case
2. **Nd:YAG Linear Cavity** - Troubleshooting case with thermal issues
3. **OPO Bow-tie Cavity** - Complex multi-parameter case
4. **Fiber Laser System** - Custom cavity type example
5. **Mode-locked Laser** - Advanced case with multiple symptoms

### 6.2 Sample Generated Content
- Pre-generated plans for each case
- Pre-generated ReZonator schemas
- Pre-generated troubleshooting suggestions
- Pre-generated reports

## Phase 7: Frontend Integration (Task #8)

### 7.1 Pages
- Home/Dashboard: Recent cases, quick actions
- Cases List: All experiment cases with search/filter
- Case Detail: Full case view with tabs:
  - Overview
  - Experiment Plan
  - ReZonator Schema
  - Troubleshooting
  - Report
  - Attachments
- New Case: Creation form
- Edit Case: Edit form

### 7.2 Components
- CaseCard: Case summary card
- ParameterEditor: Key-value pair editor
- SymptomSelector: Multi-select with custom input
- GeneratedContentViewer: Display AI-generated content with disclaimer
- AttachmentUploader: File upload with preview

### 7.3 Styling
- Dark theme with #13111c background
- Light text colors for readability
- Consistent spacing and typography
- Responsive design

## Phase 8: Testing (Task #9)

### 8.1 Backend Tests
- Model tests: CRUD operations
- API tests: All endpoints
- Service tests: AI generation logic
- Integration tests: Database operations

### 8.2 Test Coverage
- Aim for >80% coverage on critical paths
- Mock external dependencies
- Test error handling

## Phase 9: Documentation (Task #10)

### 9.1 README.md
- Project overview and motivation
- Architecture diagram (ASCII or link to image)
- Tech stack
- Setup instructions:
  - Prerequisites
  - Clone repository
  - Environment variables
  - Docker Compose commands
- Demo flow walkthrough
- Screenshots/placeholders
- Roadmap for future features
- Contributing guidelines
- License

### 9.2 Code Documentation
- Docstrings in Chinese for all functions
- Inline comments for complex logic
- API documentation (auto-generated from FastAPI)

## Phase 10: Final Verification (Task #11)

### 10.1 Success Criteria Checklist
Go through all 16 criteria one by one:
1. ✅ Clean, modular, well-documented codebase
2. ✅ App runs locally with Docker Compose
3. ✅ Working FastAPI backend
4. ✅ Working React frontend
5. ✅ PostgreSQL integrated correctly
6. ✅ User can create, view, edit, delete experiment cases
7. ✅ User can enter experiment goals, cavity type, key parameters, symptoms
8. ✅ System generates structured experiment plan
9. ✅ System generates ReZonator schema/template draft
10. ✅ System generates troubleshooting suggestions from symptoms
11. ✅ System generates and saves experiment report
12. ✅ Users can upload and view attachments
13. ✅ Repo includes seeded demo data
14. ✅ AI features support mock/demo mode
15. ✅ README includes overview, architecture, setup, demo flow, roadmap
16. ✅ Core backend tests pass

### 10.2 Integration Testing
- Full workflow test: Create case → Generate plan → Generate ReZonator → Troubleshoot → Generate report → Upload attachment
- Docker Compose startup test
- Database persistence test
- API endpoint smoke tests

### 10.3 Polish
- Fix any remaining bugs
- Improve error messages
- Add loading states
- Improve UI/UX

## Implementation Order

1. ✅ Create implementation plan (Task #1)
2. Set up project structure and Docker Compose (Task #2)
3. Implement experiment case CRUD (Task #3)
4. Implement structured experiment intake (Task #4)
5. Implement AI features with mock provider (Task #5)
6. Implement attachment handling (Task #6)
7. Add seeded demo data (Task #7)
8. Build React frontend UI (Task #8)
9. Add backend tests (Task #9)
10. Write comprehensive README (Task #10)
11. Final verification and polish (Task #11)

## Risk Mitigation

### Potential Blockers
- Docker Compose networking issues on Windows
- PostgreSQL connection issues
- File upload size limits
- CORS configuration

### Mitigation Strategies
- Test Docker Compose early
- Use explicit network configuration
- Document all environment variables
- Add comprehensive error handling
- Create BLOCKERS.md for tracking issues

## Definition of Done

The MVP is complete when:
- All 16 success criteria are met
- `docker-compose up` starts the full stack
- A user can complete the full workflow without errors
- Tests pass
- README is complete and accurate
- Code is clean and documented in Chinese
- No critical bugs remain

## Next Steps After MVP

Not in scope for MVP, but future enhancements:
- Real AI provider integration (OpenAI, Anthropic, etc.)
- Advanced multi-agent orchestration
- Hardware control integration
- Cloud deployment
- User authentication
- Collaborative features
- Advanced visualization
- Export to various formats
