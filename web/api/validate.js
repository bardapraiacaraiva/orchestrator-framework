/**
 * License Validation API
 * POST /api/validate
 *
 * Called by the framework to verify a license key is valid.
 * Returns: { valid, tier, expires_at, status, features }
 *
 * Environment variables needed:
 *   LICENSE_SECRET — signing secret for key verification
 *   KV_REST_API_URL — Vercel KV (or Upstash Redis) URL
 *   KV_REST_API_TOKEN — Vercel KV token
 */

// In-memory fallback if no KV configured (for development)
const DEMO_LICENSES = {
  'PRO-DEMO-0000-0000': { tier: 'pro', email: 'demo@test.com', status: 'active', expires_at: '2026-12-31T23:59:59Z' },
  'TEAM-DEMO-0000-0000': { tier: 'team', email: 'demo@test.com', status: 'active', expires_at: '2026-12-31T23:59:59Z' },
  'ENT-DEMO-0000-0000': { tier: 'enterprise', email: 'demo@test.com', status: 'active', expires_at: '2026-12-31T23:59:59Z' },
};

const TIER_FEATURES = {
  community: { max_parallel: 2, playbooks: false, eval_calibration: false, advanced_analytics: false, multi_user: false, priority_support: false },
  pro: { max_parallel: 3, playbooks: true, eval_calibration: true, advanced_analytics: true, multi_user: false, priority_support: true },
  team: { max_parallel: 5, playbooks: true, eval_calibration: true, advanced_analytics: true, multi_user: true, max_seats: 5, priority_support: true },
  enterprise: { max_parallel: 10, playbooks: true, eval_calibration: true, advanced_analytics: true, multi_user: true, max_seats: 50, custom_presets: true, priority_support: true, sla_guaranteed: true },
};

async function getFromKV(key) {
  const kvUrl = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  if (!kvUrl || !kvToken) return null;

  try {
    const res = await fetch(`${kvUrl}/get/${key}`, {
      headers: { Authorization: `Bearer ${kvToken}` }
    });
    const data = await res.json();
    return data.result ? JSON.parse(data.result) : null;
  } catch {
    return null;
  }
}

async function setToKV(key, value, exSeconds) {
  const kvUrl = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  if (!kvUrl || !kvToken) return;

  try {
    const body = exSeconds
      ? `SET ${key} ${JSON.stringify(JSON.stringify(value))} EX ${exSeconds}`
      : `SET ${key} ${JSON.stringify(JSON.stringify(value))}`;
    await fetch(`${kvUrl}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${kvToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(["SET", key, JSON.stringify(value), ...(exSeconds ? ["EX", exSeconds] : [])])
    });
  } catch {}
}

export default async function handler(req, res) {
  // CORS preflight
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed. Use POST.' });
  }

  const { key, tier, email } = req.body || {};

  if (!key) {
    return res.status(400).json({ valid: false, error: 'Missing license key' });
  }

  // 1. Check KV store first
  let license = await getFromKV(`license:${key}`);

  // 2. Fallback to demo licenses
  if (!license && DEMO_LICENSES[key]) {
    license = DEMO_LICENSES[key];
  }

  // 3. Key not found
  if (!license) {
    return res.status(404).json({
      valid: false,
      status: 'not_found',
      message: 'License key not found. Check your key or purchase at orchestrator-ai.com'
    });
  }

  // 4. Check expiration
  const now = new Date();
  const expires = new Date(license.expires_at);
  const graceEnd = new Date(expires);
  graceEnd.setDate(graceEnd.getDate() + 7);

  let status = 'active';
  let valid = true;

  if (license.status === 'suspended') {
    status = 'suspended';
    valid = false;
  } else if (now > graceEnd) {
    status = 'expired';
    valid = false;
  } else if (now > expires) {
    status = 'grace';
    valid = true;
  }

  // 5. Log validation (analytics)
  await setToKV(`validation:${key}:${now.toISOString().split('T')[0]}`, {
    key, tier: license.tier, status, timestamp: now.toISOString()
  }, 86400 * 90); // Keep 90 days

  return res.status(200).json({
    valid,
    tier: valid ? license.tier : 'community',
    status,
    expires_at: license.expires_at,
    features: TIER_FEATURES[valid ? license.tier : 'community'],
    message: status === 'grace' ? 'License expired. Grace period active (7 days).' :
             status === 'expired' ? 'License expired. Downgraded to Community.' :
             status === 'suspended' ? 'License suspended. Contact support.' : null
  });
}
