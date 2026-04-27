/**
 * Key Generation API — POST /api/generate-key
 * Trial: anyone with email. Pro/Team/Enterprise/VIP: admin only.
 */

function randomHex(bytes) {
  let r = '';
  for (let i = 0; i < bytes; i++) r += Math.floor(Math.random() * 256).toString(16).padStart(2, '0');
  return r;
}

function generateKey(tier) {
  const prefix = tier === 'vip' ? 'VIP' : tier === 'enterprise' ? 'ENT' : tier === 'team' ? 'TEAM' : tier === 'trial' ? 'TRIAL' : 'PRO';
  return `${prefix}-${randomHex(8).toUpperCase().match(/.{4}/g).join('-')}`;
}

export default async function handler(req, res) {
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });

  const body = req.body || {};
  const tier = body.tier || 'trial';
  const email = body.email || '';
  const days = body.days || (tier === 'trial' ? 14 : 30);

  // Auth: trial = public, everything else = admin
  if (tier !== 'trial') {
    const auth = req.headers.authorization || '';
    const secret = process.env.ADMIN_SECRET;
    if (secret && auth !== `Bearer ${secret}`) {
      return res.status(401).json({ error: 'Admin key required for non-trial tiers.' });
    }
  }

  if (!['trial', 'pro', 'team', 'enterprise', 'vip'].includes(tier)) {
    return res.status(400).json({ error: 'Invalid tier.' });
  }

  // Email required for trial
  if (tier === 'trial' && (!email || !email.includes('@'))) {
    return res.status(400).json({ error: 'Email required for trial key.' });
  }

  const key = generateKey(tier);
  const isVip = tier === 'vip';
  const expiresAt = isVip ? null : new Date(Date.now() + days * 86400000).toISOString();

  console.log(`[KEY] ${key} (${tier}) for ${email || 'admin'}, expires ${expiresAt || 'never'}`);

  return res.status(200).json({
    success: true,
    key,
    tier,
    email,
    expires_at: expiresAt,
    install_command: `npx orchestrator-ai-framework init --license ${key}`
  });
}
