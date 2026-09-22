# Hey Broski Web Frontend

## Project Overview

The Hey Broski web frontend is a React-based chat interface built with Next.js App Router. It provides users with access to their personal admin AI assistant through a polished chat interface.

## Key Features

### Chat Interface
- Real-time chat with AI assistant
- Action card system for task management
- Source-grounded responses with citations
- Approval flows for risky actions

### Demo Mode
- Instant evaluation without real account connections
- Pre-populated demo data (emails, calendar, documents)
- Full feature testing capability

### UI/UX
- Modern, responsive design with Tailwind CSS
- Clean, intuitive interface focused on usability
- Action cards with priority indicators
- Source citations for all responses

## Technical Stack

### Frontend Dependencies
```
React 18+
Next.js with App Router
TypeScript
Tailwind CSS
ChatKit (self-hosted)
shadcn/ui components
lucide-react icons
TanStack Query for server state
Zustand for client state
Zod for schema validation
React Hook Form for forms
Playwright for E2E tests
```

### Architecture
```
Next.js App Router
├── app/
│   ├── page.tsx           # Main chat page
│   └── layout.tsx         # App shell with sidebar
├── src/
│   ├── components/        # Reusable UI components
│   │   ├── chat/          # Chat-specific components
│   │   ├── action-cards/  # Action card UI
│   │   ├── dashboard/     # Dashboard components
│   │   └── layout/        # Layout components
│   ├── lib/              # Custom hooks and utilities
│   │   ├── api.ts         # API client
│   │   ├── schemas.ts     # Type schemas
│   │   └── query-client.ts # TanStack Query config
│   └── styles/           # Global styles
└── public/              # Static assets
```

## Getting Started

### Development
```bash
cd apps/web
pnpm install
pnpm dev
```

### Build for Production
```bash
cd apps/web
pnpm build
```

### Testing
```bash
# E2E tests
cd apps/web
pnpm test:e2e

# Unit tests
cd apps/web
pnpm test:unit

# Component tests
cd apps/web
pnpm test:components
```

## Core Components

### Chat Interface
- **HeyBroskiChat**: Main chat component with message handling
- **ChatMessage**: Individual message display with formatting
- **SourceCitation**: Display source references for AI responses

### Action Cards
- **ActionCard**: Individual action card with approval controls
- **ActionCardList**: Collection of action cards
- **ApprovalModal**: Modal for approving/rejecting actions

### Layout
- **AppShell**: Main application layout with sidebar
- **Sidebar**: Navigation and account management
- **Dashboard**: Overview page with attention summary

### Components
- **AccountBadge**: Display connected account status
- **AccountConnectionCard**: Account connection UI
- **DailyBriefPanel**: Daily attention summary
- **AttentionSummary**: Component for displaying attention items
- **DocumentUpload**: File upload component
- **DocumentTable**: Document listing and management

## API Integration

The frontend connects to the Hey Broski backend API:

### Key Endpoints
```
GET /api/health                    # Service health check
POST /api/chat/sessions          # Create chat session
GET /api/chat/sessions          # List sessions
POST /api/chat/sessions/{id}/messages # Send message
GET /api/actions                 # List action cards
POST /api/actions/{id}/approve   # Approve action
POST /api/approvals/pending      # Get pending approvals
POST /api/approvals/{id}/approve # Approve approval request
GET /api/accounts                # List connected accounts
POST /api/accounts/demo/enable   # Enable demo mode
```

### Chat Flow
1. **Session Initialization**: Create a new chat session on first load
2. **Message Sending**: Send user messages to the backend
3. **Response Handling**: Display AI responses with sources and action cards
4. **Action Card Management**: Approve, dismiss, or snooze action cards
5. **Source Citation**: Click to expand source references

## Demo Mode

### Enabling Demo Mode
1. Click "Enable Demo" button in the header
2. Full demo data loads automatically:
   - 4 demo emails (various priorities)
   - 2 calendar events (with conflict)
   - 2 documents (with due dates)

### Demo Features
- **No OAuth Required**: Works instantly without real Gmail/Outlook accounts
- **Full Functionality**: All features testable with demo data
- **Realistic Scenarios**: Credit card bills, renewals, follow-ups, calendar conflicts
- **Source Grounding**: Every response includes demo data sources

### Sample Demo Conversations
```
What needs my attention today?
→ Returns 4 items needing attention with action cards

Who is waiting on me?
→ Detects unanswered emails and commitments

Find upcoming renewals and deadlines
→ Shows due dates from emails and documents

Summarize important unread emails
→ Lists all unread emails with priorities
```

## Action Cards System

### Card Types
- **reply_needed**: Emails requiring a response
- **follow_up**: Follow-up tasks or commitments
- **deadline**: Time-sensitive tasks
- **renewal**: Subscription or service renewals
- **calendar_conflict**: Overlapping calendar events
- **document_expiry**: Document warranties or expiries
- **invoice**: Billing and payment tasks
- **meeting_prep**: Meeting preparation items
- **automation_suggestion**: Automation recommendations
- **custom**: User-created action cards

