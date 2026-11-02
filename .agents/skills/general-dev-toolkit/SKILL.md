---
name: general-dev-toolkit
description: "通用开发工具箱：全栈开发（Clean Architecture / DDD、TDD 与测试分层、安全、DevOps、代码质量）；代码优化（性能剖析与重构杠杆）；代码符号（符号级导航与安全编辑配方）；提示词与任务规格分析。用于端到端搭建或评审 Web 应用、定位性能热点、做符号级精确改动、或澄清含糊的任务描述。"
agent_created: true
---

# 通用开发工具箱（全栈开发 / 代码优化 / 代码符号 / 提示词分析）

## 本轮合并（2026-10-29）

本 Skill 是 2026-10-29 同类合并的归并结果。以下源能力的完整 playbook 已收编进本目录，按需加载 `references/<name>/SKILL.md`，不要把全部参考文档读进上下文：

- `code-optimization` → `references/code-optimization/SKILL.md`
- `code-symbols` → `references/code-symbols/SKILL.md`
- `analyze-prompt` → `references/analyze-prompt/SKILL.md`
- 宿主：本目录 SKILL.md 主体来自 `fullstack-dev`，目录名按合并后语义重命名。

被吸收源技能的 frontmatter 仅在其原子文档内作历史留存；本目录的 `name` 与路由表为准。跨组的兄弟能力引用见各参考文档内的重定向注。

This skill provides expert guidance for building complete, production-ready web applications. It combines best practices from Clean Architecture, Domain-Driven Design, Test-Driven Development, security principles, and DevOps practices.

## When to Use This Skill

- Building new web applications (frontend + backend)
- Implementing features with architectural best practices
- Setting up testing strategies (unit, integration, e2e)
- Improving code quality and security
- Deploying applications to cloud infrastructure
- Optimizing application performance
- Creating data visualizations and dashboards
- Writing maintainable, scalable code

## Core Principles

### 1. Architecture & Design (Clean Architecture + DDD)

**Project Structure:**
```
src/
├── domain/           # Core business logic (entities, value objects)
├── application/      # Use cases, services, DTOs
├── infrastructure/   # Database, external services, APIs
├── presentation/     # HTTP handlers, controllers, middleware
└── shared/          # Utilities, constants, helpers
```

**Naming Conventions:**
- ✅ Use domain-specific names: `OrderCalculator`, `UserAuthenticator`, `PaymentProcessor`
- ❌ Avoid generic names: `utils.js`, `helpers.js`, `common.js`

**Key Rules:**
- Early return pattern: Always use early returns for better readability
- Single Responsibility: Each class/function has ONE clear purpose
- Dependency Injection: Pass dependencies explicitly, don't create inside functions
- Library-First: Search for existing solutions BEFORE writing custom code
  - Auth → Use Auth0, Supabase, or NextAuth
  - Retry Logic → Use cockatiel or p-retry
  - Form Validation → Use Zod, Yup, or Joi
  - State Management → Use Redux, Zustand, or Jotai
  - ORM → Use Prisma, TypeORM, or Sequelize

**Code Size Limits:**
- Functions: max 50 lines
- Components: max 80 lines
- Files: max 200 lines
- Nesting: max 3 levels deep

### 2. Frontend Development (React + Modern Stack)

**React Components:**
```typescript
// ✅ GOOD: Functional component with clear purpose
interface UserCardProps {
  userId: string;
  onEdit: (id: string) => void;
}

export function UserCard({ userId, onEdit }: UserCardProps) {
  const user = useQuery(['user', userId], fetchUser);
  
  if (user.isLoading) return <Skeleton />;
  if (user.isError) return <ErrorFallback error={user.error} />;
  
  return (
    <div className="card">
      <h3>{user.data.name}</h3>
      <button onClick={() => onEdit(userId)}>Edit</button>
    </div>
  );
}

// ❌ AVOID: Overly complex, mixed concerns
function UserComponent({ data, onAction, ...props }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // ... 200 lines of mixed logic
}
```

