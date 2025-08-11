# 🎙️ PGL Podcast Outreach Automation System

A comprehensive B2B podcast placement automation platform that leverages AI to match clients with relevant podcasts and streamline the outreach process.

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd "PGL - Postgres"

# Copy environment template and configure
cp podcast_outreach/.env.example podcast_outreach/.env
# Edit .env with your configuration

# Build and run with Docker Compose
cd podcast_outreach
docker-compose up --build

# Access the application
# API: http://localhost:8000
# Documentation: http://localhost:8000/docs
```

### Local Development

```bash
# Navigate to the application directory
cd podcast_outreach

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn main:app --reload
```

## 📋 Features

- **Automated Podcast Discovery**: Integrates with ListenNotes and Podscan APIs
- **AI-Powered Matching**: Uses advanced scoring algorithms to match clients with podcasts
- **Pitch Generation**: Automated personalized pitch creation with multiple templates
- **Campaign Management**: End-to-end campaign workflow from discovery to placement
- **Review System**: Built-in review tasks for quality control
- **Analytics Dashboard**: Track AI usage, costs, and campaign performance
- **CRM Integration**: Syncs with Attio and Instantly.ai

## 🏗️ Architecture

```
podcast_outreach/
├── api/              # FastAPI routes and schemas
├── services/         # Business logic and AI services
├── database/         # PostgreSQL models and queries
├── integrations/     # External API clients
├── templates/        # Web UI templates
└── static/          # CSS/JS assets
```

## 🐳 Docker Deployment

The application is fully containerized for easy deployment:

- **Dockerfile**: Production-ready container with health checks
- **docker-compose.yml**: Complete stack configuration
- **Environment Variables**: Managed via `.env` file

See [podcast_outreach/DOCKER_DEPLOYMENT_GUIDE.md](podcast_outreach/DOCKER_DEPLOYMENT_GUIDE.md) for detailed deployment instructions.

## 📚 Documentation

### Core Documentation
- [API Documentation](API_DOCUMENTATION.md) - Frontend API reference
- [Workflow Documentation](podcast_outreach/WORKFLOW_DOCUMENTATION.md) - System workflows
- [Setup Guide](podcast_outreach/SETUP_AND_DEPLOYMENT_GUIDE.md) - Installation instructions

### Feature Guides
- [Pitch System Documentation](PITCH_SYSTEM_DOCUMENTATION.md) - Complete pitch system guide
- [Frontend Integration Guide](FRONTEND_INTEGRATION_GUIDE.md) - Frontend implementation
- [Review Tasks Flow](REVIEW_TASK_ACCEPT_REJECT_FLOW.md) - Review system documentation

### System Documentation
- [Workflow Self-Healing](podcast_outreach/WORKFLOW_SELF_HEALING.md) - Automatic recovery mechanisms
- [Vetting Score Migration](podcast_outreach/VETTING_SCORE_MIGRATION_SUMMARY.md) - Score system changes (0-100 scale)
- [Enrichment Enhancements](ENRICHMENT_ENHANCEMENTS_V2.md) - Data enrichment features

## 🔧 Configuration

### Required Environment Variables

```env
# Database
PGHOST=your-neon-host
PGDATABASE=your-database
PGUSER=your-username
PGPASSWORD=your-password

# AI Services
GEMINI_API_KEY=your-key
OPENAI_API=your-key
ANTHROPIC_API=your-key

# External APIs
LISTEN_NOTES_API_KEY=your-key
PODSCANAPI=your-key
INSTANTLY_API_KEY=your-key
TAVILY_API_KEY=your-key

# Application
SESSION_SECRET_KEY=your-secret-key
FRONTEND_ORIGIN=http://localhost:5173
```

## 🛠️ Development

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=podcast_outreach
```

### Code Quality
```bash
# Format code
black podcast_outreach/

# Lint
flake8 podcast_outreach/

# Type checking
mypy podcast_outreach/
```

## 📦 Dependencies

- **FastAPI**: Web framework
- **PostgreSQL**: Database (via Neon)
- **SQLAlchemy**: ORM
- **Pydantic**: Data validation
- **AI Libraries**: OpenAI, Anthropic, Google Gemini
- **External Services**: ListenNotes, Podscan, Instantly.ai, Attio

## 🚢 Production Deployment

### Cloud Providers

The application can be deployed to:
- **AWS**: ECS/Fargate with RDS
- **Google Cloud**: Cloud Run with Cloud SQL
- **Azure**: Container Instances with PostgreSQL
- **Heroku**: Container Registry deployment

### Monitoring

- Health check endpoint: `/api-status`
- Structured logging with correlation IDs
- AI usage tracking and cost monitoring

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is proprietary software. All rights reserved.

## 🆘 Support

For issues and questions:
- Check the [documentation](podcast_outreach/WORKFLOW_DOCUMENTATION.md)
- Review [troubleshooting guide](podcast_outreach/DOCKER_DEPLOYMENT_GUIDE.md#troubleshooting)
- Contact the development team

---

**Note**: Archived documentation from previous development phases can be found in the `docs_archive/` directory.