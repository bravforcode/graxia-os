# BravOS v3 Monorepo

Enterprise-grade OS automation and orchestration platform.

## Structure

- `apps/`: User-facing applications.
  - `dashboard-web`: React/Next.js dashboard.
  - `gateway-api`: Unified API Gateway.
- `services/`: Core backend services.
  - `identity-broker`: Auth and IAM.
  - `release-control`: Deployment and lifecycle.
  - `agent-mesh`: Distributed agent coordination.
- `packages/`: Shared libraries and protocols.
  - `bwcp-protocol`: BravOS Web Control Protocol.
  - `auth`: Shared authentication logic.
  - `logging`: Enterprise logging utilities.
- `infra/`: Infrastructure as Code (Terraform/K8s).
- `docs/`: Technical documentation.

## Development

### Prerequisites

- Node.js (v18+)
- Python (v3.11+)
- npm workspaces

### Setup

```bash
npm install
# Set up python venv
python -m venv venv
source venv/bin/activate # or venv\Scripts\activate on Windows
pip install black flake8
```

### Standards

- **TypeScript**: ESLint + Prettier
- **Python**: Black + Flake8
- **Commits**: Husky pre-commit hooks for compliance.