**Component Structure:**
- Keep components focused (max 80 lines)
- Use React hooks properly (useQuery, useState, useEffect)
- Extract complex logic to custom hooks or services
- Use TypeScript for type safety
- Apply styling consistently (Tailwind CSS recommended)

**State Management:**
- Local state (useState) for simple component state
- React Query (TanStack Query) for server state
- Zustand/Redux for complex global state
- Context API for theme/auth state

### 3. Backend Development (Node.js/Express or Framework of Choice)

**API Design:**
```typescript
// Use RESTful conventions and proper HTTP methods
GET    /api/users           // List all users
POST   /api/users           // Create user
GET    /api/users/:id       // Get single user
PUT    /api/users/:id       // Update user
DELETE /api/users/:id       // Delete user
```

**Error Handling:**
```typescript
// ✅ Structured error handling
try {
  const user = await userService.getUser(id);
  if (!user) {
    throw new NotFoundError(`User ${id} not found`);
  }
  return user;
} catch (error) {
  if (error instanceof NotFoundError) {
    res.status(404).json({ error: error.message });
  } else if (error instanceof ValidationError) {
    res.status(400).json({ error: error.message });
  } else {
    res.status(500).json({ error: 'Internal server error' });
  }
}
```

**Database:**
- Use an ORM (Prisma, TypeORM, Sequelize) - never write raw SQL
- Apply migrations for schema changes
- Use proper indexes for performance
- Implement soft deletes where appropriate
- Use transactions for multi-step operations

**Authentication & Security:**
```typescript
// Use established libraries
// Auth: NextAuth, Auth0, Supabase, Passport
// Session: express-session + redis or JWT with refresh tokens
// Password hashing: bcrypt
// API keys: stored in secure vault (HashiCorp Vault, AWS Secrets Manager)

// ✅ Always validate and sanitize input
const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

const validated = schema.parse(req.body);
```

### 4. Testing Strategy (Test-Driven Development)

**Testing Pyramid:**
```
        UI/E2E Tests (10%)
       /              \\
      /                \\
  Integration Tests (30%)
    /                   \\
   /                     \\
Unit Tests (60%)
```

**Unit Tests:**
```typescript
// Test individual functions/methods
describe('OrderCalculator', () => {
  it('should calculate total with tax', () => {
    const order = { items: [{ price: 100 }] };
    const total = calculateTotal(order);
    expect(total).toBe(115); // 100 + 15% tax
  });

  it('should apply discount', () => {
    const order = { items: [{ price: 100 }], discount: 0.1 };
    const total = calculateTotal(order);
    expect(total).toBe(103.5); // (100 - 10) * 1.15
  });
});
```

**Integration Tests:**
```typescript
// Test multiple components working together
describe('User Service with Database', () => {
  it('should create and retrieve user', async () => {
    const user = await userService.create({ email: 'test@example.com' });
    const retrieved = await userService.getById(user.id);
    expect(retrieved.email).toBe('test@example.com');
  });
});
```

**E2E Tests (Playwright):**
```typescript
// Test complete user flows
test('user should be able to register and login', async ({ page }) => {
  await page.goto('http://localhost:3000/register');
  await page.fill('input[name="email"]', 'test@example.com');
  await page.fill('input[name="password"]', 'SecurePassword123');
  await page.click('button[type="submit"]');
  
  expect(page.url()).toContain('/dashboard');
});
```

**Test Libraries:**
- Unit: Jest, Vitest
- Integration: Jest with database
- E2E: Playwright, Cypress
- Mocking: Jest, MSW (Mock Service Worker)

### 5. Security & Vulnerability Testing

**FFUF Web Fuzzing for Penetration Testing:**
```bash
# Directory discovery
ffuf -w wordlist.txt -u https://target.com/FUZZ -ac

# API endpoint discovery
ffuf -w api-endpoints.txt -u https://api.target.com/v1/FUZZ -ac

# Parameter fuzzing (requires authentication)
ffuf --request authenticated_req.txt -w params.txt -ac

# IDOR testing (finds insecure direct object references)
ffuf --request req.txt -w user_ids.txt -ac -mc 200
```

