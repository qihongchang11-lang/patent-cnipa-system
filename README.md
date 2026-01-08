# CNIPA Patent System

A comprehensive system for processing China National Intellectual Property Administration (CNIPA) patent applications with automated workflows, quality checks, and document generation.

## Overview

This system provides an end-to-end solution for patent application processing through CNIPA, featuring:

- **High-quality 4-piece generation**: specification / claims / abstract / disclosure
- **Quality gates**: multi-check scoring, issues, and recommendations
- **Dual input**: structured form fields or uploaded `txt/md/docx`
- **Deliverables**: `patent.docx` + `preview.md` + `quality_report.json` (zipped)

Note: the current stable delivery path is **Python (FastAPI + Streamlit)**. The Node.js job-card/orchestrator parts are experimental.

## 📁 Repository Structure

```
patent-cnipa-system/
├── jobcards/                 # Task cards for orchestration
├── schema/                   # JSON schemas for data validation
├── rules/                    # Patent rules and regulations
├── src/
│   ├── core/                 # Core patent processing modules
│   ├── checks/               # Quality gate checkers
│   ├── generators/           # Document generators
│   ├── utils/                # Utility functions
│   └── orchestrator/         # Pipeline orchestration
├── tests/fixtures/           # Test data and examples
├── data/drafts/              # Input patent drafts
├── .github/workflows/        # CI/CD pipelines
├── scripts/                  # Helper scripts
└── docs/                     # Documentation
```

## Installation

### Prerequisites

- Python (v3.9+)
- Git

Optional:
- Node.js (v16+) (experimental scripts only)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/your-org/patent-cnipa-system.git
cd patent-cnipa-system
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Quick Start (Python)

### Start API
```bash
python api_main.py
```

### Start UI (Streamlit)
```bash
streamlit run patent_streamlit_app.py
```

The UI calls the API and lets you download a zip containing `patent.docx`, `preview.md`, and `quality_report.json`.

## LLM Configuration (Beginner Friendly)

Goal: enable DeepSeek (or any OpenAI-compatible provider) by editing **one file**: `.env`.

1) Create `.env` from the template:
   - Windows PowerShell: `powershell -ExecutionPolicy Bypass -File scripts/setup_env.ps1`
   - Or manually copy `patent-cnipa-system/.env.example` → `patent-cnipa-system/.env`

2) Edit `.env` (do NOT commit it):
```bash
notepad .env
```

3) Start API:
```bash
python api_main.py
```

At startup the API logs (without secrets) whether LLM is enabled; if not, it logs: `LLM disabled, falling back to rules`.

This project uses an OpenAI-compatible SDK; any compatible provider can be used via `LLM_BASE_URL`.

## Verification (Phase 1.1)

Dual-mode verification script:

```bash
python scripts/test_ai_pipeline.py --mode=rules
python scripts/test_ai_pipeline.py --mode=llm
```

- `--mode=rules`: forces bypass of LLM (asserts `audit.extraction.source == rules`)
- `--mode=llm`: requires real LLM configuration (asserts extraction + claims generation use `llm`)

## Audit & Soft-Fail Contract

- Soft fail: unless input is completely invalid, the system always produces outputs and a `quality_report.json`.
- Every run persists an `audit` section in `quality_report.json`:
  - `audit.run_trace_id`: per-run id
  - `audit.extraction.source`: `llm` or `rules`
  - `audit.extraction.trace_id`: trace id (always present)
  - `audit.generation.claims.source` / `audit.generation.abstract.source`: `llm` or `rules`
  - `audit.llm`: provider/base_url/model (never includes API keys)
- `quality_report.json` also includes `kpis` (claims counts, avg length, term consistency score).

## Quick Start (Node.js, experimental)

### Validate a Patent Application
```bash
node scripts/validate-application.js tests/fixtures/sample-patent-application.json
```

### Process a Patent Using Orchestrator
```bash
node scripts/orchestrate-patent.js data/drafts/your-application.json --job-card=patent-application-processing
```

### Start the System
```bash
npm start
```

## 🔧 Configuration

### Environment Variables
Create a `.env` file in the root directory:

```env
NODE_ENV=development
LOG_LEVEL=info
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cnipa_patents
REDIS_URL=redis://localhost:6379
```

### Configuration Files
- `config/default.json`: Default system settings
- `config/development.json`: Development environment overrides
- `config/production.json`: Production environment overrides

## 📋 Core Features

### 1. Patent Application Processing Pipeline
Comprehensive workflow covering:
- Application Receipt & Validation
- Formal Requirements Check
- Substantive Examination
- Quality Review
- Office Action Generation
- Applicant Response Processing
- Final Decision
- Document Archival

### 2. Validation & Quality Control
- **Schema Validation**: Strict JSON Schema compliance
- **Business Rule Validation**: CNIPA-specific requirements
- **Format Validation**: Document format and language checks
- **Dependency Validation**: Claim dependency analysis
- **Classification Validation**: IPC/CPC code validation

