/**
 * Manual Key Generation API
 * POST /api/generate-key
 *
 * Admin endpoint to manually generate license keys.
 * Protected by ADMIN_SECRET env var.
 *
 * Body: { tier, email, days }
 * Returns: { key, tier, expires_at }
 */

const crypto = require('crypto');

async function setToKV(key, value) {
  const kvUrl = process.env.KV_REST_API_URL;
  const kvToken = process.env.KV_REST_API_TOKEN;
  if (!kvUrl || !kvToken) {
    console.log(`[MOCK] Would store: ${key}`);
    return;
  }
  try {
    await fetch(`${kvUrl}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${kvToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(["SET", key, JSON.stringify(value)])
    });
  } catch (e) {
    console.error(`KV SET failed: ${e.message}`);
  }
}

function generateKey(tier) {
  const prefix = tier === 'vip' ? 'VIP' : tier === 'enterprise' ? 'ENT' : tier === 'team' ? 'TEAM' : 'PRO';
  const random = crypto.randomBytes(8).toString('hex').toUpperCase();
  return `${prefix}-${random.match(/.{4}/g).join('-')}`;
}

export default async function handler(req, res) {
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });

  // Admin auth
  const authHeader = req.headers.authorization || '';
  const adminSecret = process.env.ADMIN_SECRET;
  if (adminSecret && authHeader !== `Bearer ${adminSecret}`) {
    return res.status(401).json({ error: 'Unauthorized. Provide ADMIN_SECRET.' });
  }

  const { tier = 'pro', email = '', days = 30 } = req.body || {};

  if (!['pro', 'team', 'enterprise', 'vip'].includes(tier)) {
    return res.status(400).json({ error: 'Invalid tier. Use: pro, team, enterprise, vip' });
  }

  const key = generateKey(tier);
  const isVip = tier === 'vip';
  const expires = isVip ? null : new Date();
  if (expires) expires.setDate(expires.getDate() + days);

  const license = {
    key,
    tier,
    email,
    status: 'active',
    created_at: new Date().toISOString(),
    expires_at: expires ? expires.toISOString() : null,
    lifetime: isVip,
    created_by: 'admin',
    subscription_id: 'manual',
    payment_provider: 'manual'
  };

  await setToKV(`license:${key}`, license);
  if (email) {
    await setToKV(`email:${email}`, { key, tier });
  }

  console.log(`[ADMIN] Generated ${key} (${tier}) for ${email || 'no-email'}, expires ${expires.toISOString()}`);

  return res.status(200).json({
    success: true,
    key,
    tier,
    email,
    expires_at: expires.toISOString(),
    install_command: `npx orchestrator-ai-framework init --license ${key}`
  });
}