**Security Checklist:**
- ✅ Use HTTPS everywhere
- ✅ Implement CORS correctly
- ✅ Use secure headers (CSP, X-Frame-Options, etc.)
- ✅ Hash passwords with bcrypt (12 rounds minimum)
- ✅ Validate and sanitize all inputs
- ✅ Use parameterized queries (ORM handles this)
- ✅ Implement rate limiting on APIs
- ✅ Log security events
- ✅ Regular dependency updates
- ✅ Use security scanning tools (npm audit, Snyk)

### 6. Data Visualization (D3.js or Chart Libraries)

**Chart Selection:**
- Line/Area charts: Time series, trends
- Bar charts: Comparisons, categories
- Pie/Donut charts: Proportions
- Scatter: Correlations
- Heatmaps: Density, patterns
- Network graphs: Relationships

**Example with Recharts (Simpler Alternative):**
```typescript
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';

export function SalesChart({ data }) {
  return (
    <LineChart width={800} height={400} data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="name" />
      <YAxis />
      <Tooltip />
      <Line type="monotone" dataKey="sales" stroke="#8884d8" />
    </LineChart>
  );
}
```

### 7. DevOps & Deployment

**CI/CD Pipeline:**
```yaml
# Example GitHub Actions
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: npm install
      - run: npm run lint
      - run: npm run test
      - run: npm run build

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to AWS
        run: |
          aws s3 cp dist/ s3://my-bucket --recursive
          aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

**Deployment Environments:**
- Development: Local machine + Docker
- Staging: AWS/Vercel/Railway with latest code
- Production: AWS/Vercel/Railway with tagged releases

**Infrastructure as Code (AWS CDK):**
```typescript
// Define infrastructure in code
const app = new cdk.App();
const stack = new cdk.Stack(app, 'fullstack-stack');

const bucket = new s3.Bucket(stack, 'frontend-bucket', {
  websiteIndexDocument: 'index.html',
  publicReadAccess: true,
});

const distribution = new cloudfront.Distribution(stack, 'distribution', {
  defaultBehavior: { origin: new S3Origin(bucket) },
});
```

### 8. Git Workflow

**Branching Strategy (Git Flow):**
```
main (production)
  ├── release/v1.0.0
  │   └── hotfix/critical-bug
  └── develop (staging)
      ├── feature/user-auth
      ├── feature/payment-integration
      └── feature/dashboard
```

**Commit Messages:**
```
feat: add user authentication
fix: correct payment calculation
docs: update API documentation
test: add tests for auth service
refactor: simplify order service
chore: update dependencies
```

**Git Worktrees for Parallel Work:**
```bash
# Create isolated workspace for feature
git worktree add ../feature-branch feature/new-feature

# Switch between features without stashing
cd ../feature-branch
# Work on feature...

# Cleanup
git worktree remove ../feature-branch
```

### 9. Performance Optimization

**Frontend:**
- Code splitting: Load only needed JavaScript
- Lazy loading: Images, components on-demand
- Caching: Static assets with long-lived cache headers
- Minification: Reduce bundle size
- Critical rendering path: Optimize above-fold content

**Backend:**
- Database indexing: Fast queries
- Caching: Redis for frequently accessed data
- Connection pooling: Reuse database connections
- Async operations: Non-blocking I/O
- Load balancing: Distribute traffic

**Monitoring:**
```typescript
// Use Application Performance Monitoring
// Services: New Relic, DataDog, Sentry, LogRocket

// Track key metrics
metrics.recordLatency('api.users.get', duration);
metrics.incrementCounter('api.errors');
metrics.recordGauge('db.connections.active', activeConnections);
```

## Workflow for Building Features

### Step 1: Plan & Design
1. Define requirements and acceptance criteria
2. Sketch API endpoints and data models
3. Design database schema
4. Plan component structure (frontend)

### Step 2: Write Tests First (TDD)
```typescript
// Write test before implementation
describe('createUser', () => {
  it('should create user with valid email', async () => {
    const user = await createUser({ email: 'test@example.com' });
    expect(user.id).toBeDefined();
    expect(user.email).toBe('test@example.com');
  });
});
```

### Step 3: Implement Backend
1. Create database schema/migration
2. Implement service layer
3. Create API endpoints
4. Add authentication/authorization
5. Write integration tests

### Step 4: Implement Frontend
1. Create React components
2. Integrate with API
3. Add form validation
4. Handle errors gracefully
5. Write E2E tests

### Step 5: Security Review
```bash
# Run security checks
npm audit
npx snyk test