### 3. Document Generation
- Office Action generation
- Notification letters
- Patent grant documents
- Rejection decisions
- Multilingual support (Chinese/English)
- Digital signatures and certifications

### 4. Integration Capabilities
- XML document processing
- PDF generation and manipulation
- Database integration
- External API connectivity
- File system monitoring

## 🔍 Usage Examples

### Basic Patent Validation
```javascript
const PatentValidator = require('./src/checks/patent-validator');

const validator = new PatentValidator();
const result = await validator.validateApplication(patentData);

if (result.valid) {
    console.log('Application is valid');
} else {
    console.log('Validation errors:', result.errors);
}
```

### Job Card Validation
```bash
node scripts/validate-jobcard.js jobcards/patent-application-processing.json
```

### Custom Workflow Creation
Create your own workflow by adding a new job card:

```json
{
  "id": "custom-patent-process",
  "name": "Custom Patent Processing",
  "version": "1.0.0",
  "type": "workflow",
  "steps": [
    // Your custom steps here
  ]
}
```

## 🧪 Testing

### Run All Tests
```bash
npm test
```

### Run Specific Test Suite
```bash
npm run test:unit
npm run test:integration
npm run test:e2e
```

### Test Coverage
```bash
npm run coverage
```

## 📝 API Documentation

### REST API Endpoints

#### POST /api/validate-patent
Validate a patent application
```json
{
  "application": { /* patent data */ },
  "options": {
    "strict": true
  }
}
```

#### POST /api/orchestrate
Start patent processing orchestration
```json
{
  "application": { /* patent data */ },
  "jobCardId": "patent-application-processing",
  "options": {}
}
```

#### GET /api/status/:id
Check orchestration status

### WebSocket API
Real-time updates during patent processing
```javascript
ws.on('patent-update', (data) => {
    console.log('Patent processing update:', data);
});
```

## 🏗️ Architecture

### System Architecture
- **Microservices**: Modular, container-ready design
- **Event-Driven**: Asynchronous processing with message queues
- **Scalable**: Horizontal scaling capabilities
- **Fault-Tolerant**: Robust error handling and retry mechanisms
- **Monitorable**: Comprehensive logging and metrics

### Technology Stack
- **Backend**: Node.js, Express.js, FastAPI (Python)
- **Validation**: JSON Schema, AJV
- **Orchestration**: Custom workflow engine
- **Storage**: File system (expandable to databases)
- **CI/CD**: GitHub Actions
- **Testing**: Jest, Pytest

## 🔒 Security

- Input validation and sanitization
- Schema-based data validation
- Audit logging for all operations
- Role-based access control ready
- API rate limiting built-in
- Secure document handling

## 📊 Monitoring

The system provides comprehensive monitoring capabilities:

- **Metrics**: Processing duration, success rates, error counts
- **Alerts**: Automatic notifications for failures and timeouts
- **Reports**: Detailed processing reports and analytics
- **Dashboards**: Real-time status monitoring (expandable)

## 🔧 Extending the System

### Adding Custom Validators
```javascript
class MyCustomValidator {
    async validate(data) {
        // Your validation logic here
        return {
            valid: true,
            errors: [],
            recommendations: []
        };
    }
}

// Register with the system
system.validator.register('my-custom-validator', MyCustomValidator);
```

### Adding Custom Job Cards
1. Create a new JSON file in `jobcards/`
2. Follow the job card schema structure
3. Add custom workflow steps
4. Test with validation script

### Adding New Document Generators
```javascript
class MyDocumentGenerator {
    async generate(data, template) {
        // Your generation logic here
        return generatedDocument;
    }
}
```

## 🌐 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Write tests for new features
- Follow the existing code style
- Update documentation as needed
- Run all tests before submitting PR

## 📚 Documentation

- [Architecture Guide](docs/architecture.md)
- [API Reference](docs/api-reference.md)
- [Configuration Guide](docs/configuration.md)
- [Development Guide](docs/development.md)
- [Deployment Guide](docs/deployment.md)

## 🐛 Troubleshooting

### Common Issues

**Q: Validation is failing for a valid application**
A: Check the detailed validation report and ensure all required fields are present according to the schema.

**Q: Job card is not loading**
A: Verify the job card JSON format and run validation using the validation script.

**Q: System is not processing applications**
A: Check the logs for error messages and ensure the input directory is properly configured.

### Debug Mode
Enable debug logging by setting environment variable:
```bash
LOG_LEVEL=debug npm start
```

## 📞 Support

- Create an issue for bug reports
- Use discussions for questions
- Check existing issues before creating new ones

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- CNIPA for patent processing requirements
- Patent examination community for feedback
- Open source contributors

---

**Disclaimer**: This system is designed to assist in patent application processing. Final decisions should always be verified by qualified patent examiners and legal professionals.
