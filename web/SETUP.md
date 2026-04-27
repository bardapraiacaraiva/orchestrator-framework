# Payment & Licensing Setup Guide

## Step 1: Deploy to Vercel

```bash
cd web/
vercel link                    # Link to Vercel project
vercel env add KV_REST_API_URL     # From Vercel KV dashboard
vercel env add KV_REST_API_TOKEN   # From Vercel KV dashboard
vercel env add WEBHOOK_SECRET      # Random string for webhook verification
vercel env add ADMIN_SECRET        # Random string for admin API
vercel --prod                  # Deploy
```

## Step 2: Setup Vercel KV

1. Go to vercel.com → your project → Storage
2. Add "KV" store (powered by Upstash Redis)
3. Copy KV_REST_API_URL and KV_REST_API_TOKEN to env vars

## Step 3: Create Products on LemonSqueezy

1. Go to https://lemonsqueezy.com → Sign up
2. Create Store: "Orchestrator AI"
3. Create 3 Products:

### Product: Orchestrator Pro
- Price: €29/month (recurring)
- Create Variant → note the variant_id
- Description: "3 parallel tasks, playbooks, eval calibration, analytics, priority support"

### Product: Orchestrator Team
- Price: €99/month (recurring)
- Create Variant → note the variant_id
- Description: "5 seats, shared budgets, team dashboards, role-based access"

### Product: Orchestrator Enterprise
- Price: €299/month (recurring)
- Create Variant → note the variant_id
- Description: "50 seats, custom integrations, SLA, dedicated onboarding, white-label"

4. Update `web/api/webhook.js` VARIANT_TO_TIER mapping with your variant IDs

## Step 4: Configure Webhooks

1. LemonSqueezy → Settings → Webhooks
2. URL: `https://your-vercel-domain.vercel.app/api/webhook`
3. Secret: Same as WEBHOOK_SECRET env var
4. Events to listen:
   - subscription_created
   - subscription_updated
   - subscription_payment_success
   - subscription_payment_failed
   - subscription_cancelled

## Step 5: Link Checkout to Pricing Page

Update the CTA buttons in `index.html`:
- "Get Pro" → `https://your-store.lemonsqueezy.com/checkout/buy/VARIANT_ID`
- "Get Team" → `https://your-store.lemonsqueezy.com/checkout/buy/VARIANT_ID`
- "Contact Us" → `mailto:your@email.com`

## Step 6: Test the Flow

```bash
# 1. Generate a test key manually
curl -X POST https://your-domain.vercel.app/api/generate-key \
  -H "Authorization: Bearer YOUR_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"tier": "pro", "email": "test@test.com", "days": 30}'

# 2. Validate the key
curl -X POST https://your-domain.vercel.app/api/validate \
  -H "Content-Type: application/json" \
  -d '{"key": "PRO-XXXX-XXXX-XXXX-XXXX"}'

# 3. Install with the key
npx orchestrator-ai-framework init --company "Test" --license PRO-XXXX-XXXX-XXXX-XXXX

# 4. Check license status
node ~/.claude/orchestrator/license.js status
```

## Payment Flow Summary

```
Customer clicks "Get Pro" on pricing page
    ↓
LemonSqueezy checkout (handles payment, invoicing, taxes)
    ↓
Payment succeeds → LemonSqueezy sends webhook → /api/webhook
    ↓
Webhook generates license key → stores in Vercel KV
    ↓
Email sent to customer with: npx orchestrator-ai-framework init --license PRO-KEY
    ↓
Customer installs → framework calls /api/validate → confirms tier
    ↓
Monthly: LemonSqueezy charges → webhook → extends license
    ↓
Payment fails → webhook → 3 failures = suspend → grace period → downgrade
```

## API Reference

### POST /api/validate
Validates a license key.
```json
// Request
{ "key": "PRO-XXXX-XXXX", "tier": "pro", "email": "user@example.com" }

// Response
{ "valid": true, "tier": "pro", "status": "active", "expires_at": "2026-05-27T00:00:00Z", "features": {...} }
```

### POST /api/webhook
Receives payment webhooks from LemonSqueezy/Stripe.
Automatically handles: creation, renewal, failure, cancellation.

### POST /api/generate-key
Admin endpoint to manually create license keys.
```json
// Request (requires Authorization: Bearer ADMIN_SECRET)
{ "tier": "pro", "email": "client@example.com", "days": 30 }

// Response
{ "success": true, "key": "PRO-XXXX-XXXX", "install_command": "npx orchestrator-ai-framework init --license PRO-XXXX-XXXX" }
```