# Run FFUF tests on staging
ffuf -w api-wordlist.txt -u https://staging.app/api/FUZZ -ac
```

### Step 6: Deploy & Monitor
1. Run full test suite
2. Build for production
3. Deploy to staging
4. Run E2E tests on staging
5. Deploy to production
6. Monitor metrics and logs

### Step 7: Iterate
1. Gather user feedback
2. Monitor performance
3. Fix bugs and security issues
4. Plan improvements

## Technology Stack Recommendations

### Frontend
- **Framework**: React 18+ with TypeScript
- **State Management**: TanStack Query + Zustand
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui, Radix UI
- **Testing**: Vitest + React Testing Library
- **E2E**: Playwright

### Backend
- **Runtime**: Node.js 18+ or Bun
- **Framework**: Express, NestJS, or FastAPI
- **Database**: PostgreSQL with Prisma ORM
- **Authentication**: NextAuth, Auth0, or Supabase
- **API Documentation**: OpenAPI/Swagger
- **Testing**: Jest, Supertest
- **Logging**: Winston, Pino

### DevOps & Infrastructure
- **Hosting**: AWS, Vercel, Railway, Render
- **Container**: Docker
- **CI/CD**: GitHub Actions, GitLab CI
- **Infrastructure as Code**: AWS CDK or Terraform
- **Monitoring**: DataDog, New Relic, or Sentry
- **Database Hosting**: AWS RDS, Railway, or Supabase

## Common Patterns

### Error Handling
```typescript
// Create custom error classes
class AppError extends Error {
  constructor(public statusCode: number, message: string) {
    super(message);
  }
}

class ValidationError extends AppError {
  constructor(message: string) {
    super(400, message);
  }
}

// Use in middleware
app.use((err, req, res, next) => {
  if (err instanceof AppError) {
    res.status(err.statusCode).json({ error: err.message });
  } else {
    res.status(500).json({ error: 'Internal server error' });
  }
});
```

### Async/Await Best Practices
```typescript
// ✅ Good: Parallel operations when possible
const [user, posts] = await Promise.all([
  getUser(id),
  getPosts(userId),
]);

// ❌ Avoid: Sequential when parallel is possible
const user = await getUser(id);
const posts = await getPosts(user.id);
```

### API Response Format
```typescript
// Consistent response structure
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
  };
  meta?: {
    timestamp: string;
    version: string;
  };
}
```

## Tools & Resources

### Code Quality
- ESLint: Linting
- Prettier: Code formatting
- TypeScript: Type safety
- SonarQube: Code analysis

### Testing
- Jest: Unit testing
- Playwright: E2E testing
- Mock Service Worker: API mocking
- Storybook: Component testing

### Performance
- Lighthouse: Web performance auditing
- WebPageTest: Detailed performance analysis
- Chrome DevTools: Browser debugging
- Bundle Analyzer: JavaScript bundle analysis

### Security
- FFUF: Web fuzzing
- npm audit: Dependency vulnerabilities
- Snyk: Security scanning
- OWASP Top 10: Security best practices

## Notes for Claude

- When building features, emphasize TDD approach
- Always recommend using established libraries instead of custom code
- Ensure proper error handling and validation
- Consider security implications at every step
- Optimize for performance and user experience
- Use TypeScript for type safety
- Follow SOLID principles and Clean Architecture
- Implement proper logging and monitoring
- Write comprehensive tests (unit, integration, E2E)
- Use git best practices and semantic commits
- Document API endpoints with OpenAPI/Swagger
- Consider accessibility (a11y) in frontend development
- Plan for scalability from the start