### Card Priorities
- **urgent**: Due within 24 hours or high-impact conflict
- **high**: Due within 3 days, important sender, money/legal/work obligation
- **medium**: Due within 14 days or likely useful follow-up
- **low**: Informational or low confidence

### Approval Flow
1. **System Creates**: AI creates action cards with suggested actions
2. **User Review**: Cards appear in sidebar with details
3. **Approve/Reject**: Click buttons to approve, edit, snooze, or dismiss
4. **Audit Trail**: All approval decisions logged for security
5. **Execution**: Approved actions trigger through MCP tools or n8n

## Security and Privacy

### Data Protection
- **Local-First**: All data stored locally by default
- **No Cloud Dependencies**: Zero paid LLM API calls
- **Secure Token Storage**: OS keychain for OAuth tokens
- **Source Grounding**: No exposure of raw email bodies or document content

### Access Control
- **Multi-Account Support**: Personal, work, and other account types
- **Account Labeling**: Clear display of email source accounts
- **Permission Management**: Minimum scopes required
- **Audit Logging**: All tool calls and approvals logged

## Performance Optimization

### For Better UX
- **Lazy Loading**: Load additional messages on demand
- **WebSocket**: Real-time updates for long-polling scenarios
- **Caching**: Cache frequent responses and action cards
- **Compression**: Minify and compress assets

### Mobile Considerations
- **Responsive Design**: Works on tablets and mobile devices
- **Touch Targets**: Appropriate button sizes for touch
- **Gesture Support**: Swipe actions for dismissing cards
- **Voice Input**: Speech-to-text for accessibility

## Internationalization

### Language Support
- **English**: Primary language
- **Spanish**: Support for Spanish-speaking users
- **French**: Support for French-speaking users
- **Chinese**: Support for Chinese-speaking users

### Number and Date Formatting
- **Locale-aware**: Respects user locale settings
- **Consistent**: Uniform formatting across the app
- **Accessibility**: Screen reader compatible

## Testing Strategy

### Unit Tests
```
components/
├── chat/
│   ├── ChatMessage.test.tsx
│   └── HeyBroskiChat.test.tsx
├── action-cards/
│   ├── ActionCard.test.tsx
│   └── ActionCardList.test.tsx
└── hooks/
    └── useChat.test.tsx
```

### Integration Tests
```
api/
├── chat.test.ts
├── actions.test.ts
└── approvals.test.ts
```

### E2E Tests
```
playwright/
├── chat-flow.spec.ts
├── demo-mode.spec.ts
└── action-cards.spec.ts
```

## Deployment

### Production Build
```bash
# Build both frontend and backend
cd hey-broski
docker compose up --build
```

### Docker Compose
The project includes a complete docker-compose.yml with:
- **web**: Next.js frontend (port 3000)
- **api**: FastAPI backend (port 8000)
- **ollama**: Local LLM service (port 11434)
- **n8n**: Automation engine (port 5678)

### Environment Variables
```bash
# Next.js
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# App-wide
HEYBROSKI_ENV=production
HEYBROSKI_DATA_DIR=/data/heybroski
```

## Customization

### Theme Customization
```css
/* Override Tailwind config for custom colors */
```

### Feature Flags
```typescript
const features = {
  demoMode: true,
  gmailConnector: true,
  outlookConnector: true,
  localDocuments: true,
  n8nIntegration: true,
  mcpTools: true,
};
```

### API Extensions
Add new endpoints by:
1. Implementing in backend api_routes/
2. Adding TypeScript types to shared package
3. Updating frontend API client

## Troubleshooting

### Common Issues

#### "Cannot connect to backend"
- Ensure backend is running: `docker compose up -d`
- Check network connectivity
- Verify environment variables

#### "Chat stuck loading"
- Check browser console for error messages
- Refresh the page
- Clear browser cache

#### "Action cards not updating"
- Check if user has appropriate permissions
- Verify account connections
- Check demo mode status

### Debug Tools
- **Browser DevTools**: Network and console tabs
- **Docker Logs**: `docker compose logs -f web api`
- **Local Storage**: Check for API tokens or state
- **Network Monitor**: Verify API calls and responses

## Future Enhancements

### Phase 1 (MVP)
- [x] Basic chat interface ✅
- [x] Demo mode with dummy data ✅
- [x] Action cards system ✅
- [x] Source citations ✅

### Phase 2 (Expansion)
- Tauri desktop app integration
- Local notifications
- Google Drive/OneDrive integration
- Advanced semantic person memory graph
- Meeting prep packs

### Phase 3 (Advanced)
- Invoice tracker dashboard
- Subscription tracker dashboard
- Plugin marketplace for Hey Broski tools
- Advanced RAG evaluation dashboard

## Version Information

- **Version**: 0.1.0 (MVP)
- **Framework**: Next.js 14 with App Router
- **Build**: Production-ready with Docker support
- **License**: Proprietary

---

Built with zero paid APIs, local LLMs, and complete data ownership. Start your personal admin experience with Hey Broski today!
